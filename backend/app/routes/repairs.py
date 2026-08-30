from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import RepairStatus
from app.database import get_session
from app.models import RepairCenter, RepairOrder
from app.services import notify_service, repairs_service

router = APIRouter()


def _days_ago(dt: datetime | None) -> int:
    if dt is None:
        return 0
    return max(0, (datetime.now() - dt).days)


def _card(rep: RepairOrder) -> dict:
    return {
        "id": rep.id,
        "number": rep.number,
        "device_description": rep.device_description,
        "reported_issue": rep.reported_issue,
        "customer_name": rep.customer.name if rep.customer else None,
        "technician_name": rep.technician.full_name if rep.technician else None,
        "center_name": rep.center.name if rep.center else None,
        "status": rep.status,
        "days": _days_ago(rep.created_at),
    }


@router.get("/centers")
def list_centers(db: Session = Depends(get_session)) -> list[dict]:
    centers = db.scalars(select(RepairCenter).where(RepairCenter.is_active.is_(True))).all()
    return [{"id": c.id, "name": c.name} for c in centers]


@router.get("/board")
def repairs_board(db: Session = Depends(get_session)) -> dict:
    all_open = db.scalars(
        select(RepairOrder).where(
            RepairOrder.status.not_in([RepairStatus.CANCELLED.value])
        ).order_by(RepairOrder.id.desc())
    ).all()

    columns = {"received": [], "with_technician": [], "returned": [], "delivered": []}
    for rep in all_open:
        card = _card(rep)
        if rep.status == RepairStatus.RECEIVED.value:
            columns["received"].append(card)
        elif rep.status in (RepairStatus.WITH_TECHNICIAN.value, RepairStatus.SENT_OUT.value):
            columns["with_technician"].append(card)
        elif rep.status == RepairStatus.RETURNED.value:
            columns["returned"].append(card)
        elif rep.status in (RepairStatus.DELIVERED.value, RepairStatus.CLOSED.value):
            columns["delivered"].append(card)

    return {
        "columns": columns,
        "counts": {k: len(v) for k, v in columns.items()},
    }


# ---------------------------------------------------------------------------
# Actions — thin wrappers around repairs_service
# ---------------------------------------------------------------------------

class ReceiveDeviceBody(BaseModel):
    customer_id: int
    device_description: str
    reported_issue: str
    condition_received: str | None = None
    item_uuid: str | None = None
    notes: str | None = None
    user_id: int | None = None


@router.post("/receive")
def receive_device(body: ReceiveDeviceBody, db: Session = Depends(get_session)) -> dict:
    rep = repairs_service.receive_device(db, **body.model_dump())
    notify_service.notify_repair_event(db, rep, "received")
    return _card(rep)


class HandToTechnicianBody(BaseModel):
    technician_id: int
    notes: str | None = None
    user_id: int | None = None


@router.post("/{repair_id}/hand-to-technician")
def hand_to_technician(repair_id: int, body: HandToTechnicianBody, db: Session = Depends(get_session)) -> dict:
    rep = repairs_service.hand_to_technician(db, repair_id, **body.model_dump())
    return _card(rep)


class SendToCenterBody(BaseModel):
    repair_center_id: int
    expected_cost: Decimal = Decimal("0.00")
    external_tracking: str | None = None
    technician_name: str | None = None
    user_id: int | None = None


@router.post("/{repair_id}/send-to-center")
def send_to_center(repair_id: int, body: SendToCenterBody, db: Session = Depends(get_session)) -> dict:
    rep = repairs_service.send_to_center(db, repair_id, **body.model_dump())
    return _card(rep)


class ReceiveBackBody(BaseModel):
    actual_cost: Decimal = Decimal("0.00")
    repair_result: str | None = None
    user_id: int | None = None


@router.post("/{repair_id}/receive-from-technician")
def receive_from_technician(repair_id: int, body: ReceiveBackBody, db: Session = Depends(get_session)) -> dict:
    rep = repairs_service.receive_from_technician(db, repair_id, **body.model_dump())
    notify_service.notify_repair_event(db, rep, "ready")
    return _card(rep)


@router.post("/{repair_id}/receive-from-center")
def receive_from_center(repair_id: int, body: ReceiveBackBody, db: Session = Depends(get_session)) -> dict:
    rep = repairs_service.receive_from_center(db, repair_id, **body.model_dump())
    notify_service.notify_repair_event(db, rep, "ready")
    return _card(rep)


class DeliverBody(BaseModel):
    shop_fee: Decimal = Decimal("0.00")
    notes: str | None = None
    payments: list[dict] | None = None
    user_id: int | None = None


@router.post("/{repair_id}/deliver")
def deliver_repair(repair_id: int, body: DeliverBody, db: Session = Depends(get_session)) -> dict:
    rep, invoice = repairs_service.deliver_repair(db, repair_id, **body.model_dump())
    notify_service.notify_repair_event(db, rep, "delivered")
    return {**_card(rep), "invoice_number": invoice.number if invoice else None}


class CancelBody(BaseModel):
    reason: str
    user_id: int | None = None


@router.post("/{repair_id}/cancel")
def cancel_repair(repair_id: int, body: CancelBody, db: Session = Depends(get_session)) -> dict:
    rep = repairs_service.cancel_repair(db, repair_id, **body.model_dump())
    return _card(rep)
