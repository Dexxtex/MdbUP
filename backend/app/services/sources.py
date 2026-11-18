"""Source read model and healthcheck.

A healthcheck only runs against a registered connector with a valid credential.
A disabled or unregistered source returns an explicit error instead of a
simulated ``OK``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.api.errors import NotFoundError, SourceUnavailableError
from app.connectors import registry
from app.core.config import Settings
from app.core.time import utcnow
from app.db.models import Source
from app.domain.enums import AuditActorType, SourceStatus
from app.repositories import audit
from app.repositories import credentials as credentials_repo
from app.repositories import sources as sources_repo
from app.services.credentials import CREDENTIAL_SPECS


@dataclass(frozen=True)
class SourceSummary:
    id: uuid.UUID
    key: str
    name: str
    type: str
    base_url: str | None
    status: str
    status_message: str | None
    is_official: bool
    origin_default: str
    requires_contract: bool
    capabilities: dict[str, object]
    credential_configured: bool
    connector_available: bool
    last_healthcheck_at: datetime | None
    last_success_at: datetime | None


@dataclass(frozen=True)
class HealthcheckResult:
    source_id: uuid.UUID
    source_key: str
    ok: bool
    status: str
    latency_ms: int | None
    message: str
    checked_at: datetime


def list_sources(db: Session) -> list[SourceSummary]:
    return [_summary(db, source) for source in sources_repo.list_sources(db)]


def healthcheck_source(
    db: Session,
    settings: Settings,
    source_id: uuid.UUID,
    *,
    actor_user_id: uuid.UUID | None = None,
    request_id: str | None = None,
) -> HealthcheckResult:
    source = sources_repo.get_source(db, source_id)
    if source is None:
        raise NotFoundError("Fonte non trovata.", details={"source_id": str(source_id)})
    if source.status == SourceStatus.DISABLED.value:
        raise SourceUnavailableError(
            f"Fonte '{source.key}' disabilitata: {source.status_message or 'non attiva'}.",
            details={"source_key": source.key},
        )
    if not registry.is_registered(source.key):
        raise SourceUnavailableError(
            f"Connettore non disponibile per la fonte '{source.key}'.",
            details={"source_key": source.key},
        )
    connector = registry.create_connector(db, settings, source.key)
    try:
        health = connector.healthcheck()
    finally:
        connector.close()
    status = SourceStatus.OK if health.ok else SourceStatus.ERROR
    checked_at = utcnow()
    sources_repo.record_healthcheck(
        db,
        source,
        status=status.value,
        latency_ms=health.latency_ms,
        message=health.message,
        details={"source_key": source.key},
        checked_at=checked_at,
    )
    audit.record(
        db,
        action="source_healthcheck",
        entity_type="source",
        entity_id=source.id,
        actor_user_id=actor_user_id,
        actor_type=AuditActorType.USER if actor_user_id else AuditActorType.SYSTEM,
        after={"status": status.value, "ok": health.ok},
        request_id=request_id,
    )
    db.commit()
    return HealthcheckResult(
        source_id=source.id,
        source_key=source.key,
        ok=health.ok,
        status=status.value,
        latency_ms=health.latency_ms,
        message=health.message,
        checked_at=checked_at,
    )


def _summary(db: Session, source: Source) -> SourceSummary:
    return SourceSummary(
        id=source.id,
        key=source.key,
        name=source.name,
        type=source.type,
        base_url=source.base_url,
        status=source.status,
        status_message=source.status_message,
        is_official=source.is_official,
        origin_default=source.origin_default,
        requires_contract=source.requires_contract,
        capabilities=dict(source.capabilities or {}),
        credential_configured=_credential_configured(db, source),
        connector_available=registry.is_registered(source.key),
        last_healthcheck_at=source.last_healthcheck_at,
        last_success_at=source.last_success_at,
    )


def _credential_configured(db: Session, source: Source) -> bool:
    kind = registry.required_credential_kind(source.key)
    if kind is None:
        return False
    spec = CREDENTIAL_SPECS[kind]
    row = credentials_repo.get_credential(
        db, scope=spec.scope.value, source_id=source.id, key=spec.key
    )
    return row is not None
