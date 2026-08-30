"""Sends (or simulates + logs) a WhatsApp notification for a repair status
event. Called from the repairs API routes right after a state-machine
transition succeeds — kept out of repairs_service.py itself so that core
business logic doesn't depend on an external messaging integration.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import RepairOrder, WhatsAppMessage
from app.services.whatsapp_client import WhatsAppClient

_EVENT_MESSAGES = {
    "received": "تم استلام جهازك ({device}) بنجاح — رقم الصيانة {number}. هنبلغك أول ما يبقى جاهز للاستلام.",
    "ready": "خبر سعيد! جهازك ({device}) بقى جاهز للاستلام — رقم الصيانة {number}.",
    "delivered": "تم تسليم جهازك ({device}) بنجاح — رقم الصيانة {number}. شكرًا لثقتك فينا!",
}


def notify_repair_event(db: Session, repair: RepairOrder, event: str) -> dict | None:
    """event: 'received' | 'ready' | 'delivered'. Returns None if the
    customer has no phone on file (nothing to notify) or the event isn't
    one we send a message for."""
    template = _EVENT_MESSAGES.get(event)
    if template is None:
        return None
    phone = repair.customer.phone if repair.customer else None
    if not phone:
        return None

    body = template.format(device=repair.device_description, number=repair.number)
    client = WhatsAppClient()
    result = client.send_text(phone, body)

    db.add(WhatsAppMessage(
        direction="out", phone=phone, message_type="text", body=body,
        status="simulated" if not client.configured else "sent",
        customer_id=repair.customer_id, repair_id=repair.id,
    ))
    db.commit()
    return result
