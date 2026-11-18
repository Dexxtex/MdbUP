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
    )


def get_snapshot_summary(db: Session, snapshot_id: uuid.UUID) -> SnapshotSummary:
    snapshot = snapshots_repo.get_snapshot(db, snapshot_id)
    if snapshot is None:
        raise NotFoundError("Snapshot non trovato.", details={"snapshot_id": str(snapshot_id)})
    return snapshot_summary(snapshot)


def list_snapshot_items(
    db: Session,
    snapshot_id: uuid.UUID,
    *,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[SnapshotItemView], int]:
    if snapshots_repo.get_snapshot(db, snapshot_id) is None:
        raise NotFoundError("Snapshot non trovato.", details={"snapshot_id": str(snapshot_id)})
    offset = (page - 1) * page_size
    stmt = (
        select(SnapshotItem, Media)
        .outerjoin(Media, SnapshotItem.media_id == Media.id)
        .where(SnapshotItem.snapshot_id == snapshot_id)
        .order_by(SnapshotItem.position)
        .limit(page_size)
        .offset(offset)
    )
    views: list[SnapshotItemView] = []
    for item, media in db.execute(stmt).all():
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
            )
        )
    total = int(
        db.scalar(
            select(func.count())
            .select_from(SnapshotItem)
            .where(SnapshotItem.snapshot_id == snapshot_id)
        )
        or 0
    )
    return views, total
