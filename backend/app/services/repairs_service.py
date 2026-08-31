"""Repair hub business logic (drop-off / pickup intermediary).

State machine:
    RECEIVED --send_to_center--> SENT_OUT --receive_from_center--> RETURNED
    RECEIVED --hand_to_technician--> WITH_TECHNICIAN
             --receive_from_technician--> RETURNED
    RETURNED --deliver_repair--> DELIVERED (invoice) or CLOSED (free)
    RECEIVED/SENT_OUT/WITH_TECHNICIAN/RETURNED --cancel_repair--> CANCELLED

The customer's account is updated at delivery: the final invoice passes the
repair cost (center's actual charge or technician parts+labor) through and
adds the shop's service fee.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.enums import DocType, ItemStatus, MovementType, RepairStatus, UserRole
from app.core.exceptions import BusinessError
from app.core.numbering import next_number
from app.models import Invoice, Item, RepairCenter, RepairOrder, StockMovement, User
from app.services import sales_service

settings = get_settings()


# ---------------------------------------------------------------------------
# Repair centers
# ---------------------------------------------------------------------------


def create_repair_center(db: Session, *, name: str, phone: str | None = None,
                         email: str | None = None, address: str | None = None,
                         notes: str | None = None) -> RepairCenter:
    # FIX: CHANGES.md claims this function checks for a duplicate phone and
    # raises BusinessError(409) — the original code had no such check and
    # relied entirely on the DB-level UNIQUE constraint, which raises a raw
    # IntegrityError (500) instead of a clean 409. Added an explicit
    # pre-check for a fast, friendly error, PLUS a try/except around the
    # insert to correctly catch the (rare but real) race where two requests
    # pass the pre-check at the same time before either commits.
    phone = phone.strip() if phone else None
    if phone:
        existing = db.scalar(select(RepairCenter).where(RepairCenter.phone == phone))
        if existing is not None:
            raise BusinessError(
                f"A repair center with phone '{phone}' already exists ({existing.name})",
                409,
            )

    center = RepairCenter(name=name.strip(), phone=phone, email=email,
                          address=address, notes=notes)
    db.add(center)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise BusinessError(f"A repair center with phone '{phone}' already exists", 409)
    db.refresh(center)
    return center


def find_repair_centers(db: Session, *, active_only: bool = False) -> list[RepairCenter]:
    stmt = select(RepairCenter).order_by(RepairCenter.name)
    if active_only:
        stmt = stmt.where(RepairCenter.is_active.is_(True))
    return list(db.scalars(stmt))


def update_repair_center(
    db: Session,
    center_id: int,
    *,
    name: str | None = None,
    phone: str | None = None,
    email: str | None = None,
    address: str | None = None,
    notes: str | None = None,
    is_active: bool | None = None,
) -> RepairCenter:
    center = db.get(RepairCenter, center_id)
    if center is None:
        raise BusinessError("مركز الصيانة غير موجود", 404)

    if name is not None:
        center.name = name.strip()
    if phone is not None:
        phone = phone.strip() if phone else None
        if phone != center.phone:
            existing = db.scalar(select(RepairCenter).where(RepairCenter.phone == phone, RepairCenter.id != center_id))
            if existing is not None:
                raise BusinessError(
                    f"مركز صيانة تاني بنفس رقم الموبايل '{phone}' موجود ({existing.name})",
                    409,
                )
        center.phone = phone
    if email is not None:
        center.email = email.strip() if email else None
    if address is not None:
        center.address = address.strip() if address else None
    if notes is not None:
        center.notes = notes.strip() if notes else None
    if is_active is not None:
        center.is_active = is_active

    db.commit()
    db.refresh(center)
    return center


# ---------------------------------------------------------------------------
# Step 1 — receive the device from the customer
# ---------------------------------------------------------------------------


def receive_device(
    db: Session,
    *,
    customer_id: int,
    device_description: str,
    reported_issue: str,
    condition_received: str | None = None,
    item_uuid: str | None = None,
    notes: str | None = None,
    user_id: int | None = None,
) -> RepairOrder:
    """Register the device, the fault and its visible condition; the
    customer gets a numbered receipt (RPR-...)."""

    item: Item | None = None
    if item_uuid:
        item = db.scalar(select(Item).where(Item.uuid == item_uuid.strip().lower()))
        if item is None:
            raise BusinessError(f"Unit with barcode '{item_uuid}' not found", 404)
        if item.status != ItemStatus.SOLD:
            raise BusinessError(
                f"Unit {item.serial_number or item.uuid} is not sold to a customer "
                f"(current: {item.status.value})",
                409,
            )

    repair = RepairOrder(
        number=next_number(db, DocType.REPAIR, settings.repair_prefix),
        customer_id=customer_id,
        item_id=item.id if item else None,
        device_description=device_description.strip(),
        reported_issue=reported_issue.strip(),
        # FIX: strip condition_received like the other free-text fields so
        # accidental leading/trailing whitespace doesn't slip into the DB.
        condition_received=condition_received.strip() if condition_received else None,
        status=RepairStatus.RECEIVED,
        notes=notes,
        user_id=user_id,
    )
    db.add(repair)
    db.flush()  # movements below reference repair.id

    if item is not None:
        item.status = ItemStatus.IN_REPAIR
        db.add(StockMovement(
            item_id=item.id,
            movement_type=MovementType.REPAIR_IN,
            ref_type="repair",
            ref_id=repair.id,
            user_id=user_id,
            notes=f"Repair {repair.number}: received from customer",
        ))

    db.add(repair)
    db.commit()
    db.refresh(repair)
    return repair


# ---------------------------------------------------------------------------
# Step 2 — send to the external repair center
# ---------------------------------------------------------------------------


def send_to_center(
    db: Session,
    repair_id: int,
    *,
    repair_center_id: int,
    expected_cost: Decimal = Decimal("0.00"),
    external_tracking: str | None = None,
    technician_name: str | None = None,
    user_id: int | None = None,
) -> RepairOrder:
    repair = db.get(RepairOrder, repair_id)
    if repair is None:
        raise BusinessError("Repair order not found", 404)
    if repair.status != RepairStatus.RECEIVED:
        raise BusinessError(
            f"Cannot send to center from status '{repair.status}' — "
            "only received devices can be sent out",
            409,
        )
    center = db.get(RepairCenter, repair_center_id)
    if center is None or not center.is_active:
        raise BusinessError("Repair center not found", 404)

    # FIX: reject a negative expected_cost instead of silently storing it —
    # a negative value here would later flow into repair.total at delivery.
    expected_cost = Decimal(str(expected_cost))
    if expected_cost < 0:
        raise BusinessError("expected_cost cannot be negative", 400)

    repair.repair_center_id = center.id
    repair.external_tracking = external_tracking
    repair.expected_cost = expected_cost
    repair.sent_at = datetime.now()
    repair.status = RepairStatus.SENT_OUT
    if repair.item_id is not None:
        db.add(StockMovement(
            item_id=repair.item_id,
            movement_type=MovementType.REPAIR_OUT,
            ref_type="repair",
            ref_id=repair.id,
            user_id=user_id,
            notes=f"Repair {repair.number}: handed to center {center.name}",
        ))
    repair.notes = ((repair.notes or "") + f"\nSent to {center.name} "
                    f"({repair.external_tracking or 'no tracking'})"
                    + (f" — Tech: {technician_name}" if technician_name else ""))
    db.commit()
    db.refresh(repair)
    return repair


# ---------------------------------------------------------------------------
# Step 2 (internal) — hand the device to a specific staff technician
# ---------------------------------------------------------------------------


def hand_to_technician(
    db: Session,
    repair_id: int,
    *,
    technician_id: int,
    notes: str | None = None,
    user_id: int | None = None,
) -> RepairOrder:
    """Assign the device to a specific technician (multi-technician support).
    The device leaves the counter with the technician (WITH_TECHNICIAN)."""
    repair = db.get(RepairOrder, repair_id)
    if repair is None:
        raise BusinessError("Repair order not found", 404)
    if repair.status != RepairStatus.RECEIVED:
        raise BusinessError(
            f"Cannot hand to technician from status '{repair.status}' — "
            "only received devices can be handed over",
            409,
        )
    technician = db.get(User, technician_id)
    if technician is None or not technician.is_active:
        raise BusinessError("Technician not found", 404)
    if technician.role != UserRole.TECHNICIAN:
        raise BusinessError("The selected user is not a technician", 400)

    repair.technician_id = technician.id
    repair.handed_to_tech_at = datetime.now()
    repair.status = RepairStatus.WITH_TECHNICIAN
    if notes:
        repair.notes = (repair.notes or "") + f"\nHanded to technician: {notes}"
    else:
        repair.notes = (repair.notes or "") + f"\nHanded to technician {technician.full_name}"
    if repair.item_id is not None:
        db.add(StockMovement(
            item_id=repair.item_id,
            movement_type=MovementType.REPAIR_OUT,
            ref_type="repair",
            ref_id=repair.id,
            user_id=user_id,
            notes=f"Repair {repair.number}: handed to technician {technician.full_name}",
        ))
    db.commit()
    db.refresh(repair)
    return repair


# ---------------------------------------------------------------------------
# Step 3 (internal) — receive the device back from the technician
# ---------------------------------------------------------------------------


def receive_from_technician(
    db: Session,
    repair_id: int,
    *,
    actual_cost: Decimal = Decimal("0.00"),
    repair_result: str | None = None,
    user_id: int | None = None,
) -> RepairOrder:
    """The technician returns the device — ready for customer pickup.
    `actual_cost` = parts + technician labor, billed at delivery."""
    repair = db.get(RepairOrder, repair_id)
    if repair is None:
        raise BusinessError("Repair order not found", 404)
    if repair.status != RepairStatus.WITH_TECHNICIAN:
        raise BusinessError(
            f"Cannot receive from technician from status '{repair.status}' — "
            "the device must first be handed to a technician",
            409,
        )

    # FIX: same negative-amount guard as the center flow below — actual_cost
    # feeds straight into the delivery invoice.
    actual_cost = Decimal(str(actual_cost))
    if actual_cost < 0:
        raise BusinessError("actual_cost cannot be negative", 400)

    repair.actual_cost = actual_cost
    repair.repair_result = repair_result
    repair.received_from_tech_at = datetime.now()
    repair.status = RepairStatus.RETURNED
    tech_name = repair.technician.full_name if repair.technician else "technician"
    repair.notes = (repair.notes or "") + (
        f"\nReturned from technician {tech_name}: {repair_result or 'no result'}")
    if repair.item_id is not None:
        db.add(StockMovement(
            item_id=repair.item_id,
            movement_type=MovementType.REPAIR_IN,
            ref_type="repair",
            ref_id=repair.id,
            user_id=user_id,
            notes=f"Repair {repair.number}: back from technician, ready for pickup",
        ))
    db.commit()
    db.refresh(repair)
    return repair


# ---------------------------------------------------------------------------
# Step 3 — receive back from the center
# ---------------------------------------------------------------------------


def receive_from_center(
    db: Session,
    repair_id: int,
    *,
    actual_cost: Decimal = Decimal("0.00"),
    repair_result: str | None = None,
    user_id: int | None = None,
) -> RepairOrder:
    repair = db.get(RepairOrder, repair_id)
    if repair is None:
        raise BusinessError("Repair order not found", 404)
    if repair.status != RepairStatus.SENT_OUT:
        raise BusinessError(
            f"Cannot receive back from status '{repair.status}' — "
            "the device must first be sent to the center",
            409,
        )

    # FIX: negative-amount guard (see receive_from_technician above).
    actual_cost = Decimal(str(actual_cost))
    if actual_cost < 0:
        raise BusinessError("actual_cost cannot be negative", 400)

    repair.actual_cost = actual_cost
    repair.repair_result = repair_result
    repair.returned_at = datetime.now()
    repair.status = RepairStatus.RETURNED
    repair.notes = (repair.notes or "") + f"\nReturned from center: {repair_result or 'no result'}"
    if repair.item_id is not None:
        db.add(StockMovement(
            item_id=repair.item_id,
            movement_type=MovementType.REPAIR_IN,
            ref_type="repair",
            ref_id=repair.id,
            user_id=user_id,
            notes=f"Repair {repair.number}: back from center, ready for pickup",
        ))
    db.commit()
    db.refresh(repair)
    return repair


# ---------------------------------------------------------------------------
# Step 4 — deliver to the customer (final invoice updates their account)
# ---------------------------------------------------------------------------


def deliver_repair(
    db: Session,
    repair_id: int,
    *,
    shop_fee: Decimal = Decimal("0.00"),
    notes: str | None = None,
    payments: list[dict] | None = None,
    user_id: int | None = None,
) -> tuple[RepairOrder, Invoice | None]:
    """Hand the device back. The customer is billed with a final invoice:
    the center's actual cost passes through + the shop's service fee. When
    nothing is charged, the order closes without an invoice (CLOSED).

    NOTE (not fixed here — needs sales_service.py to confirm): if
    sales_service.create_invoice() commits its own transaction internally
    and then something below fails (e.g. repair.item_id points at a
    missing Item), you can end up with a committed Invoice that has no
    matching repair.status/invoice_id update. That is only fixable from
    this file if create_invoice() can be called without an internal
    commit (flush-only) so this whole function commits atomically once.
    """
    repair = db.get(RepairOrder, repair_id)
    if repair is None:
        raise BusinessError("Repair order not found", 404)
    if repair.status != RepairStatus.RETURNED:
        raise BusinessError(
            f"Cannot deliver from status '{repair.status}' — "
            "the device must be back from the center first",
            409,
        )

    fee = Decimal(str(shop_fee))
    # FIX: guard against a negative shop fee (would otherwise reduce the
    # invoice total silently instead of failing loudly).
    if fee < 0:
        raise BusinessError("shop_fee cannot be negative", 400)

    if repair.technician_id is not None:
        center_name = repair.technician.full_name if repair.technician else "technician"
    else:
        center_name = repair.center.name if repair.center else "external center"
    lines: list[dict] = []
    if repair.actual_cost > 0:
        lines.append({
            "item_uuid": None,
            "description": (
                f"Repair {repair.number}: {repair.device_description} "
                f"({repair.repair_result or 'repaired'} — {center_name})"
            ),
            "quantity": 1,
            "unit_price": repair.actual_cost,
        })
    if fee > 0:
        lines.append({
            "item_uuid": None,
            "description": f"Repair {repair.number}: shop service fee",
            "quantity": 1,
            "unit_price": fee,
        })

    invoice: Invoice | None = None
    if lines:
        invoice = sales_service.create_invoice(
            db,
            customer_id=repair.customer_id,
            lines=lines,
            notes=notes or f"Repair {repair.number} delivery",
            payments=payments,
            user_id=user_id,
        )
        repair.invoice_id = invoice.id
        repair.total = repair.actual_cost + fee
        repair.shop_fee = fee
        repair.status = RepairStatus.DELIVERED
    else:
        repair.total = Decimal("0.00")
        repair.shop_fee = Decimal("0.00")
        repair.status = RepairStatus.CLOSED

    repair.delivered_at = datetime.now()
    if repair.item_id is not None:
        item = db.get(Item, repair.item_id)
        # FIX: guard against a dangling item_id (item deleted/missing)
        # instead of raising an unhandled AttributeError after the
        # invoice has already been committed above.
        if item is None:
            raise BusinessError(
                f"Repair {repair.number} references a missing item (id={repair.item_id})",
                500,
            )
        item.status = ItemStatus.SOLD
        db.add(StockMovement(
            item_id=item.id,
            movement_type=MovementType.REPAIR_OUT,
            ref_type="repair",
            ref_id=repair.id,
            user_id=user_id,
            notes=f"Repair {repair.number}: delivered to customer",
        ))

    db.commit()
    db.refresh(repair)
    if invoice is not None:
        db.refresh(invoice)
    return repair, invoice


# ---------------------------------------------------------------------------
# Cancel (abandoned / not repairable)
# ---------------------------------------------------------------------------


def cancel_repair(
    db: Session,
    repair_id: int,
    *,
    reason: str,
    user_id: int | None = None,
) -> RepairOrder:
    """Cancel an open repair: the device goes back to the customer with no
    charge (or the order stays cancelled if it was never picked up)."""
    repair = db.get(RepairOrder, repair_id)
    if repair is None:
        raise BusinessError("Repair order not found", 404)
    if repair.status in (RepairStatus.DELIVERED, RepairStatus.CLOSED, RepairStatus.CANCELLED):
        raise BusinessError(f"Repair is already {repair.status}", 409)

    repair.status = RepairStatus.CANCELLED
    # FIX: the original code wrote datetime.now() into `delivered_at` for a
    # CANCELLED order. That's misleading — any report or query that filters
    # "delivered_at IS NOT NULL" to mean "delivered repairs" would wrongly
    # include cancelled ones. There is no cancelled_at column on RepairOrder
    # per the current schema, so the safe fix without a migration is to NOT
    # touch delivered_at and rely on `status == CANCELLED` + the timestamped
    # note below. If you want a queryable cancellation date, add a
    # `cancelled_at` column via a new alembic migration instead of reusing
    # delivered_at.
    repair.notes = (repair.notes or "") + f"\nCancelled: {reason} (at {datetime.now().isoformat()})"
    if repair.item_id is not None:
        item = db.get(Item, repair.item_id)
        # FIX: same dangling item_id guard as deliver_repair.
        if item is None:
            raise BusinessError(
                f"Repair {repair.number} references a missing item (id={repair.item_id})",
                500,
            )
        item.status = ItemStatus.SOLD
        db.add(StockMovement(
            item_id=item.id,
            movement_type=MovementType.REPAIR_OUT,
            ref_type="repair",
            ref_id=repair.id,
            user_id=user_id,
            notes=f"Repair {repair.number} cancelled: {reason}",
        ))
    db.commit()
    db.refresh(repair)
    return repair


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


def find_repairs(
    db: Session,
    *,
    status: RepairStatus | None = None,
    customer_id: int | None = None,
    technician_id: int | None = None,
    search: str | None = None,
    limit: int = 200,
) -> list[RepairOrder]:
    stmt = select(RepairOrder).order_by(RepairOrder.id.desc()).limit(limit)
    if status is not None:
        stmt = stmt.where(RepairOrder.status == status)
    if customer_id is not None:
        stmt = stmt.where(RepairOrder.customer_id == customer_id)
    if technician_id is not None:
        stmt = stmt.where(RepairOrder.technician_id == technician_id)
    if search:
        q = f"%{search.strip()}%"
        stmt = stmt.where(or_(
            RepairOrder.number.ilike(q),
            RepairOrder.device_description.ilike(q),
            RepairOrder.reported_issue.ilike(q),
        ))
    return list(db.scalars(stmt))
