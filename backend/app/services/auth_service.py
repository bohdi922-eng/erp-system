"""Password hashing + session tokens.

Sessions are opaque random tokens stored in the DB (not JWT) — simpler for
a single local shop app, and trivially revocable (delete the row) which a
self-contained JWT isn't without extra infrastructure.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta

import bcrypt
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.models import Session as SessionModel
from app.models import User

SESSION_LIFETIME = timedelta(days=14)


def hash_password(raw: str) -> str:
    return bcrypt.hashpw(raw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(raw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(raw.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        # Covers a None/malformed hash (e.g. a user row with no password
        # set yet) instead of letting bcrypt raise past this function.
        return False


def create_session(db: DbSession, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    db.add(SessionModel(
        token=token, user_id=user_id,
        expires_at=datetime.now() + SESSION_LIFETIME,
    ))
    db.commit()
    return token


def get_user_by_token(db: DbSession, token: str) -> User | None:
    session = db.scalar(select(SessionModel).where(SessionModel.token == token))
    if session is None:
        return None
    if session.expires_at < datetime.now():
        db.delete(session)
        db.commit()
        return None
    return db.get(User, session.user_id)


def delete_session(db: DbSession, token: str) -> None:
    session = db.scalar(select(SessionModel).where(SessionModel.token == token))
    if session is not None:
        db.delete(session)
        db.commit()
