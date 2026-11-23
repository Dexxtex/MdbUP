"""Delete local collections and their dependent history.

Remote MDBList lists are never contacted here: only local snapshots, bindings
and run history are removed. The explicit delete order keeps the FKs valid on
both SQLite and PostgreSQL, where some references (episode events and runs to
snapshots) have no ON DELETE action.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from app.db.models import (
    Collection,
    CollectionSnapshot,
    EpisodeEvent,
    SnapshotItem,
    SyncBinding,
    SyncOperation,
    SyncRun,
    SyncRunEvent,
)
from app.domain.enums import ACTIVE_RUN_STATUSES
from app.domain.errors import ConflictError


@dataclass(frozen=True)
class CollectionCleanupStats:
    collections: int
    snapshots: int
    bindings: int
    runs: int


def collect_local_data(
    db: Session, collection_ids: list[uuid.UUID]
) -> tuple[list[uuid.UUID], list[uuid.UUID]]:
    """Return the snapshot and binding ids that belong to the collections."""
    if not collection_ids:
        return [], []
    snapshot_ids = list(
        db.scalars(
            select(CollectionSnapshot.id).where(
                CollectionSnapshot.collection_id.in_(collection_ids)
            )
        )
    )
    binding_ids = list(
        db.scalars(select(SyncBinding.id).where(SyncBinding.collection_id.in_(collection_ids)))
    )
    return snapshot_ids, binding_ids


def ensure_no_active_runs(
    db: Session,
    binding_ids: list[uuid.UUID],
    *,
    code: str,
    message: str,
    details: dict[str, object],
) -> None:
    """Refuse deletion while a binding has a run that is still writing."""
    if not binding_ids:
        return
    active_statuses = [status.value for status in ACTIVE_RUN_STATUSES]
    active_runs = db.scalar(
        select(func.count())
        .select_from(SyncRun)
        .where(
            SyncRun.binding_id.in_(binding_ids),
            SyncRun.status.in_(active_statuses),
        )
    )
    if active_runs:
        raise ConflictError(
            message,
            code=code,
            details={**details, "active_runs": int(active_runs)},
        )


def delete_local_data(
    db: Session,
    *,
    collection_ids: list[uuid.UUID],
    snapshot_ids: list[uuid.UUID],
    binding_ids: list[uuid.UUID],
) -> CollectionCleanupStats:
    """Delete collections and all their local dependent rows."""
    run_ids: list[uuid.UUID] = []
    run_condition = None
    if binding_ids and snapshot_ids:
        run_condition = or_(
            SyncRun.binding_id.in_(binding_ids),
            SyncRun.snapshot_id.in_(snapshot_ids),
        )
    elif binding_ids:
        run_condition = SyncRun.binding_id.in_(binding_ids)
    elif snapshot_ids:
        run_condition = SyncRun.snapshot_id.in_(snapshot_ids)
    if run_condition is not None:
        run_ids = list(db.scalars(select(SyncRun.id).where(run_condition)))

    if run_ids:
        # Child runs may reference a run that is about to be deleted.
        db.execute(
            update(SyncRun).where(SyncRun.parent_run_id.in_(run_ids)).values(parent_run_id=None)
        )
        db.execute(delete(SyncRunEvent).where(SyncRunEvent.run_id.in_(run_ids)))
        db.execute(delete(SyncOperation).where(SyncOperation.run_id.in_(run_ids)))
        db.execute(delete(SyncRun).where(SyncRun.id.in_(run_ids)))

    if snapshot_ids:
        db.execute(
            update(EpisodeEvent)
            .where(EpisodeEvent.snapshot_id.in_(snapshot_ids))
            .values(snapshot_id=None)
        )
        db.execute(
            update(CollectionSnapshot)
            .where(CollectionSnapshot.items_from_snapshot_id.in_(snapshot_ids))
            .values(items_from_snapshot_id=None)
        )
        db.execute(
            update(Collection)
            .where(Collection.last_valid_snapshot_id.in_(snapshot_ids))
            .values(last_valid_snapshot_id=None)
        )
        db.execute(delete(SnapshotItem).where(SnapshotItem.snapshot_id.in_(snapshot_ids)))
        db.execute(delete(CollectionSnapshot).where(CollectionSnapshot.id.in_(snapshot_ids)))

    if binding_ids:
        db.execute(delete(SyncBinding).where(SyncBinding.id.in_(binding_ids)))
    if collection_ids:
        db.execute(delete(Collection).where(Collection.id.in_(collection_ids)))

    return CollectionCleanupStats(
        collections=len(collection_ids),
        snapshots=len(snapshot_ids),
        bindings=len(binding_ids),
        runs=len(run_ids),
    )
