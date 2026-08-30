from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessError
from app.core.security import generate_token, verify_password
from app.database import get_session
from app.models import AuthSession, User

router = APIRouter()

SESSION_COOKIE = "erp_session"

# Long-lived sliding session: stays valid as long as the user keeps using
# the app (renewed on each authenticated request), so login happens once.
SESSION_TTL = timedelta(days=30)
RENEW_THRESHOLD = timedelta(days=1)
# The cookie lives longer than the session itself so an active user is never
# kicked out by the browser dropping it; the server decides validity/renewal.
COOKIE_MAX_AGE = 365 * 24 * 60 * 60


def _renew_if_due(db: Session, sess: AuthSession) -> None:
    """Extend a still-active session so people don't get logged out mid-work.
    Only writes when the session is actually close to expiring."""
    if sess.expires_at - datetime.now() < RENEW_THRESHOLD:
        sess.expires_at = datetime.now() + SESSION_TTL
        db.commit()


def _session_token(request: Request) -> str | None:
    """Accept the token from the Authorization header (API clients / tests)
    or from the automatic erp_session cookie (browser users)."""
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.cookies.get(SESSION_COOKIE)


def _bearer_token(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


def get_current_user(
    request: Request, db: Session = Depends(get_session)
) -> User:
    """FastAPI dependency: returns the logged-in User or raises 401."""
    token = _session_token(request)
    if not token:
        raise BusinessError("غير مسجل الدخول", 401)
    sess = db.scalar(
        select(AuthSession).where(AuthSession.token == token)
    )
    if sess is None or sess.expires_at < datetime.now():
        raise BusinessError("انتهت الجلسة، سجل الدخول من جديد", 401)
    user = db.get(User, sess.user_id)
    if user is None or not user.is_active:
        raise BusinessError("الحساب غير متاح", 401)
    _renew_if_due(db, sess)
    return user


def _user_dict(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "role": user.role,
        "is_active": user.is_active,
    }


class LoginBody(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(body: LoginBody, db: Session = Depends(get_session)):
    user = db.scalar(
        select(User).where(User.username == body.username.strip())
    )
    if user is None or not verify_password(body.password, user.password_hash):
        raise BusinessError("اسم المستخدم أو كلمة المرور غير صحيحة", 401)
    if not user.is_active:
        raise BusinessError("الحساب موقوف", 403)

    token = generate_token()
    db.add(AuthSession(
        token=token,
        user_id=user.id,
        expires_at=datetime.now() + SESSION_TTL,
    ))
    db.commit()
    response = JSONResponse({"token": token, "user": _user_dict(user)})
    response.set_cookie(
        SESSION_COOKIE,
        value=token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        path="/",
    )
    return response


@router.post("/logout")
def logout(request: Request, db: Session = Depends(get_session)):
    token = _session_token(request)
    if token:
        db.execute(delete(AuthSession).where(AuthSession.token == token))
        db.commit()
    response = JSONResponse({"ok": True})
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@router.get("/me")
def me(user: User = Depends(get_current_user)) -> dict:
    return _user_dict(user)