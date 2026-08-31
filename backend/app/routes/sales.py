from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_session
from app.models import Invoice, Item
from app.services import sales_service

router = APIRouter()


@router.get("/items/lookup")
def lookup_item(serial: str | None = None, uuid: str | None = None, db: Session = Depends(get_session)) -> dict | None:
    stmt = select(Item)
    if uuid:
        stmt = stmt.where(Item.uuid == uuid.strip().lower())
    elif serial:
        stmt = stmt.where(Item.serial_number == serial.strip())
    else:
        return None
    item = db.scalar(stmt)
    if item is None:
        return None
    return {
        "uuid": item.uuid,
        "serial_number": item.serial_number,
        "status": item.status,
        "product_name": f"{item.product.brand} {item.product.model}" if item.product else None,
        "default_price": str(item.product.default_price) if item.product else "0.00",
    }


class InvoiceLineBody(BaseModel):
    item_uuid: str | None = None
    description: str | None = None
    quantity: int = 1
    unit_price: str = "0"
    discount: str = "0"


class PaymentBody(BaseModel):
    amount: str
    method: str = "cash"
    reference: str | None = None


class CreateInvoiceBody(BaseModel):
    customer_id: int
    lines: list[InvoiceLineBody]
    notes: str | None = None
    payments: list[PaymentBody] | None = None
    user_id: int | None = None
    tax_rate: float | None = None


@router.post("/invoices")
def create_invoice(body: CreateInvoiceBody, db: Session = Depends(get_session)) -> dict:
    lines = [
        {
            "item_uuid": l.item_uuid, "description": l.description or "",
            "quantity": l.quantity, "unit_price": l.unit_price, "discount": l.discount,
        }
        for l in body.lines
    ]
    payments = None
    if body.payments:
        payments = [{"amount": p.amount, "method": p.method, "reference": p.reference} for p in body.payments]

    invoice = sales_service.create_invoice(
        db, customer_id=body.customer_id, lines=lines, notes=body.notes,
        payments=payments, user_id=body.user_id, tax_rate=body.tax_rate,
    )
    return {
        "id": invoice.id, "number": invoice.number, "status": invoice.status,
        "subtotal": str(invoice.subtotal), "discount": str(invoice.discount),
        "total": str(invoice.total), "paid_amount": str(invoice.paid_amount),
    }


@router.get("/invoices")
def list_invoices(db: Session = Depends(get_session)) -> list[dict]:
    # Quotes (DRAFT) are surfaced separately via GET /api/sales/quotes, so
    # keep this list to real (issued/paid/partial/cancelled) invoices only.
    invoices = db.scalars(
        select(Invoice)
        .where(Invoice.status != "draft")
        .order_by(Invoice.id.desc()).limit(50)
    ).all()
    return [
        {
            "id": inv.id, "number": inv.number, "status": inv.status,
            "total": str(inv.total), "customer": inv.customer.name if inv.customer else None,
            "invoice_date": inv.invoice_date.isoformat(),
        }
        for inv in invoices
    ]


class CreateQuoteBody(BaseModel):
    customer_id: int
    lines: list[InvoiceLineBody]
    notes: str | None = None
    user_id: int | None = None
    tax_rate: float | None = None


@router.post("/quotes")
def create_quote(body: CreateQuoteBody, db: Session = Depends(get_session)) -> dict:
    lines = [
        {
            "item_uuid": l.item_uuid, "description": l.description or "",
            "quantity": l.quantity, "unit_price": l.unit_price, "discount": l.discount,
        }
        for l in body.lines
    ]
    quote = sales_service.create_quote(
        db, customer_id=body.customer_id, lines=lines, notes=body.notes,
        user_id=body.user_id, tax_rate=body.tax_rate,
    )
    return {
        "id": quote.id, "number": quote.number, "status": quote.status,
        "subtotal": str(quote.subtotal), "discount": str(quote.discount),
        "total": str(quote.total), "tax_amount": str(quote.tax_amount),
    }


class ConvertBody(BaseModel):
    payments: list[PaymentBody] | None = None
    user_id: int | None = None
    tax_rate: float | None = None


@router.post("/invoices/{invoice_id}/convert")
def convert_quote(invoice_id: int, body: ConvertBody, db: Session = Depends(get_session)) -> dict:
    payments = None
    if body.payments:
        payments = [{"amount": p.amount, "method": p.method, "reference": p.reference} for p in body.payments]
    inv = sales_service.convert_quote(
        db, invoice_id, payments=payments, user_id=body.user_id, tax_rate=body.tax_rate,
    )
    return {
        "id": inv.id, "number": inv.number, "status": inv.status,
        "total": str(inv.total), "paid_amount": str(inv.paid_amount),
    }


@router.get("/quotes")
def list_quotes(db: Session = Depends(get_session)) -> list[dict]:
    quotes = db.scalars(
        select(Invoice).where(Invoice.status == "draft").order_by(Invoice.id.desc()).limit(100)
    ).all()
    return [
        {
            "id": q.id, "number": q.number, "status": q.status,
            "total": str(q.total), "subtotal": str(q.subtotal),
            "tax_amount": str(q.tax_amount),
            "customer": q.customer.name if q.customer else None,
            "invoice_date": q.invoice_date.isoformat(),
            "line_count": len(q.lines),
        }
        for q in quotes
    ]


@router.get("/quotes/{quote_id}")
def get_quote(quote_id: int, db: Session = Depends(get_session)) -> dict:
    quote = db.get(Invoice, quote_id)
    if quote is None:
        raise HTTPException(status_code=404, detail="Quote not found")
    return {
        "id": quote.id, "number": quote.number, "status": quote.status,
        "customer_id": quote.customer_id,
        "customer": quote.customer.name if quote.customer else None,
        "subtotal": str(quote.subtotal), "discount": str(quote.discount),
        "tax_rate": str(quote.tax_rate), "tax_amount": str(quote.tax_amount),
        "total": str(quote.total), "notes": quote.notes,
        "invoice_date": quote.invoice_date.isoformat(),
        "lines": [
            {
                "item_uuid": l.item.uuid if l.item else None,
                "product": l.product_id,
                "description": l.description,
                "quantity": l.quantity,
                "unit_price": str(l.unit_price),
                "discount": str(l.discount),
                "line_total": str(l.line_total),
                "item_status": l.item.status if l.item else None,
            }
            for l in quote.lines
        ],
    }
