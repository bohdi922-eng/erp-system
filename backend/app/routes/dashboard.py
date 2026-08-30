from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.enums import InvoiceStatus, RepairStatus
from app.database import get_session
from app.models import Customer, Invoice, Item, Product, RepairOrder
from app.services import crm_service

router = APIRouter()

LOW_STOCK_THRESHOLD = 3  # products with fewer than this many IN_STOCK units


@router.get("/summary")
def dashboard_summary(db: Session = Depends(get_session)) -> dict:
    today = date.today()

    # -- Today's revenue --------------------------------------------------
    today_revenue = db.scalar(
        select(func.coalesce(func.sum(Invoice.total), 0)).where(
            Invoice.invoice_date == today,
            Invoice.status != InvoiceStatus.CANCELLED.value,
        )
    ) or Decimal("0.00")

    # -- Open repairs -------------------------------------------------------
    closed_statuses = [
        RepairStatus.DELIVERED.value, RepairStatus.CLOSED.value, RepairStatus.CANCELLED.value,
    ]
    open_repairs = db.scalar(
        select(func.count(RepairOrder.id)).where(RepairOrder.status.not_in(closed_statuses))
    ) or 0

    # -- Low stock ------------------------------------------------------
    in_stock_counts = dict(
        db.execute(
            select(Item.product_id, func.count(Item.id))
            .where(Item.status == "in_stock")
            .group_by(Item.product_id)
        ).all()
    )
    all_product_ids = db.scalars(select(Product.id).where(Product.is_active.is_(True))).all()
    low_stock_count = sum(
        1 for pid in all_product_ids if in_stock_counts.get(pid, 0) < LOW_STOCK_THRESHOLD
    )

    # -- Outstanding balances (reuses crm_service so this stays consistent
    #    with whatever the customer statement / aging report show) --------
    customer_ids = db.scalars(select(Customer.id)).all()
    outstanding_total = sum(
        (crm_service.customer_outstanding(db, cid) for cid in customer_ids), Decimal("0.00")
    )

    # -- Recent activity (latest invoices + repairs, merged) ----------------
    recent_invoices = db.scalars(
        select(Invoice).order_by(Invoice.created_at.desc()).limit(5)
    ).all()
    recent_repairs = db.scalars(
        select(RepairOrder).order_by(RepairOrder.created_at.desc()).limit(5)
    ).all()
    activity = [
        {
            "type": "invoice",
            "number": inv.number,
            "at": inv.created_at.isoformat(),
            "total": str(inv.total),
            "customer": inv.customer.name if inv.customer else None,
        }
        for inv in recent_invoices
    ] + [
        {
            "type": "repair",
            "number": rep.number,
            "at": rep.created_at.isoformat(),
            "status": rep.status,
            "device": rep.device_description,
        }
        for rep in recent_repairs
    ]
    activity.sort(key=lambda e: e["at"], reverse=True)

    return {
        "today_revenue": str(today_revenue),
        "open_repairs": open_repairs,
        "low_stock_count": low_stock_count,
        "outstanding_total": str(outstanding_total),
        "activity": activity[:5],
        "currency": "ج.م",
    }
