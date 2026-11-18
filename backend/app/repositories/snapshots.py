"""Immutable collection snapshots and their items."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import CollectionSnapshot, SnapshotItem
from app.domain.enums import SnapshotStatus


def create_running_snapshot(
    db: Session,
    collection_id: uuid.UUID,
    *,
    job_execution_id: uuid.UUID | None = None,
) -> CollectionSnapshot:
    snapshot = CollectionSnapshot(
        collection_id=collection_id,
        status=SnapshotStatus.RUNNING.value,
        job_execution_id=job_execution_id,
    )
    db.add(snapshot)
    db.flush()
    return snapshot


def get_snapshot(db: Session, snapshot_id: uuid.UUID) -> CollectionSnapshot | None:
    return db.get(CollectionSnapshot, snapshot_id)


def items_snapshot_id(db: Session, snapshot: CollectionSnapshot) -> uuid.UUID:
    """Resolve the snapshot that physically owns the items.

    A verification identical to the previous valid snapshot stores a pointer
    instead of copying every item. Follow the pointer chain defensively: a
    missing/self-referential pointer falls back to the current snapshot.
    """
    current = snapshot
    seen: set[uuid.UUID] = set()
    while current.items_from_snapshot_id is not None and current.id not in seen:
        seen.add(current.id)
        parent = db.get(CollectionSnapshot, current.items_from_snapshot_id)
        if parent is None or parent.id in seen:
            break
        current = parent
    return current.id


def get_running_snapshot(db: Session, collection_id: uuid.UUID) -> CollectionSnapshot | None:
    return db.scalar(
        select(CollectionSnapshot).where(
            CollectionSnapshot.collection_id == collection_id,
            CollectionSnapshot.status == SnapshotStatus.RUNNING.value,
        )
    )


def list_snapshots(
    db: Session,
    collection_id: uuid.UUID,
    *,
    limit: int = 50,
    offset: int = 0,
) -> list[CollectionSnapshot]:
    stmt = (
        select(CollectionSnapshot)
        .where(CollectionSnapshot.collection_id == collection_id)
        .order_by(CollectionSnapshot.started_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(db.scalars(stmt).all())


def count_snapshots(db: Session, collection_id: uuid.UUID) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(CollectionSnapshot)
            .where(CollectionSnapshot.collection_id == collection_id)
        )
        or 0
    )


def latest_snapshots_for(
    db: Session,
    collection_ids: Sequence[uuid.UUID],
    *,
    valid_only: bool = False,
) -> dict[uuid.UUID, CollectionSnapshot]:
    """Most recent snapshot per collection (optionally only valid ones)."""
    if not collection_ids:
        return {}
    stmt = (
        select(CollectionSnapshot)
        .where(CollectionSnapshot.collection_id.in_(collection_ids))
        .order_by(CollectionSnapshot.started_at.desc())
    )
    if valid_only:
        stmt = stmt.where(CollectionSnapshot.is_valid.is_(True))
    latest: dict[uuid.UUID, CollectionSnapshot] = {}
    for snapshot in db.scalars(stmt).all():
        latest.setdefault(snapshot.collection_id, snapshot)
    return latest


def add_item(
    db: Session,
    snapshot: CollectionSnapshot,
    *,
    position: int,
    media_id: uuid.UUID | None,
    source_item_id: str | None,
    source_payload: dict[str, Any],
    source_date_created: date | None,
    date_basis: str,
    resolution_status: str,
    resolution_error: str | None = None,
    availability_status: str | None = None,
) -> SnapshotItem:
    item = SnapshotItem(
        snapshot_id=snapshot.id,
        media_id=media_id,
        position=position,
        source_item_id=source_item_id,
        source_payload=source_payload,
        source_date_created=source_date_created,
        date_basis=date_basis,
        resolution_status=resolution_status,
        resolution_error=resolution_error,
        availability_status=availability_status,
    )
    db.add(item)
    return item


def count_by_status(db: Session) -> dict[str, int]:
    stmt = select(CollectionSnapshot.status, func.count()).group_by(CollectionSnapshot.status)
    return {status: int(total) for status, total in db.execute(stmt).all()}


def count_valid(db: Session) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(CollectionSnapshot)
            .where(CollectionSnapshot.is_valid.is_(True))
        )
        or 0
    )


def recent(db: Session, *, limit: int = 5) -> Sequence[CollectionSnapshot]:
    return list(
        db.scalars(
            select(CollectionSnapshot).order_by(CollectionSnapshot.started_at.desc()).limit(limit)
        ).all()
    )
