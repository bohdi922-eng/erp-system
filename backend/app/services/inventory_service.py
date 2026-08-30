"""Inventory business logic: items, stock movements, serial validation.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.enums import DocType, ItemStatus, MovementType
from app.core.exceptions import BusinessError
from app.core.numbering import next_number
from app.models import Item, Product, PurchaseOrder, PurchaseOrderLine, StockMovement, Supplier

settings = get_settings()


def _validate_serialized_product(db: Session, product: Product, serials: list[str]) -> None:
    """Ensure serialized products get serial numbers on receive."""
    if product.is_serialized and not serials:
        raise BusinessError(
            f"Product '{product.brand} {product.model}' is serialized — "
            "serial numbers are required on receive",
            400,
        )


def create_item(
    db: Session,
    *,
    product_id: int,
    serial_number: str | None,
    purchase_cost: Decimal,
    purchase_date: date | None = None,
    warranty_months: int = 0,
    warranty_terms: str | None = None,
    location_id: int | None = None,
    supplier_id: int | None = None,
    notes: str | None = None,
    # FIX: this function had no user_id parameter at all, so the
    # StockMovement it creates below always recorded user_id=None — on a
    # multi-user system, there was no audit trail of *who* manually added
    # a unit to stock. Added the parameter and wired it through.
    user_id: int | None = None,
) -> Item:
    """Create a single physical unit (Item)."""
    product = db.get(Product, product_id)
    if product is None:
        raise BusinessError("Product not found", 404)

    # FIX: this was duplicated inline instead of calling the
    # `_validate_serialized_product()` helper that already exists a few
    # lines above — the helper was dead code, never called from anywhere
    # in the file. Using it here removes the duplication (and is the
    # reason the helper exists in the first place).
    _validate_serialized_product(db, product, [serial_number] if serial_number else [])

    item = Item(
        product_id=product_id,
        serial_number=serial_number.strip() if serial_number else None,
        status=ItemStatus.IN_STOCK,
        location_id=location_id,
        supplier_id=supplier_id,
        purchase_cost=Decimal(str(purchase_cost)),
        purchase_date=purchase_date or date.today(),
        warranty_months=warranty_months,
        warranty_terms=warranty_terms,
        notes=notes,
    )
    db.add(item)
    db.flush()

    db.add(StockMovement(
        item_id=item.id,
        movement_type=MovementType.PURCHASE,
        ref_type="purchase",
        ref_id=None,
        user_id=user_id,
        notes=f"Item created: {product.brand} {product.model}",
    ))

    db.commit()
    db.refresh(item)
    return item


def receive_purchase(
    db: Session,
    purchase_id: int,
    *,
    serials_by_line: dict[int, list[str]] | None = None,
    warranty_by_line: dict[int, dict] | None = None,
    user_id: int | None = None,
) -> dict:
    """Receive a purchase order: create Items from serials, update status."""
    purchase = db.get(PurchaseOrder, purchase_id)
    if purchase is None:
        raise BusinessError("Purchase order not found", 404)
    if purchase.status == "received":
        raise BusinessError("Purchase already received", 409)

    created_items = []
    warnings = []

    for line in purchase.lines:
        product = db.get(Product, line.product_id)
        if product is None:
            warnings.append(f"Product {line.product_id} not found for line {line.id}")
            continue

        serials = serials_by_line.get(line.id, []) if serials_by_line else []
        warranty = warranty_by_line.get(line.id, {}) if warranty_by_line else {}

        if product.is_serialized:
            if len(serials) < line.quantity:
                # NOTE (flagging, not silently changing): when fewer serials
                # are supplied than the line quantity, this fills the gap
                # with fake "AUTO-..." placeholder serials instead of
                # rejecting the receive. That keeps the "Zero-Error" POS
                # flow unblocked, but it also means a cashier who forgot to
                # scan barcodes ends up with real inventory Items that
                # *look* serialized but aren't traceable to an actual
                # device — no warranty lookups or serial search will ever
                # find the physical unit. This is a genuine product/business
                # decision (block the receive vs. auto-fill placeholders),
                # not something I've changed here. Made the warning more
                # visible so it can't be missed/ignored by the frontend.
                warnings.append(
                    f"⚠️ MISSING SERIALS — {product.brand} {product.model}: expected "
                    f"{line.quantity}, got {len(serials)}. {line.quantity - len(serials)} "
                    "item(s) will get an AUTO-generated placeholder serial and will NOT "
                    "be traceable to a real device."
                )
            while len(serials) < line.quantity:
                serials.append(f"AUTO-{purchase.number}-{len(serials) + 1}")
        else:
            # Bulk product — create items without serials
            serials = [None] * line.quantity

        for serial in serials[:line.quantity]:
            item = Item(
                product_id=product.id,
                serial_number=serial.strip() if serial else None,
                status=ItemStatus.IN_STOCK,
                purchase_cost=line.unit_cost,
                purchase_date=date.today(),
                warranty_months=warranty.get("months", product.warranty_months),
                warranty_terms=warranty.get("terms", product.warranty_terms),
            )
            db.add(item)
            db.flush()
            created_items.append(item)

            db.add(StockMovement(
                item_id=item.id,
                movement_type=MovementType.PURCHASE,
                ref_type="purchase",
                ref_id=purchase.id,
                # FIX: the function already receives `user_id` as a
                # parameter but hardcoded `user_id=None` here, so no
                # purchase receipt was ever attributed to the staff member
                # who did it — same audit-trail gap as create_item above.
                user_id=user_id,
                notes=f"Purchase {purchase.number}: received {product.brand} {product.model}",
            ))

    purchase.status = "received"
    db.commit()

    return {
        "items": created_items,
        "warnings": warnings,
    }


def transfer_item(db: Session, item_id: int, *, to_location_id: int, user_id: int | None = None) -> Item:
    item = db.get(Item, item_id)
    if item is None:
        raise BusinessError("Item not found", 404)
    if item.status not in (ItemStatus.IN_STOCK, ItemStatus.RESERVED):
        raise BusinessError(f"Cannot transfer item in status '{item.status}'", 409)

    from_loc_id = item.location_id
    item.location_id = to_location_id
    db.add(StockMovement(
        item_id=item.id,
        movement_type=MovementType.TRANSFER,
        from_location_id=from_loc_id,
        to_location_id=to_location_id,
        user_id=user_id,
        notes=f"Transferred from location {from_loc_id} to {to_location_id}",
    ))
    db.commit()
    db.refresh(item)
    return item


def scrap_item(db: Session, item_id: int, *, reason: str, user_id: int | None = None) -> Item:
    item = db.get(Item, item_id)
    if item is None:
        raise BusinessError("Item not found", 404)
    if item.status == ItemStatus.SCRAPPED:
        raise BusinessError("Item already scrapped", 409)

    item.status = ItemStatus.SCRAPPED
    item.notes = (item.notes or "") + f"\nScrapped: {reason}"
    db.add(StockMovement(
        item_id=item.id,
        movement_type=MovementType.SCRAP,
        ref_type="scrap",
        ref_id=None,
        user_id=user_id,
        notes=f"Scrapped: {reason}",
    ))
    db.commit()
    db.refresh(item)
    return item
