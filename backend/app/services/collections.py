"""Collection read models with provider/source labels and snapshot state."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.api.errors import NotFoundError
from app.db.models import Collection, CollectionSnapshot, Provider, Source
from app.repositories import collections as collections_repo
from app.repositories import providers as providers_repo
from app.repositories import snapshots as snapshots_repo
from app.repositories import sources as sources_repo
from app.services.snapshots import SnapshotSummary, snapshot_summary


@dataclass(frozen=True)
class CollectionSummary:
    id: uuid.UUID
    slug: str
    name: str
    provider_id: uuid.UUID
    provider_slug: str | None
    provider_name: str | None
    source_id: uuid.UUID
    source_key: str | None
    country_code: str
    media_type: str
    kind: str
    origin: str
    date_basis: str
    description: str | None
    filters: dict[str, object]
    quality_flags: dict[str, object]
    provider_names: list[str]
    is_local_filter: bool
    is_multi_provider: bool
    offer_types: list[str]
    sort_mode: str
    is_active: bool
    last_valid_snapshot_id: uuid.UUID | None
    latest_snapshot: SnapshotSummary | None
    last_valid_snapshot: SnapshotSummary | None


def list_collections(
    db: Session,
    *,
    provider_id: uuid.UUID | None = None,
    media_type: str | None = None,
    origin: str | None = None,
    kind: str | None = None,
    country_code: str | None = None,
    is_active: bool | None = None,
) -> list[CollectionSummary]:
    rows = collections_repo.list_collections(
        db,
        provider_id=provider_id,
        media_type=media_type,
        origin=origin,
        kind=kind,
        country_code=country_code,
        is_active=is_active,
    )
    if not rows:
        return []
    collection_ids = [row.id for row in rows]
    latest = snapshots_repo.latest_snapshots_for(db, collection_ids)
    valid = snapshots_repo.latest_snapshots_for(db, collection_ids, valid_only=True)
    providers = {provider.id: provider for provider in providers_repo.list_providers(db)}
    sources = {source.id: source for source in sources_repo.list_sources(db)}
    return [_summary(row, providers, sources.get(row.source_id), latest, valid) for row in rows]


def get_collection(db: Session, collection_id: uuid.UUID) -> CollectionSummary:
    row = collections_repo.get_collection(db, collection_id)
    if row is None:
        raise NotFoundError(
            "Collezione non trovata.", details={"collection_id": str(collection_id)}
        )
    latest = snapshots_repo.latest_snapshots_for(db, [row.id])
    valid = snapshots_repo.latest_snapshots_for(db, [row.id], valid_only=True)
    return _summary(
        row,
        {provider.id: provider for provider in providers_repo.list_providers(db)},
        sources_repo.get_source(db, row.source_id),
        latest,
        valid,
    )


def list_collection_snapshots(
    db: Session,
    collection_id: uuid.UUID,
    *,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[SnapshotSummary], int]:
    if collections_repo.get_collection(db, collection_id) is None:
        raise NotFoundError(
            "Collezione non trovata.", details={"collection_id": str(collection_id)}
        )
    offset = (page - 1) * page_size
    rows = snapshots_repo.list_snapshots(db, collection_id, limit=page_size, offset=offset)
    total = snapshots_repo.count_snapshots(db, collection_id)
    return [snapshot_summary(row) for row in rows], total


def _summary(
    row: Collection,
    providers: dict[uuid.UUID, Provider],
    source: Source | None,
    latest: dict[uuid.UUID, CollectionSnapshot],
    valid: dict[uuid.UUID, CollectionSnapshot],
) -> CollectionSummary:
    latest_snapshot = latest.get(row.id)
    valid_snapshot = valid.get(row.id)
    provider = providers.get(row.provider_id)
    filters = dict(row.filters or {})
    raw_provider_ids = filters.get("provider_ids") or []
    provider_ids: list[uuid.UUID] = []
    for raw in raw_provider_ids:
        try:
            provider_ids.append(uuid.UUID(str(raw)))
        except ValueError:
            continue
    if not provider_ids:
        provider_ids = [row.provider_id]
    provider_names = [
        providers[provider_id].name for provider_id in provider_ids if provider_id in providers
    ]
    if not provider_names and provider is not None:
        provider_names = [provider.name]
    is_local_filter = filters.get("derivation") == "LOCAL_FILTER"
    return CollectionSummary(
        id=row.id,
        slug=row.slug,
        name=row.name,
        provider_id=row.provider_id,
        provider_slug=provider.slug if provider is not None else None,
        provider_name=provider.name if provider is not None else None,
        source_id=row.source_id,
        source_key=source.key if source is not None else None,
        country_code=row.country_code,
        media_type=row.media_type,
        kind=row.kind,
        origin=row.origin,
        date_basis=row.date_basis,
        description=row.description,
        filters=filters,
        quality_flags=dict(row.quality_flags or {}),
        provider_names=provider_names,
        is_local_filter=is_local_filter,
        is_multi_provider=len(provider_ids) > 1,
        offer_types=[str(value) for value in (row.offer_types or [])],
        sort_mode=row.sort_mode,
        is_active=row.is_active,
        last_valid_snapshot_id=row.last_valid_snapshot_id,
        latest_snapshot=snapshot_summary(latest_snapshot) if latest_snapshot else None,
        last_valid_snapshot=snapshot_summary(valid_snapshot) if valid_snapshot else None,
    )
