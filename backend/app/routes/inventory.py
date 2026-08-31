from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessError
from app.database import get_session
from app.models import Item, Product
from app.services import inventory_service

router = APIRouter()


@router.get("/items")
def list_items(q: str | None = None, status: str | None = None, db: Session = Depends(get_session)) -> list[dict]:
    stmt = select(Item)
    if status:
        stmt = stmt.where(Item.status == status)
    items = db.scalars(stmt).all()
    if q:
        q_lower = q.strip().lower()
        items = [
            i for i in items
            if q_lower in (i.serial_number or "").lower()
            or q_lower in i.uuid.lower()
            or (i.product and q_lower in f"{i.product.brand} {i.product.model}".lower())
        ]
    return [
        {
            "id": i.id, "uuid": i.uuid, "serial_number": i.serial_number,
            "status": i.status,
            "product_name": f"{i.product.brand} {i.product.model}" if i.product else None,
            "purchase_cost": str(i.purchase_cost),
            "is_placeholder_serial": bool(i.serial_number and i.serial_number.startswith("AUTO-")),
        }
        for i in items
    ]


@router.get("/products")
def list_products(db: Session = Depends(get_session)) -> list[dict]:
    products = db.scalars(select(Product).where(Product.is_active.is_(True))).all()
    stock_counts: dict[int, int] = {}
    for i in db.scalars(select(Item).where(Item.status == "in_stock")).all():
        stock_counts[i.product_id] = stock_counts.get(i.product_id, 0) + 1
    return [
        {
            "id": p.id, "brand": p.brand, "model": p.model,
            "default_price": str(p.default_price), "is_serialized": p.is_serialized,
            "in_stock_count": stock_counts.get(p.id, 0),
        }
        for p in products
    ]


class CreateProductBody(BaseModel):
    brand: str
    model: str
    is_serialized: bool = True
    default_price: str = "0.00"
    warranty_months: int = 0
    warranty_terms: str | None = None


@router.post("/products")
def create_product(body: CreateProductBody, db: Session = Depends(get_session)) -> dict:
    if not body.brand.strip() or not body.model.strip():
        raise BusinessError("Brand and model are required", 400)
    product = Product(
        brand=body.brand.strip(), model=body.model.strip(),
        is_serialized=body.is_serialized, default_price=Decimal(body.default_price),
        warranty_months=body.warranty_months, warranty_terms=body.warranty_terms,
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return {"id": product.id, "brand": product.brand, "model": product.model}


class AddStockBody(BaseModel):
    product_id: int
    serial_number: str | None = None
    purchase_cost: str = "0.00"
    quantity: int = 1  # for non-serialized products, add this many identical units
    user_id: int | None = None


@router.post("/items")
def add_stock(body: AddStockBody, db: Session = Depends(get_session)) -> list[dict]:
    product = db.get(Product, body.product_id)
    if product is None:
        raise BusinessError("Product not found", 404)

    if product.is_serialized:
        if not body.serial_number:
            raise BusinessError("Serial number is required for a serialized product", 400)
        item = inventory_service.create_item(
            db, product_id=body.product_id, serial_number=body.serial_number,
            purchase_cost=Decimal(body.purchase_cost), user_id=body.user_id,
        )
        return [{"id": item.id, "uuid": item.uuid, "serial_number": item.serial_number}]
    else:
        if body.quantity < 1:
            raise BusinessError("Quantity must be at least 1", 400)
        created = []
        for _ in range(body.quantity):
            item = inventory_service.create_item(
                db, product_id=body.product_id, serial_number=None,
                purchase_cost=Decimal(body.purchase_cost), user_id=body.user_id,
            )
            created.append({"id": item.id, "uuid": item.uuid, "serial_number": item.serial_number})
        return created


class UpdateProductBody(BaseModel):
    brand: str | None = None
    model: str | None = None
    is_serialized: bool | None = None
    default_price: str | None = None


@router.put("/products/{product_id}")
def update_product(product_id: int, body: UpdateProductBody, db: Session = Depends(get_session)) -> dict:
    product = db.get(Product, product_id)
    if product is None:
        raise BusinessError("Product not found", 404)
    if body.brand is not None and not body.brand.strip():
        raise BusinessError("Brand cannot be empty", 400)
    if body.model is not None and not body.model.strip():
        raise BusinessError("Model cannot be empty", 400)
    if body.brand is not None:
        product.brand = body.brand.strip()
    if body.model is not None:
        product.model = body.model.strip()
    if body.is_serialized is not None:
        product.is_serialized = body.is_serialized
    if body.default_price is not None:
        product.default_price = Decimal(body.default_price)
    db.commit()
    db.refresh(product)
    return {"id": product.id, "brand": product.brand, "model": product.model}


@router.delete("/products/{product_id}")
def delete_product(product_id: int, db: Session = Depends(get_session)) -> dict:
    product = db.get(Product, product_id)
    if product is None:
        raise BusinessError("Product not found", 404)
    product.is_active = False
    db.commit()
    return {"id": product_id, "deleted": True}


class SetItemSerialBody(BaseModel):
    serial_number: str


@router.put("/items/{item_id}/serial")
def set_item_serial(item_id: int, body: SetItemSerialBody, db: Session = Depends(get_session)) -> dict:
    item = db.get(Item, item_id)
    if item is None:
        raise BusinessError("Item not found", 404)
    serial = body.serial_number.strip()
    if not serial:
        raise BusinessError("Serial number cannot be empty", 400)
    item.serial_number = serial
    db.commit()
    db.refresh(item)
    return {"id": item.id, "uuid": item.uuid, "serial_number": item.serial_number}
