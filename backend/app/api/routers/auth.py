"""Authentication endpoints: bootstrap, login, logout, session."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.api import schemas
from app.api.deps import (
    clear_session_cookies,
    enforce_rate_limit,
    get_client_ip,
    get_current_session,
    get_current_user,
    get_db_dep,
    get_rate_limiter,
    get_request_id,
    get_settings_dep,
    require_csrf,
    set_csrf_cookie,
    set_session_cookies,
    verify_origin,
)
from app.core.config import Settings
from app.core.security import RateLimiter, constant_time_equals, hash_token
from app.db.models import AppUser, UserSession
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/bootstrap",
    status_code=201,
    response_model=schemas.BootstrapOut,
    summary="Crea il primo admin con il token monouso",
)
def bootstrap(
    payload: schemas.BootstrapRequest,
    request: Request,
    db: Session = Depends(get_db_dep),
    settings: Settings = Depends(get_settings_dep),
    limiter: RateLimiter = Depends(get_rate_limiter),
) -> schemas.BootstrapOut:
    verify_origin(request, settings)
    ip = get_client_ip(request)
    enforce_rate_limit(
        limiter,
        key=f"bootstrap:{ip}",
        limit=settings.bootstrap_max_attempts,
        window_seconds=60 * settings.login_window_minutes,
    )
    user = auth_service.bootstrap_admin(
        db,
        settings,
        token=payload.token,
        email=str(payload.email),
        password=payload.password,
        ip=ip,
        user_agent=request.headers.get("user-agent"),
        request_id=get_request_id(request),
    )
    return schemas.BootstrapOut(user=schemas.UserOut.model_validate(user))


@router.post("/login", response_model=schemas.SessionOut, summary="Login con email e password")
def login(
    payload: schemas.LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db_dep),
    settings: Settings = Depends(get_settings_dep),
    limiter: RateLimiter = Depends(get_rate_limiter),
) -> schemas.SessionOut:
    verify_origin(request, settings)
    ip = get_client_ip(request)
    rate_key = f"login:{ip}:{str(payload.email).strip().lower()}"
    enforce_rate_limit(
        limiter,
        key=rate_key,
        limit=settings.login_max_attempts,
        window_seconds=60 * settings.login_window_minutes,
        lockout_seconds=60 * settings.login_lockout_minutes,
    )
    result = auth_service.login(
        db,
        settings,
        email=str(payload.email),
        password=payload.password,
        ip=ip,
        user_agent=request.headers.get("user-agent"),
        request_id=get_request_id(request),
    )
    limiter.reset(rate_key)
    set_session_cookies(
        response,
        settings,
        session_token=result.session_token,
        csrf_token=result.csrf_token,
        expires_at=result.expires_at,
    )
    return schemas.SessionOut(
        user=schemas.UserOut.model_validate(result.user), csrf_token=result.csrf_token
    )


@router.post(
    "/logout",
    status_code=204,
    dependencies=[Depends(require_csrf)],
    summary="Revoca la sessione corrente",
)
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db_dep),
    settings: Settings = Depends(get_settings_dep),
    session: UserSession = Depends(get_current_session),
) -> None:
    auth_service.logout(
        db,
        session,
        ip=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_id=get_request_id(request),
    )
    clear_session_cookies(response, settings)


@router.post(
    "/change-password",
    status_code=204,
    dependencies=[Depends(require_csrf)],
    summary="Cambia la password dell'utente autenticato",
)
def change_password(
    payload: schemas.ChangePasswordRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db_dep),
    settings: Settings = Depends(get_settings_dep),
    limiter: RateLimiter = Depends(get_rate_limiter),
    user: AppUser = Depends(get_current_user),
) -> None:
    ip = get_client_ip(request)
    enforce_rate_limit(
        limiter,
        key=f"change-password:{user.id}:{ip}",
        limit=3,
        window_seconds=60 * settings.login_window_minutes,
        lockout_seconds=60 * settings.login_lockout_minutes,
    )
    auth_service.change_password(
        db,
        user,
        current_password=payload.current_password,
        new_password=payload.new_password,
        ip=ip,
        user_agent=request.headers.get("user-agent"),
        request_id=get_request_id(request),
    )
    clear_session_cookies(response, settings)


@router.get("/session", response_model=schemas.SessionOut, summary="Sessione corrente")
def read_session(
    request: Request,
    response: Response,
    db: Session = Depends(get_db_dep),
    settings: Settings = Depends(get_settings_dep),
    session: UserSession = Depends(get_current_session),
    user: AppUser = Depends(get_current_user),
) -> schemas.SessionOut:
    cookie = request.cookies.get(settings.csrf_cookie, "")
    if cookie and constant_time_equals(hash_token(cookie), session.csrf_hash):
        csrf_token = cookie
    else:
        # The CSRF cookie is missing or stale: rotate it so the client can mutate.
        csrf_token = auth_service.rotate_csrf(db, session)
        set_csrf_cookie(response, settings, csrf_token)
    return schemas.SessionOut(user=schemas.UserOut.model_validate(user), csrf_token=csrf_token)
