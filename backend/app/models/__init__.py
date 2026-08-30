"""SQLAlchemy models for ERP System.

Scope note: this covers exactly what repairs_service.py, sales_service.py,
crm_service.py, and inventory_service.py reference (verified against those
four files). Modules mentioned in SPEC.md but not yet touched by any
service we've built/fixed (WhatsApp bot tables, AI assistant tool-call
logs, Treasury, License/AuditLog, Snippets) are intentionally left out —
add them when we build the service layer that needs them, rather than
guessing their shape now.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _uuid() -> str:
    return uuid_lib.uuid4().hex


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    full_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(20))  # UserRole
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


# ---------------------------------------------------------------------------
# Locations / Suppliers / Categories / Products
# ---------------------------------------------------------------------------

class Location(Base):
    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(20), default="warehouse")  # LocationKind
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    email: Mapped[str | None] = mapped_column(String(120), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), nullable=True)


class Product(Base):
    """A catalog entry (model/spec). Physical units are `Item` rows."""
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    brand: Mapped[str] = mapped_column(String(80))
    model: Mapped[str] = mapped_column(String(120))
    is_serialized: Mapped[bool] = mapped_column(Boolean, default=True)
    default_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    warranty_months: Mapped[int] = mapped_column(Integer, default=0)
    warranty_terms: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    items: Mapped[list["Item"]] = relationship(back_populates="product")


# ---------------------------------------------------------------------------
# Items (physical units) & stock movements
# ---------------------------------------------------------------------------

class Item(Base):
    """One physical unit — the core of the inventory system. `uuid` is the
    stable unique identifier (barcode-scannable); `serial_number` is
    informational and, per the historical migration note carried over from
    CHANGES.md, intentionally NOT unique (units can be re-received/re-sold
    with a serial that was already recorded on an older, since-scrapped
    unit)."""
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uuid: Mapped[str] = mapped_column(String(32), unique=True, default=_uuid)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    serial_number: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="in_stock")  # ItemStatus
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"), nullable=True)
    purchase_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    purchase_date: Mapped[date] = mapped_column(Date, default=date.today)
    warranty_months: Mapped[int] = mapped_column(Integer, default=0)
    warranty_terms: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    product: Mapped["Product"] = relationship(back_populates="items")


class StockMovement(Base):
    """Immutable ledger of every state change an Item goes through."""
    __tablename__ = "stock_movements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"))
    movement_type: Mapped[str] = mapped_column(String(20))  # MovementType
    ref_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    ref_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    from_location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    to_location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


# ---------------------------------------------------------------------------
# Purchasing
# ---------------------------------------------------------------------------

class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    number: Mapped[str] = mapped_column(String(40), unique=True)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft/received/cancelled
    order_date: Mapped[date] = mapped_column(Date, default=date.today)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    lines: Mapped[list["PurchaseOrderLine"]] = relationship(back_populates="purchase")


class PurchaseOrderLine(Base):
    __tablename__ = "purchase_order_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    purchase_id: Mapped[int] = mapped_column(ForeignKey("purchase_orders.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))

    purchase: Mapped["PurchaseOrder"] = relationship(back_populates="lines")


# ---------------------------------------------------------------------------
# CRM — customers
# ---------------------------------------------------------------------------

class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (UniqueConstraint("phone", name="uq_customers_phone"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    # FIX carried over from the crm_service.py review: phone must be
    # nullable so multiple no-phone walk-in customers don't collide on a
    # shared "" value under the UNIQUE constraint (SQLite allows many NULLs,
    # not many empty strings).
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    email: Mapped[str | None] = mapped_column(String(120), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    tax_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    credit_limit: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


# ---------------------------------------------------------------------------
# Sales — invoices, lines, payments, returns
# ---------------------------------------------------------------------------

class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    number: Mapped[str] = mapped_column(String(40), unique=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    invoice_date: Mapped[date] = mapped_column(Date, default=date.today)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # InvoiceStatus
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    discount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    shipping_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("0.00"))
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    customer: Mapped["Customer"] = relationship()
    lines: Mapped[list["InvoiceLine"]] = relationship(back_populates="invoice")
    returns: Mapped[list["SalesReturn"]] = relationship(back_populates="invoice")


class InvoiceLine(Base):
    __tablename__ = "invoice_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"))
    item_id: Mapped[int | None] = mapped_column(ForeignKey("items.id"), nullable=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    description: Mapped[str] = mapped_column(Text)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    discount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    line_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))

    invoice: Mapped["Invoice"] = relationship(back_populates="lines")


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    number: Mapped[str] = mapped_column(String(40), unique=True)
    invoice_id: Mapped[int | None] = mapped_column(ForeignKey("invoices.id"), nullable=True)
    purchase_id: Mapped[int | None] = mapped_column(ForeignKey("purchase_orders.id"), nullable=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"), nullable=True)
    # Positive = payment received; negative = refund. See crm_service.py's
    # customer_statement() for how the sign is interpreted.
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    paid_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    method: Mapped[str] = mapped_column(String(20), default="cash")  # PaymentMethod
    reference: Mapped[str | None] = mapped_column(String(80), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    # NOTE: polymorphic-FK gap flagged in the earlier architecture review
    # (§ "Payment model — polymorphic FK bez enforcement") — this scaffold
    # still doesn't enforce "exactly one of invoice/purchase/customer/
    # supplier is set" at the DB level. Add a CHECK constraint once the
    # exact allowed combinations are decided (e.g. can a payment be linked
    # to both a customer AND their invoice at once, or must it be either/or?).


class SalesReturn(Base):
    __tablename__ = "sales_returns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    number: Mapped[str] = mapped_column(String(40), unique=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"))
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    return_date: Mapped[date] = mapped_column(Date, default=date.today)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    invoice: Mapped["Invoice"] = relationship(back_populates="returns")
    lines: Mapped[list["SalesReturnLine"]] = relationship(back_populates="sales_return")


class SalesReturnLine(Base):
    __tablename__ = "sales_return_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sale_return_id: Mapped[int] = mapped_column(ForeignKey("sales_returns.id"))
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    refund_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))

    sales_return: Mapped["SalesReturn"] = relationship(back_populates="lines")


# ---------------------------------------------------------------------------
# Repairs
# ---------------------------------------------------------------------------

class RepairCenter(Base):
    __tablename__ = "repair_centers"
    __table_args__ = (UniqueConstraint("phone", name="uq_repair_centers_phone"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    email: Mapped[str | None] = mapped_column(String(120), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class RepairOrder(Base):
    __tablename__ = "repair_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    number: Mapped[str] = mapped_column(String(40), unique=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    item_id: Mapped[int | None] = mapped_column(ForeignKey("items.id"), nullable=True)
    device_description: Mapped[str] = mapped_column(Text)
    reported_issue: Mapped[str] = mapped_column(Text)
    condition_received: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="received")  # RepairStatus

    repair_center_id: Mapped[int | None] = mapped_column(ForeignKey("repair_centers.id"), nullable=True)
    external_tracking: Mapped[str | None] = mapped_column(String(80), nullable=True)
    expected_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    technician_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    handed_to_tech_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    received_from_tech_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    returned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    actual_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    repair_result: Mapped[str | None] = mapped_column(Text, nullable=True)

    invoice_id: Mapped[int | None] = mapped_column(ForeignKey("invoices.id"), nullable=True)
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    shop_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    customer: Mapped["Customer"] = relationship()
    item: Mapped["Item | None"] = relationship()
    center: Mapped["RepairCenter | None"] = relationship(foreign_keys=[repair_center_id])
    technician: Mapped["User | None"] = relationship(foreign_keys=[technician_id])
    invoice: Mapped["Invoice | None"] = relationship(foreign_keys=[invoice_id])


# ---------------------------------------------------------------------------
# Shop settings (singleton row)
# ---------------------------------------------------------------------------

class ShopSettings(Base):
    __tablename__ = "shop_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), default="متجر الإلكترونيات")
    tax_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    email: Mapped[str | None] = mapped_column(String(120), nullable=True)


# ---------------------------------------------------------------------------
# WhatsApp bot — message log
# ---------------------------------------------------------------------------

class WhatsAppMessage(Base):
    """Every inbound/outbound WhatsApp message, real or simulated. This is
    what makes the bot's behavior testable and debuggable before a real
    Meta WhatsApp Business API account exists — see
    services/whatsapp_client.py."""
    __tablename__ = "whatsapp_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    direction: Mapped[str] = mapped_column(String(10))  # "in" | "out"
    phone: Mapped[str] = mapped_column(String(32))
    message_type: Mapped[str] = mapped_column(String(20), default="text")  # text | image | ocr_result
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="simulated")  # simulated | sent | received | failed
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True)
    repair_id: Mapped[int | None] = mapped_column(ForeignKey("repair_orders.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


# ---------------------------------------------------------------------------
# Numbering
# ---------------------------------------------------------------------------

class DocumentSequence(Base):
    """One row per DocType, holding the last number issued."""
    __tablename__ = "document_sequences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    doc_type: Mapped[str] = mapped_column(String(20), unique=True)
    last_number: Mapped[int] = mapped_column(Integer, default=0)
