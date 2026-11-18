"""Authentication use cases: bootstrap, login, session resolution, logout.

Services raise the ``AppError`` subclasses from ``app/api/errors.py``; the API
layer only translates them into the HTTP envelope.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import (
    CSRF_TOKEN_BYTES,
    PasswordPolicyError,
    constant_time_equals,
    generate_token,
    hash_password,
    hash_token,
    needs_rehash,
    validate_password_strength,
    verify_password,
)
from app.core.time import ensure_utc, utcnow
from app.db.models import AppUser, UserSession
from app.domain.enums import AuditActorType
from app.domain.errors import (
    AlreadyBootstrappedError,
    AuthError,
    BootstrapDisabledError,
    InvalidBootstrapTokenError,
    InvalidCredentialsError,
    ValidationError,
)
from app.repositories import audit, users

# Verifying against a fixed hash keeps the "unknown email" and "wrong password"
# paths comparable in time (no account enumeration through latency).
_TIMING_EQUALIZER_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$dlADWZLbnOyS9zW2Uf4Xbw"
    "$aPeUh1yl2rPJPJ/OoMY/I4DFTCFD46ZgOV61lBcL3dw"
)


@dataclass(frozen=True)
class LoginResult:
    user: AppUser
    session_token: str
    csrf_token: str
    expires_at: datetime


def bootstrap_admin(
    db: Session,
    settings: Settings,
    *,
    token: str,
    email: str,
    password: str,
    ip: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
) -> AppUser:
    """Create the first admin exactly once, using ``BOOTSTRAP_TOKEN``."""
    if not settings.bootstrap_enabled:
        raise BootstrapDisabledError()
    if users.count_users(db) > 0:
        raise AlreadyBootstrappedError()
    if not constant_time_equals(token, settings.bootstrap_token):
        audit.record(
            db,
            action="bootstrap_failed",
            entity_type="app_user",
            after={"email": users.normalize_email(email)},
            ip=ip,
            user_agent=user_agent,
            request_id=request_id,
        )
        db.commit()
        raise InvalidBootstrapTokenError()
    try:
        validate_password_strength(password, email)
    except PasswordPolicyError as exc:
        raise ValidationError(str(exc), code="AUTH_WEAK_PASSWORD") from exc
    user = users.create_user(db, email=email, password_hash=hash_password(password), is_admin=True)
    audit.record(
        db,
        action="bootstrap_completed",
        entity_type="app_user",
        entity_id=user.id,
        actor_user_id=user.id,
        actor_type=AuditActorType.USER,
        after={"email": user.email},
        ip=ip,
        user_agent=user_agent,
        request_id=request_id,
    )
    db.commit()
    return user


def login(
    db: Session,
    settings: Settings,
    *,
    email: str,
    password: str,
    ip: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
) -> LoginResult:
    """Verify credentials and open a new session."""
    user = users.get_by_email(db, email)
    if user is None:
        verify_password(_TIMING_EQUALIZER_HASH, password)
        password_ok = False
    else:
        password_ok = verify_password(user.password_hash, password)
    if user is None or not user.is_active or not password_ok:
        audit.record(
            db,
            action="login_failed",
            entity_type="app_user",
            entity_id=user.id if user is not None else None,
            after={"email": users.normalize_email(email)},
            ip=ip,
            user_agent=user_agent,
            request_id=request_id,
        )
        db.commit()
        raise InvalidCredentialsError()
    if needs_rehash(user.password_hash):
        users.update_password_hash(db, user, hash_password(password))
    users.record_login(db, user)
    result = _open_session(db, settings, user, ip=ip, user_agent=user_agent)
    audit.record(
        db,
        action="login_succeeded",
        entity_type="app_user",
        entity_id=user.id,
        actor_user_id=user.id,
        actor_type=AuditActorType.USER,
        ip=ip,
        user_agent=user_agent,
        request_id=request_id,
    )
    db.commit()
    return result


def logout(
    db: Session,
    session: UserSession,
    *,
    ip: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
) -> None:
    """Revoke the current session."""
    users.revoke_session(db, session)
    audit.record(
        db,
        action="logout",
        entity_type="user_session",
        entity_id=session.id,
        actor_user_id=session.user_id,
        actor_type=AuditActorType.USER,
        ip=ip,
        user_agent=user_agent,
        request_id=request_id,
    )
    db.commit()


def load_session(db: Session, settings: Settings, token: str) -> UserSession:
    """Resolve a session cookie token into a live session row."""
    session = users.get_session_by_token_hash(db, hash_token(token))
    if session is None:
        raise AuthError("Sessione non valida.")
    now = utcnow()
    if session.revoked_at is not None:
        raise AuthError("Sessione revocata.")
    if ensure_utc(session.expires_at) <= now:
        raise AuthError("Sessione scaduta.")
    idle_deadline = ensure_utc(session.last_seen_at) + timedelta(hours=settings.session_idle_hours)
    if idle_deadline <= now:
        raise AuthError("Sessione inattiva da troppo tempo.")
    touch_interval = timedelta(minutes=settings.session_touch_interval_minutes)
    if now - ensure_utc(session.last_seen_at) >= touch_interval:
        users.touch_session(db, session, at=now)
    return session


def change_password(
    db: Session,
    user: AppUser,
    *,
    current_password: str,
    new_password: str,
    ip: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
) -> None:
    """Change the password after verifying the current one.

    All sessions (including the caller's) are revoked: a password change is a
    security boundary, and the UI asks the user to log in again.
    """
    if not verify_password(user.password_hash, current_password):
        audit.record(
            db,
            action="password_change_failed",
            entity_type="app_user",
            entity_id=user.id,
            actor_user_id=user.id,
            actor_type=AuditActorType.USER,
            ip=ip,
            user_agent=user_agent,
            request_id=request_id,
        )
        db.commit()
        raise InvalidCredentialsError("La password attuale non è corretta.")
    try:
        validate_password_strength(new_password, user.email)
    except PasswordPolicyError as exc:
        raise ValidationError(str(exc), code="AUTH_WEAK_PASSWORD") from exc
    if verify_password(user.password_hash, new_password):
        raise ValidationError(
            "La nuova password deve essere diversa da quella attuale.",
            code="AUTH_PASSWORD_UNCHANGED",
        )
    user.password_hash = hash_password(new_password)
    users.revoke_all_sessions(db, user.id)
    audit.record(
        db,
        action="password_changed",
        entity_type="app_user",
        entity_id=user.id,
        actor_user_id=user.id,
        actor_type=AuditActorType.USER,
        after={"email": user.email, "sessions_revoked": True},
        ip=ip,
        user_agent=user_agent,
        request_id=request_id,
    )
    db.commit()


def rotate_csrf(db: Session, session: UserSession) -> str:
    """Issue a new CSRF token for an existing session and store its digest."""
    csrf_token = generate_token(CSRF_TOKEN_BYTES)
    users.update_csrf_hash(db, session, hash_token(csrf_token))
    db.commit()
    return csrf_token


def _open_session(
    db: Session,
    settings: Settings,
    user: AppUser,
    *,
    ip: str | None,
    user_agent: str | None,
) -> LoginResult:
    session_token = generate_token()
    csrf_token = generate_token(CSRF_TOKEN_BYTES)
    expires_at = utcnow() + timedelta(days=settings.session_ttl_days)
    users.create_session(
        db,
        user_id=user.id,
        token_hash=hash_token(session_token),
        csrf_hash=hash_token(csrf_token),
        expires_at=expires_at,
        ip=ip,
        user_agent=user_agent,
    )
    return LoginResult(
        user=user,
        session_token=session_token,
        csrf_token=csrf_token,
        expires_at=expires_at,
    )
