from __future__ import annotations

from fastapi import Depends, Header
from sqlalchemy.orm import Session as DbSession

from app.core.exceptions import BusinessError
from app.database import get_session
from app.models import User
from app.services import auth_service


def get_current_user(
    authorization: str | None = Header(None),
    db: DbSession = Depends(get_session),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise BusinessError("لازم تسجّل الدخول الأول", 401)
    token = authorization.removeprefix("Bearer ").strip()
    user = auth_service.get_user_by_token(db, token)
    if user is None:
        raise BusinessError("انتهت صلاحية الجلسة — سجّل الدخول تاني", 401)
    if not user.is_active:
        raise BusinessError("الحساب ده غير نشط", 403)
    return user
