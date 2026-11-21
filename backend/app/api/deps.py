"""Shared FastAPI dependencies: settings, database, auth, CSRF, rate limiting."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta
from functools import lru_cache
from urllib.parse import urlsplit

from fastapi import Depends, Request, Response
from sqlalchemy.orm import Session

from app.api.errors import (
    AuthError,
    CsrfError,
    ForbiddenError,
    OriginRejectedError,
    RateLimitedError,
)
from app.core.config import Settings, get_settings
from app.core.security import (
    RateLimiter,
    build_rate_limiter,
    constant_time_equals,
    hash_token,
)
from app.core.time import ensure_utc, utcnow
from app.db.models import AppUser, UserSession
from app.db.session import get_db
from app.services import auth as auth_service


def get_settings_dep() -> Settings:
    """Inject the application settings."""
    return get_settings()


def get_db_dep() -> Iterator[Session]:
    """Inject a request-scoped database session."""
    yield from get_db()


@lru_cache(maxsize=4)
def _rate_limiter_for(redis_url: str) -> RateLimiter:
    return build_rate_limiter(redis_url)


def get_rate_limiter(settings: Settings = Depends(get_settings_dep)) -> RateLimiter:
    """Inject the process-wide rate limiter (Redis with in-memory fallback)."""
    return _rate_limiter_for(settings.redis_url)


def reset_rate_limiters() -> None:
    """Drop cached limiters (tests reconfigure Redis between cases)."""
    _rate_limiter_for.cache_clear()


def get_request_id(request: Request) -> str:
    """Return the request id assigned by the middleware."""
    return getattr(request.state, "request_id", "")


def get_client_ip(request: Request, settings: Settings | None = None) -> str:
    """Return the peer IP, trusting ``X-Forwarded-For`` only from known proxies.

    The header is client-controlled unless a reverse proxy overwrites/appends it.
    Trusting it unconditionally would let anyone rotate the rate-limit key.
    """
    peer = request.client.host if request.client else "unknown"
    active = settings or get_settings()
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded and peer in active.trusted_proxy_list:
        # The trusted proxy appends the real peer; the left-most value is still
        # client-controlled and must never be used.
        candidate = forwarded.split(",")[-1].strip()
        if candidate:
            return candidate
    return peer


def _origin_parts(value: str) -> tuple[str, str, int | None] | None:
    """Return ``(scheme, hostname, port)`` for an absolute HTTP(S) URL."""
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return None
    if parsed.username is not None or parsed.password is not None:
        return None
    try:
        port = parsed.port
    except ValueError:
        return None
    if port is None:
        port = 443 if parsed.scheme == "https" else 80
    return parsed.scheme.lower(), parsed.hostname.lower(), port


def verify_origin(request: Request, settings: Settings) -> None:
    """Reject unsafe requests whose ``Origin``/``Referer`` is not the app origin.

    Both headers are validated when present: a valid ``Origin`` never masks a
    foreign ``Referer``. The comparison is on scheme, hostname and effective
    port, so ``https://app.example`` and ``https://app.example:443`` match while
    a look-alike host cannot. In production a missing Origin/Referer is rejected
    too; in dev/test it is tolerated so CLI/TestClient flows remain usable.
    """
    origin = request.headers.get("origin")
    referer = request.headers.get("referer")
    expected = _origin_parts(settings.app_base_url)
    if expected is None:
        raise OriginRejectedError("APP_BASE_URL non è un URL HTTP(S) valido.")
    candidates = [value for value in (origin, referer) if value]
    if not candidates:
        if settings.is_production:
            raise OriginRejectedError()
        return
    for candidate in candidates:
        if _origin_parts(candidate) != expected:
            raise OriginRejectedError()


def get_current_session(
    request: Request,
    db: Session = Depends(get_db_dep),
    settings: Settings = Depends(get_settings_dep),
) -> UserSession:
    """Resolve the session cookie into a live ``UserSession`` row."""
    token = request.cookies.get(settings.session_cookie)
    if not token:
        raise AuthError("Sessione mancante o scaduta.")
    session = auth_service.load_session(db, settings, token)
    db.commit()
    return session


def get_current_user(
    session: UserSession = Depends(get_current_session),
    db: Session = Depends(get_db_dep),
) -> AppUser:
    """Return the authenticated user for the current session."""
    user = db.get(AppUser, session.user_id)
    if user is None or not user.is_active:
        raise AuthError("Utente non attivo.")
    return user


def require_admin(user: AppUser = Depends(get_current_user)) -> AppUser:
    """Allow only administrators (single-user app: the bootstrap account)."""
    if not user.is_admin:
        raise ForbiddenError()
    return user


def require_csrf(
    request: Request,
    session: UserSession = Depends(get_current_session),
    settings: Settings = Depends(get_settings_dep),
) -> None:
    """Double-submit CSRF check for state-changing methods."""
    verify_origin(request, settings)
    header = request.headers.get("x-csrf-token", "")
    cookie = request.cookies.get(settings.csrf_cookie, "")
    if not header or not cookie or not constant_time_equals(header, cookie):
        raise CsrfError()
    if not constant_time_equals(hash_token(header), session.csrf_hash):
        raise CsrfError()


def enforce_rate_limit(
    limiter: RateLimiter,
    *,
    key: str,
    limit: int,
    window_seconds: int,
    lockout_seconds: int = 0,
) -> None:
    """Raise ``RateLimitedError`` when the counter for ``key`` is exhausted."""
    decision = limiter.check(
        key,
        limit=limit,
        window_seconds=window_seconds,
        lockout_seconds=lockout_seconds,
    )
    if not decision.allowed:
        raise RateLimitedError(retry_after_seconds=decision.retry_after_seconds)


def set_session_cookies(
    response: Response,
    settings: Settings,
    *,
    session_token: str,
    csrf_token: str,
    expires_at: datetime,
) -> None:
    """Set the HttpOnly session cookie and the readable CSRF cookie."""
    max_age = max(0, int((ensure_utc(expires_at) - utcnow()).total_seconds()))
    response.set_cookie(
        settings.session_cookie,
        session_token,
        max_age=max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        settings.csrf_cookie,
        csrf_token,
        max_age=max_age,
        httponly=False,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def set_csrf_cookie(response: Response, settings: Settings, csrf_token: str) -> None:
    """Refresh only the CSRF cookie (session unchanged)."""
    max_age = int(timedelta(days=settings.session_ttl_days).total_seconds())
    response.set_cookie(
        settings.csrf_cookie,
        csrf_token,
        max_age=max_age,
        httponly=False,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookies(response: Response, settings: Settings) -> None:
    """Delete both auth cookies."""
    response.delete_cookie(settings.session_cookie, path="/", secure=settings.cookie_secure)
    response.delete_cookie(settings.csrf_cookie, path="/", secure=settings.cookie_secure)
