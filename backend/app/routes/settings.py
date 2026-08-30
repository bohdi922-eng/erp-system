from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.enums import UserRole
from app.core.exceptions import BusinessError
from app.core.security import hash_password
from app.database import get_session
from app.models import ShopSettings, User

router = APIRouter()


def _get_or_create_settings(db: Session) -> ShopSettings:
    settings = db.scalar(select(ShopSettings).limit(1))
    if settings is None:
        settings = ShopSettings()
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


@router.get("/shop")
def get_shop_settings(db: Session = Depends(get_session)) -> dict:
    s = _get_or_create_settings(db)
    return {
        "name": s.name, "tax_id": s.tax_id, "address": s.address,
        "phone": s.phone, "email": s.email,
    }


class ShopSettingsBody(BaseModel):
    name: str
    tax_id: str | None = None
    address: str | None = None
    phone: str | None = None
    email: str | None = None


@router.put("/shop")
def update_shop_settings(body: ShopSettingsBody, db: Session = Depends(get_session)) -> dict:
    s = _get_or_create_settings(db)
    s.name = body.name
    s.tax_id = body.tax_id
    s.address = body.address
    s.phone = body.phone
    s.email = body.email
    db.commit()
    db.refresh(s)
    return {"name": s.name, "tax_id": s.tax_id, "address": s.address, "phone": s.phone, "email": s.email}


@router.get("/users")
def list_users(db: Session = Depends(get_session)) -> list[dict]:
    users = db.scalars(select(User).order_by(User.id)).all()
    return [
        {
            "id": u.id, "username": u.username, "full_name": u.full_name,
            "role": u.role, "is_active": u.is_active,
        }
        for u in users
    ]


class CreateUserBody(BaseModel):
    username: str
    full_name: str
    role: str  # admin | cashier | technician
    password: str


@router.post("/users")
def create_user(body: CreateUserBody, db: Session = Depends(get_session)) -> dict:
    if body.role not in (UserRole.ADMIN.value, UserRole.CASHIER.value, UserRole.TECHNICIAN.value):
        raise BusinessError(f"Invalid role '{body.role}'", 400)
    if len(body.password) < 4:
        raise BusinessError("Password must be at least 4 characters", 400)

    user = User(
        username=body.username.strip(), full_name=body.full_name.strip(),
        role=body.role, password_hash=hash_password(body.password), is_active=True,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise BusinessError(f"اسم المستخدم '{body.username}' مستخدم بالفعل", 409)
    db.refresh(user)
    return {"id": user.id, "username": user.username, "full_name": user.full_name, "role": user.role, "is_active": user.is_active}


class UpdateUserBody(BaseModel):
    full_name: str | None = None
    role: str | None = None
    is_active: bool | None = None
    password: str | None = None


@router.put("/users/{user_id}")
def update_user(user_id: int, body: UpdateUserBody, db: Session = Depends(get_session)) -> dict:
    user = db.get(User, user_id)
    if user is None:
        raise BusinessError("User not found", 404)
    if body.role is not None:
        if body.role not in (UserRole.ADMIN.value, UserRole.CASHIER.value, UserRole.TECHNICIAN.value):
            raise BusinessError(f"Invalid role '{body.role}'", 400)
        user.role = body.role
    if body.full_name is not None:
        user.full_name = body.full_name.strip()
    if body.is_active is not None:
        user.is_active = body.is_active
    if body.password:
        if len(body.password) < 4:
            raise BusinessError("Password must be at least 4 characters", 400)
        user.password_hash = hash_password(body.password)
    db.commit()
    db.refresh(user)
    return {"id": user.id, "username": user.username, "full_name": user.full_name, "role": user.role, "is_active": user.is_active}

