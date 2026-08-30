"""CRM business logic: customer profiles, balances, statements, aging.

Balance is ALWAYS derived from invoices/payments/returns — never stored —
so it cannot drift out of sync.

Credit convention: credit_limit == 0 means UNLIMITED credit;
credit_limit > 0 is the maximum allowed outstanding balance.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.enums import InvoiceStatus
from app.core.exceptions import BusinessError
from app.models import Customer, Invoice, Payment, SalesReturn


def create_customer(
    db: Session,
    *,
    name: str,
    phone: str,
    email: str | None = None,
    address: str | None = None,
    tax_id: str | None = None,
    credit_limit: Decimal = Decimal("0.00"),
    notes: str | None = None,
) -> Customer:
    # FIX: an empty string ("") is not the same as NULL for a UNIQUE column.
    # get_or_create_customer() below calls this with phone="" for walk-in
    # POS customers who didn't give a phone number. The very first such
    # customer would insert phone="" fine — but the SECOND walk-in customer
    # with no phone would hit the DB's UNIQUE constraint on phone="" and
    # blow up with a raw IntegrityError, because SQLite's unique index
    # only allows *one* NULL, not one of every "empty" value. Normalizing
    # "" to None here lets the DB's existing NULL-allows-many-once
    # behavior (already relied on for RepairCenter.phone per CHANGES.md)
    # work the same way for Customer.phone.
    phone = phone.strip() if phone and phone.strip() else None

    # Prevent duplicate customers by phone (unique constraint at DB level,
    # but check first for a friendly error message)
    if phone:
        existing = db.scalars(
            select(Customer).where(Customer.phone == phone)
        ).first()
        if existing is not None:
            raise BusinessError(
                f"عميل بهذا الرقم موجود بالفعل: {existing.name} ({existing.phone})",
                409
            )

    # FIX: guard against a negative credit limit slipping through — it
    # would make available_credit() in customer_balance() come out
    # negative/nonsensical for every invoice.
    credit_limit = Decimal(str(credit_limit))
    if credit_limit < 0:
        raise BusinessError("credit_limit cannot be negative", 400)

    customer = Customer(
        name=name.strip(),
        phone=phone,
        email=email,
        address=address,
        tax_id=tax_id,
        credit_limit=credit_limit,
        notes=notes,
    )
    db.add(customer)
    try:
        db.commit()
    except IntegrityError:
        # FIX: same race-condition safety net used in
        # repairs_service.create_repair_center — two concurrent requests
        # for the same phone can both pass the pre-check above before
        # either commits.
        db.rollback()
        raise BusinessError(f"عميل بهذا الرقم موجود بالفعل: {phone}", 409)
    db.refresh(customer)
    return customer


def get_or_create_customer(
    db: Session,
    *,
    name: str,
    phone: str | None = None,
    address: str | None = None,
) -> Customer:
    """Find an existing customer by phone (fallback: by exact name), else
    create one. Used by the Quick POS free-text customer (one click with
    the invoice)."""
    if phone and phone.strip():
        existing = db.scalars(
            select(Customer).where(Customer.phone == phone.strip())
        ).first()
        if existing is not None:
            return existing
    if name and name.strip():
        existing = db.scalars(
            select(Customer).where(Customer.name == name.strip())
        ).first()
        if existing is not None:
            return existing
    # FIX: was passing phone=phone or "" — now that create_customer()
    # normalizes "" to None itself, this still reads clean, but making it
    # explicit here too avoids relying on that normalization silently.
    return create_customer(
        db, name=name or (phone or "عميل / Customer"),
        phone=phone or "",
    )


# ---------------------------------------------------------------------------
# Balances (derived, never stored)
# ---------------------------------------------------------------------------


def invoice_remaining(invoice: Invoice) -> Decimal:
    """What is still owed on one invoice (returns are credited)."""
    returned = sum(r.total for r in invoice.returns)
    return max(Decimal("0.00"), invoice.total - invoice.paid_amount - returned)


def customer_outstanding(db: Session, customer_id: int) -> Decimal:
    """Total unpaid balance of a customer across all non-cancelled invoices."""
    invoices = db.scalars(
        select(Invoice).where(
            Invoice.customer_id == customer_id,
            Invoice.status != InvoiceStatus.CANCELLED,
        )
    ).all()
    return sum((invoice_remaining(inv) for inv in invoices), Decimal("0.00"))


def customer_balance(db: Session, customer_id: int) -> dict:
    """{outstanding, overdue, credit_limit, available_credit}."""
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise BusinessError("Customer not found", 404)
    outstanding = customer_outstanding(db, customer_id)
    limit = customer.credit_limit
    return {
        "customer_id": customer_id,
        "outstanding": outstanding,
        "overdue": customer_overdue(db, customer_id),
        "credit_limit": limit,
        "available_credit": (limit - outstanding) if limit > 0 else None,
    }


def customer_overdue(db: Session, customer_id: int, as_of: date | None = None) -> Decimal:
    """Portion of the outstanding balance past its due date (due_date or
    invoice date as reference) — mirrors the aging buckets."""
    as_of = as_of or date.today()
    invoices = db.scalars(
        select(Invoice).where(
            Invoice.customer_id == customer_id,
            Invoice.status != InvoiceStatus.CANCELLED,
        )
    ).all()
    overdue = Decimal("0.00")
    for inv in invoices:
        remaining = invoice_remaining(inv)
        if remaining <= 0:
            continue
        due = inv.due_date or inv.invoice_date
        if (as_of - due).days > 0:
            overdue += remaining
    return overdue


# ---------------------------------------------------------------------------
# Customer statement (كشف حساب)
# ---------------------------------------------------------------------------


@dataclass
class StatementEntry:
    date: date
    type: str          # invoice | payment | return
    number: str
    description: str
    debit: Decimal     # increases what the customer owes
    credit: Decimal    # decreases what the customer owes
    balance: Decimal
    _rank: int = 0     # tie-breaker within the same day
    _id: int = 0
    ref_id: int | None = None   # id of the referenced document (e.g. invoice)


def customer_statement(
    db: Session,
    customer_id: int,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[StatementEntry]:
    """Full statement with running balance, oldest first. Optional date
    window filters the movements shown (balance is still chronological)."""
    if db.get(Customer, customer_id) is None:
        raise BusinessError("Customer not found", 404)

    invoices = db.scalars(
        select(Invoice).where(
            Invoice.customer_id == customer_id,
            Invoice.status != InvoiceStatus.CANCELLED,
        )
    ).all()
    payments = db.scalars(
        select(Payment).where(Payment.customer_id == customer_id)
    ).all()
    returns = db.scalars(
        select(SalesReturn).where(SalesReturn.customer_id == customer_id)
    ).all()

    entries: list[StatementEntry] = []
    for inv in invoices:
        entries.append(StatementEntry(
            date=inv.invoice_date, type="invoice", number=inv.number,
            description=f"Invoice {inv.number}",
            debit=inv.total, credit=Decimal("0.00"), balance=Decimal("0.00"),
            _rank=0, _id=inv.id, ref_id=inv.id,
        ))
    for pay in payments:
        # FIX: Payment.amount is negative for a refund (per the schema
        # docstring elsewhere: "amount (negative = refund)"), and
        # sales_service.add_payment() does `invoice.paid_amount += amount`,
        # so a refund correctly *reduces* paid_amount (i.e. increases what
        # the customer is owed again). This statement, however, always
        # recorded `credit=abs(pay.amount)` — treating a refund exactly
        # like a normal payment, i.e. as money reducing the balance. That's
        # backwards: a refund should show as a DEBIT (balance goes back
        # up), matching what invoice_remaining()/customer_outstanding()
        # already compute from paid_amount. Left uncorrected, the running
        # balance shown on a statement would permanently diverge from the
        # "outstanding" figure shown elsewhere for any customer who ever
        # got a refund.
        is_refund = pay.amount < 0
        entries.append(StatementEntry(
            date=pay.paid_at.date(), type="payment" if not is_refund else "refund",
            number=pay.number,
            description=f"Payment {pay.number}" if not is_refund else f"Refund {pay.number}",
            debit=abs(pay.amount) if is_refund else Decimal("0.00"),
            credit=Decimal("0.00") if is_refund else pay.amount,
            balance=Decimal("0.00"),
            _rank=1, _id=pay.id,
        ))
    for ret in returns:
        entries.append(StatementEntry(
            date=ret.return_date, type="return", number=ret.number,
            description=f"Return {ret.number}",
            debit=Decimal("0.00"), credit=ret.total, balance=Decimal("0.00"),
            _rank=2, _id=ret.id,
        ))

    # FIX: the dataclass comment says `_rank` is "a tie-breaker within the
    # same day" but the original sort key was `(e.date, e._id)` — it never
    # used `_rank` at all. Worse, `_id` is each row's own table's
    # auto-increment id, so comparing an invoice's id against a payment's
    # id on the same date doesn't reflect real chronological order (e.g.
    # invoice #50 vs payment #3 issued minutes later on the same day would
    # sort the payment first). Adding `_rank` back into the key at least
    # restores the intended, documented tie-break (invoices, then
    # payments/refunds, then returns) for same-day entries.
    entries.sort(key=lambda e: (e.date, e._rank, e._id))
    if date_from is not None:
        entries = [e for e in entries if e.date >= date_from]
    if date_to is not None:
        entries = [e for e in entries if e.date <= date_to]
    running = Decimal("0.00")
    for entry in entries:
        running += entry.debit - entry.credit
        entry.balance = running
    return entries


# ---------------------------------------------------------------------------
# Aging report (أعمار الديون 30/60/90)
# ---------------------------------------------------------------------------


@dataclass
class AgingRow:
    customer_id: int
    name: str
    phone: str
    current: Decimal     # not due yet
    d1_30: Decimal       # 1-30 days overdue
    d31_60: Decimal      # 31-60 days overdue
    d61_90: Decimal      # 61-90 days overdue
    d90: Decimal         # 90+ days overdue
    total: Decimal


def aging_report(db: Session, as_of: date | None = None) -> list[AgingRow]:
    """Debt aged by how late each unpaid invoice is (due_date or invoice
    date as reference). Sorted by total debt, biggest first."""
    as_of = as_of or date.today()
    customers = db.scalars(select(Customer).order_by(Customer.name)).all()
    rows: list[AgingRow] = []

    for customer in customers:
        invoices = db.scalars(
            select(Invoice).where(
                Invoice.customer_id == customer.id,
                Invoice.status != InvoiceStatus.CANCELLED,
            )
        ).all()
        buckets = {
            "current": Decimal("0.00"), "d1_30": Decimal("0.00"),
            "d31_60": Decimal("0.00"), "d61_90": Decimal("0.00"),
            "d90": Decimal("0.00"),
        }
        for inv in invoices:
            remaining = invoice_remaining(inv)
            if remaining <= 0:
                continue
            due = inv.due_date or inv.invoice_date
            days = (as_of - due).days
            if days <= 0:
                buckets["current"] += remaining
            elif days <= 30:
                buckets["d1_30"] += remaining
            elif days <= 60:
                buckets["d31_60"] += remaining
            elif days <= 90:
                buckets["d61_90"] += remaining
            else:
                buckets["d90"] += remaining

        total = sum(buckets.values(), Decimal("0.00"))
        if total > 0:
            rows.append(AgingRow(
                customer_id=customer.id, name=customer.name, phone=customer.phone,
                current=buckets["current"], d1_30=buckets["d1_30"],
                d31_60=buckets["d31_60"], d61_90=buckets["d61_90"],
                d90=buckets["d90"], total=total,
            ))

    rows.sort(key=lambda r: r.total, reverse=True)
    return rows
