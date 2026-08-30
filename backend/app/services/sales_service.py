"""Sales business logic: invoices, line items (with customization bundles),
payments, sales returns / credit notes.

Saving an invoice creates the PO AND receives it immediately, so the
stock quantities grow automatically (one click, POS style).

Zero-Error rules: empty/missing suppliers or products NEVER stop the
page — the supplier field accepts free text and auto-creates a new
supplier with the invoice (one click).
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.enums import DocType, ItemStatus, InvoiceStatus, MovementType, PaymentMethod
from app.core.exceptions import BusinessError
from app.core.numbering import next_number
# FIX: SalesReturnLine was used in create_return() below but never imported
# — this was a guaranteed NameError (500) the first time anyone tried to
# process a return.
from app.models import Customer, Invoice, InvoiceLine, Item, Payment, SalesReturn, SalesReturnLine, StockMovement

settings = get_settings()


def _snap_unit_cost(db: Session, item: Item) -> Decimal:
    """Snapshot the unit cost at sale time (for profit math)."""
    return item.purchase_cost


def _snap_unit_price(db: Session, item: Item) -> Decimal:
    """Snapshot the unit price at sale time (for profit math)."""
    return item.product.default_price if item.product else Decimal("0.00")


def _validate_line(db: Session, line: dict) -> tuple[Item | None, Decimal, Decimal]:
    """Validate a single invoice line, returning (item, unit_price, unit_cost)."""
    item_uuid = line.get("item_uuid")
    description = line.get("description", "").strip()
    quantity = int(line.get("quantity", 1))
    unit_price = Decimal(str(line.get("unit_price", 0)))
    discount = Decimal(str(line.get("discount", 0)))

    # FIX: quantity/discount were never validated. A quantity <= 0 or a
    # discount bigger than the line's own value could silently push
    # line_total negative and quietly reduce the invoice total.
    if quantity <= 0:
        raise BusinessError("Line quantity must be > 0", 400)
    if discount < 0:
        raise BusinessError("Line discount cannot be negative", 400)

    if item_uuid:
        # NOTE (concurrency, not fixed here): two concurrent invoices can
        # both read this item as IN_STOCK before either commits, and both
        # would pass this check — a classic check-then-act race. SQLite
        # does not support real row-level locking (`with_for_update()` is
        # effectively a no-op on SQLite), so the robust fix is an atomic
        # conditional UPDATE (`UPDATE items SET status='SOLD' WHERE id=...
        # AND status='IN_STOCK'`, checking rows-affected == 1) rather than
        # a SELECT-then-UPDATE. Flagging rather than silently "fixing" this
        # with code that wouldn't actually close the race on SQLite.
        item = db.scalar(select(Item).where(Item.uuid == item_uuid.strip().lower()))
        if item is None:
            raise BusinessError(f"Unit with barcode '{item_uuid}' not found", 404)
        if item.status != ItemStatus.IN_STOCK:
            raise BusinessError(
                f"Unit {item.serial_number or item.uuid} is not in stock "
                f"(current: {item.status.value})",
                409,
            )
        unit_cost = _snap_unit_cost(db, item)
        # Use product default price if line price is 0
        if unit_price == 0:
            unit_price = _snap_unit_price(db, item)
        if discount > unit_price * quantity:
            raise BusinessError("Line discount cannot exceed the line's value", 400)
        return item, unit_price, unit_cost
    else:
        # Service line (no physical item)
        if not description:
            raise BusinessError("Service line must have a description", 400)
        if unit_price <= 0:
            raise BusinessError("Service line must have a price > 0", 400)
        if discount > unit_price * quantity:
            raise BusinessError("Line discount cannot exceed the line's value", 400)
        return None, unit_price, Decimal("0.00")


def create_invoice(
    db: Session,
    *,
    customer_id: int,
    lines: list[dict],
    notes: str | None = None,
    payments: list[dict] | None = None,
    user_id: int | None = None,
    # FIX: added so callers that need this invoice to be part of a larger
    # atomic transaction (e.g. repairs_service.deliver_repair, which also
    # updates the RepairOrder in the same logical operation) can pass
    # autocommit=False and commit everything themselves in one go. Default
    # stays True so every other existing caller keeps working unchanged.
    autocommit: bool = True,
) -> Invoice:
    """Create a sales invoice with lines (items or services), optional payments."""
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise BusinessError("Customer not found", 404)

    invoice = Invoice(
        number=next_number(db, DocType.INVOICE, settings.invoice_prefix),
        customer_id=customer_id,
        invoice_date=date.today(),
        status=InvoiceStatus.DRAFT,
        notes=notes,
        user_id=user_id,
    )
    db.add(invoice)
    db.flush()

    # FIX: the original code summed line.line_total (already net of each
    # line's discount) into `subtotal`, then did
    # `invoice.total = subtotal - total_discount`
    # — subtracting the discount a SECOND time. That double-discounted
    # every invoice (e.g. a 100 EGP item with a 10 EGP discount was billed
    # as 100 - 10 - 10 = 80, not 90). Now tracking the pre-discount gross
    # separately from the discount, so the math only applies once.
    gross_subtotal = Decimal("0.00")
    total_discount = Decimal("0.00")
    net_subtotal = Decimal("0.00")

    for line_data in lines:
        item, unit_price, unit_cost = _validate_line(db, line_data)
        quantity = int(line_data.get("quantity", 1))
        discount = Decimal(str(line_data.get("discount", 0)))

        line = InvoiceLine(
            invoice_id=invoice.id,
            item_id=item.id if item else None,
            product_id=item.product_id if item else None,
            description=line_data.get("description", "").strip(),
            quantity=quantity,
            unit_price=unit_price,
            unit_cost=unit_cost,
            discount=discount,
            line_total=(unit_price * quantity) - discount,
        )
        db.add(line)
        gross_subtotal += unit_price * quantity
        total_discount += discount
        net_subtotal += line.line_total

    invoice.subtotal = net_subtotal
    invoice.discount = total_discount
    invoice.shipping_cost = Decimal("0.00")
    # FIX (VAT): tax was hardcoded to 0.00 while the POS frontend displays a
    # 14% VAT on the invoice total and records the payment amount INCLUSIVE
    # of that tax. The backend was therefore storing the pre-tax subtotal as
    # the invoice total while the customer actually paid the tax-inclusive
    # amount — the recorded total no longer matched the money received, so a
    # fully-paid POS sale left a phantom credit on the customer's balance
    # (outstanding drift). Apply the configured VAT rate so the stored total
    # equals the subtotal + VAT, i.e. exactly what the POS shows and collects.
    tax_rate = Decimal(str(settings.default_tax_rate)).quantize(Decimal("0.0001"))
    invoice.tax_rate = tax_rate
    invoice.tax_amount = (net_subtotal * tax_rate).quantize(Decimal("0.01"))
    invoice.total = net_subtotal + invoice.tax_amount
    invoice.paid_amount = Decimal("0.00")
    invoice.status = InvoiceStatus.ISSUED

    # Process payments if provided
    if payments:
        for pay in payments:
            amount = Decimal(str(pay.get("amount", 0)))
            if amount <= 0:
                continue
            payment = Payment(
                number=next_number(db, DocType.PAYMENT, settings.payment_prefix),
                invoice_id=invoice.id,
                customer_id=customer_id,
                amount=amount,
                paid_at=datetime.now(),
                method=PaymentMethod(pay.get("method", "cash")),
                reference=pay.get("reference"),
                notes=pay.get("notes"),
                user_id=user_id,
            )
            db.add(payment)
            invoice.paid_amount += amount

    # Update status based on payments
    if invoice.paid_amount >= invoice.total:
        invoice.status = InvoiceStatus.PAID
    elif invoice.paid_amount > 0:
        invoice.status = InvoiceStatus.PARTIAL

    # Update item statuses and create stock movements
    for line in invoice.lines:
        if line.item_id:
            item = db.get(Item, line.item_id)
            item.status = ItemStatus.SOLD
            db.add(StockMovement(
                item_id=item.id,
                movement_type=MovementType.SALE,
                ref_type="invoice",
                ref_id=invoice.id,
                user_id=line.invoice.user_id,
                notes=f"Invoice {invoice.number}: sold to {line.invoice.customer.name if line.invoice.customer else 'customer'}",
            ))

    if autocommit:
        db.commit()
        db.refresh(invoice)
    else:
        db.flush()
    return invoice


def cancel_invoice(db: Session, invoice_id: int, *, reason: str, user_id: int | None = None) -> Invoice:
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise BusinessError("Invoice not found", 404)
    if invoice.status == InvoiceStatus.CANCELLED:
        raise BusinessError("Invoice already cancelled", 409)

    # NOTE (not fixed here — needs a product decision): if invoice.paid_amount
    # > 0, cancelling leaves that money recorded as paid against a now-
    # cancelled invoice with no refund created automatically. Depending on
    # how customer_balance()/statements sum things up elsewhere, this can
    # either strand a credit or hide it. Worth checking crm_service.py's
    # balance calculation, or requiring reason/refund handling before
    # allowing cancellation of an invoice with payments.

    # Restore items to IN_STOCK
    for line in invoice.lines:
        if line.item_id:
            item = db.get(Item, line.item_id)
            item.status = ItemStatus.IN_STOCK
            db.add(StockMovement(
                item_id=item.id,
                movement_type=MovementType.SALE_RETURN,
                ref_type="invoice",
                ref_id=invoice.id,
                user_id=user_id,
                notes=f"Invoice {invoice.number} cancelled: {reason}",
            ))

    invoice.status = InvoiceStatus.CANCELLED
    invoice.notes = (invoice.notes or "") + f"\nCancelled: {reason}"
    db.commit()
    db.refresh(invoice)
    return invoice


def add_payment(
    db: Session,
    invoice_id: int,
    *,
    amount: Decimal,
    method: PaymentMethod = PaymentMethod.CASH,
    reference: str | None = None,
    notes: str | None = None,
    user_id: int | None = None,
) -> Payment:
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise BusinessError("Invoice not found", 404)
    if invoice.status == InvoiceStatus.CANCELLED:
        raise BusinessError("Cannot add payment to cancelled invoice", 409)

    amount = Decimal(str(amount))
    if amount <= 0:
        raise BusinessError("Payment amount must be > 0", 400)

    payment = Payment(
        number=next_number(db, DocType.PAYMENT, settings.payment_prefix),
        invoice_id=invoice.id,
        customer_id=invoice.customer_id,
        amount=amount,
        paid_at=datetime.now(),
        method=method,
        reference=reference,
        notes=notes,
        user_id=user_id,
    )
    db.add(payment)
    invoice.paid_amount += amount

    if invoice.paid_amount >= invoice.total:
        invoice.status = InvoiceStatus.PAID
    elif invoice.paid_amount > 0:
        invoice.status = InvoiceStatus.PARTIAL

    db.commit()
    db.refresh(invoice)
    return payment


def create_return(
    db: Session,
    *,
    invoice_id: int,
    lines: list[dict],
    reason: str | None = None,
    user_id: int | None = None,
) -> SalesReturn:
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise BusinessError("Invoice not found", 404)
    if invoice.status == InvoiceStatus.CANCELLED:
        raise BusinessError("Cannot return from cancelled invoice", 409)

    # FIX: build the set of item_ids that actually belong to this invoice.
    # The original code accepted ANY item_id the caller sent and happily
    # returned it to stock — a client could return an item that was never
    # sold on this invoice at all (wrong invoice number, typo, or a
    # malicious/buggy request), corrupting stock and the invoice's balance.
    invoice_item_ids = {l.item_id for l in invoice.lines if l.item_id}

    ret = SalesReturn(
        number=next_number(db, DocType.SALES_RETURN, settings.return_prefix),
        invoice_id=invoice_id,
        customer_id=invoice.customer_id,
        return_date=date.today(),
        reason=reason,
        user_id=user_id,
    )
    db.add(ret)
    db.flush()

    total = Decimal("0.00")
    for line_data in lines:
        item_id = line_data.get("item_id")
        quantity = int(line_data.get("quantity", 1))
        refund_amount = Decimal(str(line_data.get("refund_amount", 0)))

        # FIX: the original code silently `continue`d past invalid lines
        # instead of telling the caller anything was wrong — a request with
        # a typo'd item_id would return a SalesReturn with fewer lines than
        # the user thought they were returning, with no error. Now this
        # raises so the caller (and the person on the POS screen) actually
        # finds out.
        if not item_id:
            raise BusinessError("Each return line needs an item_id", 400)
        if quantity <= 0:
            raise BusinessError("Return quantity must be > 0", 400)
        if refund_amount <= 0:
            raise BusinessError("Return refund_amount must be > 0", 400)
        if item_id not in invoice_item_ids:
            raise BusinessError(
                f"Item {item_id} was not sold on invoice {invoice.number}", 400
            )

        item = db.get(Item, item_id)
        if item is None:
            raise BusinessError(f"Item {item_id} not found", 404)

        ret_line = SalesReturnLine(
            sale_return_id=ret.id,
            item_id=item_id,
            quantity=quantity,
            refund_amount=refund_amount,
        )
        db.add(ret_line)
        total += refund_amount

        # Restore item to IN_STOCK
        item.status = ItemStatus.IN_STOCK
        db.add(StockMovement(
            item_id=item.id,
            movement_type=MovementType.SALE_RETURN,
            ref_type="return",
            ref_id=ret.id,
            user_id=user_id,
            notes=f"Return {ret.number}: item returned to stock",
        ))

    ret.total = total
    db.commit()
    db.refresh(ret)
    return ret


def invoice_remaining(invoice: Invoice) -> Decimal:
    """What is still owed on one invoice (returns are credited)."""
    returned = sum(r.total for r in invoice.returns)
    return max(Decimal("0.00"), invoice.total - invoice.paid_amount - returned)
