"""Snapshot read models: summary and paginated items."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.errors import NotFoundError
from app.db.models import CollectionSnapshot, Media, SnapshotItem
from app.repositories import snapshots as snapshots_repo


@dataclass(frozen=True)
class SnapshotSummary:
    id: uuid.UUID
    status: str
    quality: str
    is_valid: bool
    started_at: datetime
    finished_at: datetime | None
    pages_expected: int | None
    pages_fetched: int
    items_count: int
    resolved_count: int
    unresolved_count: int
    duplicate_count: int
    error_count: int
    checksum: str | None
    invalid_reason: str | None
    last_verified_at: datetime | None


@dataclass(frozen=True)
class SnapshotItemView:
    position: int
    media_id: uuid.UUID | None
    media_type: str | None
    tmdb_id: int | None
    imdb_id: str | None
    title: str | None
    release_year: int | None
    resolution_status: str
    resolution_error: str | None
    source_item_id: str | None
    date_basis: str
    source_date_created: date | None
    availability_status: str | None
    source_offer_types: list[str]


def snapshot_summary(snapshot: CollectionSnapshot) -> SnapshotSummary:
    return SnapshotSummary(
        id=snapshot.id,
        status=snapshot.status,
        quality=snapshot.quality,
        is_valid=snapshot.is_valid,
        started_at=snapshot.started_at,
        finished_at=snapshot.finished_at,
        pages_expected=snapshot.pages_expected,
        pages_fetched=snapshot.pages_fetched,
        items_count=snapshot.items_count,
        resolved_count=snapshot.resolved_count,
        unresolved_count=snapshot.unresolved_count,
        duplicate_count=snapshot.duplicate_count,
        error_count=snapshot.error_count,
        checksum=snapshot.checksum,
        invalid_reason=snapshot.invalid_reason,
        last_verified_at=snapshot.last_verified_at,
    )


def get_snapshot_summary(db: Session, snapshot_id: uuid.UUID) -> SnapshotSummary:
    snapshot = snapshots_repo.get_snapshot(db, snapshot_id)
    if snapshot is None:
        raise NotFoundError("Snapshot non trovato.", details={"snapshot_id": str(snapshot_id)})
    return snapshot_summary(snapshot)


def _offer_types(payload: dict[str, object]) -> list[str]:
    """Offer types the source reported for the item (empty when it declares none)."""
    raw = payload.get("_offer_types")
    if not isinstance(raw, (list, tuple)):
        return []
    return [str(value) for value in raw if str(value).strip()]


def list_snapshot_items(
    db: Session,
    snapshot_id: uuid.UUID,
    *,
    page: int = 1,
    page_size: int = 50,
    search: str | None = None,
) -> tuple[list[SnapshotItemView], int]:
    """Paginated items, optionally filtered by a case-insensitive title match.

    ``search`` matches ``Media.title`` only: provider and offer metadata are not
    searched, and unresolved items (no media row) never match.
    """
    snapshot = snapshots_repo.get_snapshot(db, snapshot_id)
    if snapshot is None:
        raise NotFoundError("Snapshot non trovato.", details={"snapshot_id": str(snapshot_id)})
    items_snapshot_id = snapshots_repo.items_snapshot_id(db, snapshot)
    term = (search or "").strip()
    offset = (page - 1) * page_size
    stmt = (
        select(SnapshotItem, Media)
        .outerjoin(Media, SnapshotItem.media_id == Media.id)
        .where(SnapshotItem.snapshot_id == items_snapshot_id)
        .order_by(SnapshotItem.position)
        .limit(page_size)
        .offset(offset)
    )
    count_stmt = (
        select(func.count())
        .select_from(SnapshotItem)
        .outerjoin(Media, SnapshotItem.media_id == Media.id)
        .where(SnapshotItem.snapshot_id == items_snapshot_id)
    )
    if term:
        title_matches = Media.title.icontains(term, autoescape=True)
        stmt = stmt.where(title_matches)
        count_stmt = count_stmt.where(title_matches)
    views: list[SnapshotItemView] = []
    for item, media in db.execute(stmt).all():
        payload = item.source_payload or {}
        views.append(
            SnapshotItemView(
                position=item.position,
                media_id=item.media_id,
                media_type=media.media_type if media is not None else None,
                tmdb_id=media.tmdb_id if media is not None else None,
                imdb_id=media.imdb_id if media is not None else None,
                title=media.title if media is not None else None,
                release_year=media.release_year if media is not None else None,
                resolution_status=item.resolution_status,
                resolution_error=item.resolution_error,
                source_item_id=item.source_item_id,
                date_basis=item.date_basis,
                source_date_created=item.source_date_created,
                availability_status=item.availability_status,
                source_offer_types=_offer_types(payload),
            )
        )
    total = int(db.scalar(count_stmt) or 0)
    return views, total
