from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_session
from app.models import Customer
from app.services import crm_service

router = APIRouter()


@router.get("")
def list_customers(q: str | None = None, db: Session = Depends(get_session)) -> list[dict]:
    stmt = select(Customer).order_by(Customer.name)
    customers = db.scalars(stmt).all()
    if q:
        q_lower = q.strip().lower()
        customers = [
            c for c in customers
            if q_lower in (c.name or "").lower() or q_lower in (c.phone or "")
        ]
    return [
        {"id": c.id, "name": c.name, "phone": c.phone, "credit_limit": str(c.credit_limit)}
        for c in customers
    ]


@router.get("/{customer_id}/statement")
def customer_statement(customer_id: int, db: Session = Depends(get_session)) -> dict:
    balance = crm_service.customer_balance(db, customer_id)
    entries = crm_service.customer_statement(db, customer_id)
    return {
        "balance": {k: (str(v) if v is not None else None) for k, v in balance.items()},
        "entries": [
            {
                "date": e.date.isoformat(),
                "type": e.type,
                "number": e.number,
                "description": e.description,
                "debit": str(e.debit),
                "credit": str(e.credit),
                "balance": str(e.balance),
            }
            for e in entries
        ],
    }


@router.get("/reports/aging")
def aging_report(db: Session = Depends(get_session)) -> list[dict]:
    rows = crm_service.aging_report(db)
    return [
        {
            "customer_id": r.customer_id, "name": r.name, "phone": r.phone,
            "current": str(r.current), "d1_30": str(r.d1_30), "d31_60": str(r.d31_60),
            "d61_90": str(r.d61_90), "d90": str(r.d90), "total": str(r.total),
        }
        for r in rows
    ]
