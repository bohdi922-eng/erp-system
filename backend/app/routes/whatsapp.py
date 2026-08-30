"""WhatsApp bot: Meta Cloud API webhook + a simulate-inbound endpoint for
testing the exact same logic without a real Meta account yet.

Once you have a real WhatsApp Business API account, point Meta's webhook
configuration at:  https://<your-public-domain>/api/whatsapp/webhook
(this needs a real public HTTPS URL — a tunnel like ngrok during testing,
or a real deployment; 127.0.0.1 will not work for Meta's side, since
Meta's servers call this URL over the internet, not your own machine).
Until then, use POST /api/whatsapp/simulate-inbound to test the same
customer-inquiry / OCR logic locally.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.enums import RepairStatus
from app.core.exceptions import BusinessError
from app.database import get_session
from app.models import Customer, WhatsAppMessage
from app.services import ocr_service, repairs_service
from app.services.whatsapp_client import WhatsAppClient

router = APIRouter()
settings = get_settings()


def _normalize_phone(phone: str) -> str:
    return "".join(ch for ch in phone if ch.isdigit())


def _find_customer_by_phone(db: Session, phone: str) -> Customer | None:
    target = _normalize_phone(phone)
    for c in db.scalars(select(Customer).where(Customer.phone.is_not(None))).all():
        if _normalize_phone(c.phone) == target or _normalize_phone(c.phone).endswith(target[-9:]):
            return c
    return None


def _build_status_reply(db: Session, customer: Customer) -> str:
    open_repairs = [
        r for r in repairs_service.find_repairs(db, customer_id=customer.id)
        if r.status not in (RepairStatus.DELIVERED.value, RepairStatus.CLOSED.value, RepairStatus.CANCELLED.value)
    ]
    if not open_repairs:
        return f"مرحبًا {customer.name}، مفيش أي صيانة مفتوحة على حسابك حاليًا."

    status_ar = {
        "received": "تم الاستلام، في انتظار الفني",
        "with_technician": "جاري العمل عليه مع الفني",
        "sent_out": "مرسل لمركز الصيانة الخارجي",
        "returned": "جاهز للاستلام!",
    }
    lines = [f"مرحبًا {customer.name}، حالة صيانتك:"]
    for r in open_repairs:
        lines.append(f"- {r.number}: {r.device_description} — {status_ar.get(r.status, r.status)}")
    return "\n".join(lines)


def _handle_text_message(db: Session, phone: str, text: str) -> str:
    customer = _find_customer_by_phone(db, phone)
    if customer is None:
        return "مرحبًا! رقمك مش مسجل عندنا كعميل. اتصل بالمحل لو محتاج مساعدة."
    return _build_status_reply(db, customer)


def _handle_image_message(db: Session, phone: str, media_id: str | None, raw_bytes: bytes | None) -> str:
    client = WhatsAppClient()
    if raw_bytes is None:
        if media_id is None or not client.configured:
            return (
                "استلمنا صورة، بس معالجة صور الواتساب الحقيقية محتاجة حساب "
                "Meta API فعلي متصل — جرّبها دلوقتي عن طريق simulate-inbound "
                "مع صورة تجريبية بدل كده."
            )
        raw_bytes = client.fetch_media_bytes(media_id)

    extracted = ocr_service.extract_text_from_image(raw_bytes)
    return f"استلمنا الصورة! النص اللي قدرنا نقراه منها:\n\n{extracted}"


def _log_and_reply(db: Session, phone: str, inbound_body: str, inbound_type: str, reply_body: str, customer_id: int | None) -> None:
    db.add(WhatsAppMessage(
        direction="in", phone=phone, message_type=inbound_type, body=inbound_body,
        status="received", customer_id=customer_id,
    ))
    client = WhatsAppClient()
    result = client.send_text(phone, reply_body)
    db.add(WhatsAppMessage(
        direction="out", phone=phone, message_type="text", body=reply_body,
        status="simulated" if not client.configured else "sent", customer_id=customer_id,
    ))
    db.commit()


@router.get("/webhook")
def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
):
    """Meta calls this once, when you configure the webhook URL in their
    dashboard, to confirm you control this endpoint."""
    if hub_mode == "subscribe" and hub_verify_token == settings.whatsapp_verify_token:
        return PlainTextResponse(hub_challenge or "")
    raise BusinessError("Webhook verification failed", 403)


@router.post("/webhook")
def receive_webhook(payload: dict, db: Session = Depends(get_session)) -> dict:
    """Real Meta webhook payloads land here. Parses their documented
    structure: entry[].changes[].value.messages[]."""
    try:
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                for msg in change.get("value", {}).get("messages", []):
                    phone = msg.get("from", "")
                    msg_type = msg.get("type")
                    customer = _find_customer_by_phone(db, phone)
                    if msg_type == "text":
                        text = msg.get("text", {}).get("body", "")
                        reply = _handle_text_message(db, phone, text)
                        _log_and_reply(db, phone, text, "text", reply, customer.id if customer else None)
                    elif msg_type == "image":
                        media_id = msg.get("image", {}).get("id")
                        reply = _handle_image_message(db, phone, media_id, None)
                        _log_and_reply(db, phone, "[image]", "image", reply, customer.id if customer else None)
    except Exception as exc:
        # Meta expects a 200 regardless, or it will keep retrying delivery —
        # log the failure instead of raising, so a single bad payload
        # doesn't get redelivered forever.
        return {"status": "error", "detail": str(exc)}
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Test-only: simulate an inbound message without a real Meta account
# ---------------------------------------------------------------------------

class SimulateInboundBody(BaseModel):
    phone: str
    message_type: str = "text"  # "text" | "image"
    text: str | None = None
    # For image testing: base64-encoded image bytes (small test receipts
    # only — this is a dev/testing convenience, not how real WhatsApp
    # media arrives).
    image_base64: str | None = None


@router.post("/simulate-inbound")
def simulate_inbound(body: SimulateInboundBody, db: Session = Depends(get_session)) -> dict:
    """Exercises the exact same _handle_text_message / _handle_image_message
    logic real webhook messages use — for testing the bot without a real
    Meta WhatsApp Business API account."""
    customer = _find_customer_by_phone(db, body.phone)

    if body.message_type == "text":
        text = body.text or ""
        reply = _handle_text_message(db, body.phone, text)
        _log_and_reply(db, body.phone, text, "text", reply, customer.id if customer else None)
    elif body.message_type == "image":
        import base64
        raw_bytes = base64.b64decode(body.image_base64) if body.image_base64 else b""
        reply = _handle_image_message(db, body.phone, None, raw_bytes)
        _log_and_reply(db, body.phone, "[simulated image]", "image", reply, customer.id if customer else None)
    else:
        raise BusinessError(f"Unknown message_type '{body.message_type}'", 400)

    return {"reply": reply, "customer_matched": customer.name if customer else None}


@router.get("/messages")
def list_messages(db: Session = Depends(get_session)) -> list[dict]:
    messages = db.scalars(
        select(WhatsAppMessage).order_by(WhatsAppMessage.id.desc()).limit(100)
    ).all()
    return [
        {
            "id": m.id, "direction": m.direction, "phone": m.phone,
            "message_type": m.message_type, "body": m.body, "status": m.status,
            "customer_id": m.customer_id, "created_at": m.created_at.isoformat(),
        }
        for m in messages
    ]


@router.get("/status")
def whatsapp_status() -> dict:
    client = WhatsAppClient()
    return {"configured": client.configured}
