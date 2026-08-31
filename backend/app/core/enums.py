"""Shared enums used across models and services."""
from __future__ import annotations

import enum


class DocType(str, enum.Enum):
    INVOICE = "invoice"
    QUOTE = "quote"
    PAYMENT = "payment"
    SALES_RETURN = "sales_return"
    REPAIR = "repair"
    PURCHASE = "purchase"


class ItemStatus(str, enum.Enum):
    IN_STOCK = "in_stock"
    RESERVED = "reserved"
    SOLD = "sold"
    IN_REPAIR = "in_repair"
    SCRAPPED = "scrapped"


class InvoiceStatus(str, enum.Enum):
    DRAFT = "draft"
    ISSUED = "issued"
    PARTIAL = "partial"
    PAID = "paid"
    CANCELLED = "cancelled"


class RepairStatus(str, enum.Enum):
    RECEIVED = "received"
    SENT_OUT = "sent_out"
    WITH_TECHNICIAN = "with_technician"
    RETURNED = "returned"
    DELIVERED = "delivered"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class MovementType(str, enum.Enum):
    PURCHASE = "purchase"
    SALE = "sale"
    SALE_RETURN = "sale_return"
    REPAIR_IN = "repair_in"
    REPAIR_OUT = "repair_out"
    TRANSFER = "transfer"
    SCRAP = "scrap"


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    CASHIER = "cashier"
    TECHNICIAN = "technician"


class PaymentMethod(str, enum.Enum):
    CASH = "cash"
    CARD = "card"
    WALLET = "wallet"          # Vodafone Cash / e-wallets
    INSTAPAY = "instapay"
    TRANSFER = "transfer"


class LocationKind(str, enum.Enum):
    SHOWROOM = "showroom"
    WAREHOUSE = "warehouse"
    REPAIR_BENCH = "repair_bench"
