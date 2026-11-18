"""Liveness, readiness, Prometheus metrics and system status endpoints."""

from __future__ import annotations

from typing import Literal, cast

import redis
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api import schemas
from app.api.deps import get_db_dep, get_settings_dep, require_admin
from app.api.errors import (
    AuthError,
    ForbiddenError,
    NotFoundError,
    ServiceUnavailableError,
)
from app.core.config import APP_VERSION, Settings
from app.core.crypto import encryption_key_available
from app.core.logging import get_logger
from app.core.security import constant_time_equals
from app.db.models import AppUser
from app.services import system_status

logger = get_logger(__name__)

router = APIRouter(tags=["system"])


def _database_ready(db: Session) -> bool:
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        logger.error("readiness_db_unavailable", error=type(exc).__name__)
        return False
    return True


def _redis_ready(settings: Settings) -> bool:
    if not settings.redis_url:
        return False
    try:
        client = redis.Redis.from_url(
            settings.redis_url, socket_timeout=0.5, socket_connect_timeout=0.5
        )
        return bool(client.ping())
    except redis.RedisError as exc:
        logger.warning("readiness_redis_unavailable", error=type(exc).__name__)
        return False


@router.get("/health", response_model=schemas.HealthOut, summary="Liveness")
def health() -> schemas.HealthOut:
    return schemas.HealthOut(status="ok", version=APP_VERSION)


@router.get(
    "/ready",
    response_model=schemas.ReadinessOut,
    responses={503: {"model": schemas.ErrorEnvelope}},
    summary="Readiness con controlli di dipendenza",
)
def ready(
    response: Response,
    db: Session = Depends(get_db_dep),
    settings: Settings = Depends(get_settings_dep),
) -> schemas.ReadinessOut:
    checks = {
        "db": _database_ready(db),
        "redis": _redis_ready(settings),
        "encryption_key": encryption_key_available(settings),
    }
    status = "ok" if all(checks.values()) else "degraded"
    if not checks["db"]:
        response.status_code = 503
    return schemas.ReadinessOut(status=cast(Literal["ok", "degraded"], status), checks=checks)


def _metrics_token(request: Request) -> str | None:
    """Bearer token or ``X-Metrics-Token``; ``None`` when neither is present."""
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization[len("bearer ") :].strip() or None
    header = request.headers.get("x-metrics-token", "").strip()
    return header or None


@router.get(
    "/metrics",
    summary="Metriche Prometheus (token richiesto)",
    responses={401: {"model": schemas.ErrorEnvelope}, 403: {"model": schemas.ErrorEnvelope}},
)
def metrics(
    request: Request,
    db: Session = Depends(get_db_dep),
    settings: Settings = Depends(get_settings_dep),
) -> Response:
    """Prometheus text exposition; never public, even on the internal network."""
    if not settings.metrics_enabled:
        raise NotFoundError("Endpoint metriche disabilitato.", code="METRICS_DISABLED")
    expected = settings.metrics_token.strip()
    if not expected:
        raise ServiceUnavailableError(
            "METRICS_TOKEN non configurato: endpoint metriche non disponibile.",
            code="METRICS_TOKEN_MISSING",
        )
    provided = _metrics_token(request)
    if provided is None:
        raise AuthError("Token metriche mancante.", code="METRICS_TOKEN_REQUIRED")
    if not constant_time_equals(provided, expected):
        raise ForbiddenError("Token metriche non valido.", code="METRICS_TOKEN_INVALID")
    return Response(
        content=system_status.render_metrics(db, settings),
        media_type=system_status.PROMETHEUS_CONTENT_TYPE,
    )


@router.get(
    "/system/status",
    response_model=schemas.SystemStatusOut,
    summary="Stato di sistema per topbar e dashboard",
)
def get_system_status(
    db: Session = Depends(get_db_dep),
    settings: Settings = Depends(get_settings_dep),
    _admin: AppUser = Depends(require_admin),
) -> schemas.SystemStatusOut:
    return schemas.SystemStatusOut.model_validate(system_status.get_system_status(db, settings))
