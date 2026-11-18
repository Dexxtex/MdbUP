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

from app.connectors import registry
from app.core.config import Settings
from app.core.metrics import api_usage_snapshot
from app.core.time import utcnow
from app.db.models import Source
from app.domain.enums import AuditActorType, OfferType, SourceStatus
from app.domain.errors import NotFoundError, SourceUnavailableError
from app.repositories import audit
from app.repositories import collections as collections_repo
from app.repositories import credentials as credentials_repo
from app.repositories import providers as providers_repo
from app.repositories import sources as sources_repo
from app.services.credentials import CREDENTIAL_SPECS

JUSTWATCH_SOURCE_KEY = "justwatch"
# Collection kinds the JustWatch sync and the API can create.
JUSTWATCH_SUPPORTED_KINDS = (
    "CATALOG",
    "RECENTLY_ADDED",
    "UPCOMING",
    "CHART",
)


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
    justwatch: dict[str, object] | None
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


def list_sources(db: Session, settings: Settings | None = None) -> list[SourceSummary]:
    return [_summary(db, source, settings) for source in sources_repo.list_sources(db)]


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


def _summary(db: Session, source: Source, settings: Settings | None = None) -> SourceSummary:
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
        justwatch=_justwatch_block(db, source, settings),
        last_healthcheck_at=source.last_healthcheck_at,
        last_success_at=source.last_success_at,
    )


def _justwatch_block(
    db: Session, source: Source, settings: Settings | None
) -> dict[str, object] | None:
    """JustWatch-specific runtime state: throttle, cache, usage and mappings."""
    if source.key != JUSTWATCH_SOURCE_KEY:
        return None
    usage = api_usage_snapshot()["justwatch"]
    counts = collections_repo.count_by_provider_for_source(db, source.id, country_code="IT")
    mappings: list[dict[str, object]] = []
    offer_types: set[str] = set()
    for mapping in providers_repo.list_mappings(db, source_id=source.id, country_code="IT"):
        if not mapping.is_verified:
            continue
        provider = providers_repo.get_provider(db, mapping.provider_id)
        if provider is None:
            continue
        metadata = mapping.metadata_json or {}
        monetization_types = [str(value) for value in metadata.get("monetization_types") or []]
        offer_types.update(monetization_types)
        mappings.append(
            {
                "provider_slug": provider.slug,
                "provider_name": provider.name,
                "external_id": mapping.external_provider_id,
                "technical_name": metadata.get("technical_name"),
                "clear_name": metadata.get("clear_name") or mapping.external_name,
                "monetization_types": monetization_types,
                "collections_count": counts.get(provider.id, 0),
            }
        )
    return {
        "throttle_ms": settings.justwatch_min_interval_ms if settings is not None else None,
        "cache_ttl_seconds": (
            settings.justwatch_cache_ttl_seconds if settings is not None else None
        ),
        "cache_max_entries": (
            settings.justwatch_cache_max_entries if settings is not None else None
        ),
        "cache_hits": usage["cache_hits"],
        "cache_misses": usage["cache_misses"],
        "requests_hour": usage["hour"],
        "requests_today": usage["today"],
        "mappings": sorted(mappings, key=lambda row: str(row["provider_slug"])),
        "supported_kinds": list(JUSTWATCH_SUPPORTED_KINDS),
        "supported_offer_types": sorted(offer_types) or [OfferType.FLATRATE.value],
    }


def _credential_configured(db: Session, source: Source) -> bool:
    kind = registry.required_credential_kind(source.key)
    if kind is None:
        return False
    spec = CREDENTIAL_SPECS[kind]
    row = credentials_repo.get_credential(
        db, scope=spec.scope.value, source_id=source.id, key=spec.key
    )
    return row is not None
