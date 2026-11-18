"""User and session persistence."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.db.models import AppUser, UserSession


def normalize_email(email: str) -> str:
    """Emails are stored lowercased so lookups are case-insensitive."""
    return email.strip().lower()


def count_users(db: Session) -> int:
    """Number of registered users (used to close the bootstrap)."""
    return int(db.scalar(select(func.count()).select_from(AppUser)) or 0)


def get_by_id(db: Session, user_id: uuid.UUID) -> AppUser | None:
    return db.get(AppUser, user_id)


def get_by_email(db: Session, email: str) -> AppUser | None:
    return db.scalar(select(AppUser).where(AppUser.email == normalize_email(email)))


def create_user(
    db: Session,
    *,
    email: str,
    password_hash: str,
    is_admin: bool = True,
) -> AppUser:
    """Insert a user and flush so the generated id is available."""
    user = AppUser(
        email=normalize_email(email),
        password_hash=password_hash,
        is_admin=is_admin,
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user


def record_login(db: Session, user: AppUser, *, at: datetime | None = None) -> None:
    user.last_login_at = at or utcnow()
    db.flush()


def update_password_hash(db: Session, user: AppUser, password_hash: str) -> None:
    user.password_hash = password_hash
    db.flush()


def create_session(
    db: Session,
    *,
    user_id: uuid.UUID,
    token_hash: bytes,
    csrf_hash: bytes,
    expires_at: datetime,
    ip: str | None,
    user_agent: str | None,
) -> UserSession:
    """Persist a new session (only token digests are stored)."""
    now = utcnow()
    session = UserSession(
        user_id=user_id,
        token_hash=token_hash,
        csrf_hash=csrf_hash,
        created_at=now,
        expires_at=expires_at,
        last_seen_at=now,
        ip=ip,
        user_agent=user_agent[:512] if user_agent else None,
    )
    db.add(session)
    db.flush()
    return session


def get_session_by_token_hash(db: Session, token_hash: bytes) -> UserSession | None:
    return db.scalar(select(UserSession).where(UserSession.token_hash == token_hash))


def touch_session(db: Session, session: UserSession, *, at: datetime | None = None) -> None:
    session.last_seen_at = at or utcnow()
    db.flush()


def update_csrf_hash(db: Session, session: UserSession, csrf_hash: bytes) -> None:
    session.csrf_hash = csrf_hash
    db.flush()


def revoke_session(db: Session, session: UserSession, *, at: datetime | None = None) -> None:
    session.revoked_at = at or utcnow()
    db.flush()


def revoke_all_sessions(db: Session, user_id: uuid.UUID, *, at: datetime | None = None) -> int:
    """Revoke every live session of a user (password change, logout globale)."""
    result = db.execute(
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=at or utcnow())
    )
    db.flush()
    return int(getattr(result, "rowcount", 0) or 0)
