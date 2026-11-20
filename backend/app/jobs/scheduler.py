"""Periodic work: enqueue due bindings and apply the retention policy.

The scheduler is idempotent per slot: it advances ``next_run_at`` before
dispatching, so a second tick cannot create a duplicate run for the same slot.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import and_, delete, or_, select, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.locks import build_dispatch_lock, sweep_orphan_dispatch_locks
from app.core.logging import get_logger
from app.core.time import ensure_utc, utcnow
from app.db.models import (
    Collection,
    CollectionSnapshot,
    JobExecution,
    SyncBinding,
    SyncRun,
    UserSession,
)
from app.domain.enums import (
    ACTIVE_RUN_STATUSES,
    JobStatus,
    SchedulePolicy,
    SyncMode,
    SyncRunStatus,
)
from app.repositories import bindings as bindings_repo
from app.repositories import collections as collections_repo
from app.repositories import runs as runs_repo
from app.repositories import snapshots as snapshots_repo
from app.services.bindings import compute_next_run_at
from app.services.collections import is_justwatch_collection

logger = get_logger(__name__)

STALE_RUN_MINUTES = 30
_FAILED_RUN_STATUSES = (
    SyncRunStatus.BLOCKED.value,
    SyncRunStatus.CANCELLED.value,
    SyncRunStatus.FAILED.value,
    SyncRunStatus.PARTIAL.value,
)


@dataclass(frozen=True)
class SchedulerOutcome:
    enqueued: int = 0
    skipped: int = 0
    run_ids: list[uuid.UUID] = field(default_factory=list)


def enqueue_due_bindings(
    db: Session,
    settings: Settings,
    *,
    now: datetime | None = None,
    dispatch: bool = True,
) -> SchedulerOutcome:
    """Create one run per due binding and advance ``next_run_at``."""
    moment = ensure_utc(now or utcnow())
    due = bindings_repo.list_due_bindings(db, now=moment)
    enqueued = 0
    skipped = 0
    run_ids: list[uuid.UUID] = []
    dispatch_lock = build_dispatch_lock(settings.redis_url)
    target_owner = target_binding_owner(bindings_repo.list_bindings(db, enabled=True))
    for binding in due:
        token = dispatch_lock.acquire(f"target:{binding.target_id}")
        if token is None:
            # Another scheduler/manual request is preparing a run for this target.
            skipped += 1
            continue
        try:
            next_run_at: datetime | None
            if binding.schedule_interval_hours is not None:
                next_run_at = moment + timedelta(hours=binding.schedule_interval_hours)
            else:
                next_run_at = compute_next_run_at(
                    binding.schedule_cron, binding.timezone, now=moment
                )
            bindings_repo.set_next_run_at(db, binding, next_run_at)
            owner_id = target_owner.get(binding.target_id)
            if owner_id is not None and owner_id != binding.id:
                # The API refuses a second enabled binding per target; a legacy
                # or imported row must never get a scheduled run of its own.
                logger.warning(
                    "scheduler_target_binding_conflict",
                    target_id=str(binding.target_id),
                    binding_id=str(binding.id),
                    owner_binding_id=str(owner_id),
                )
                skipped += 1
                db.commit()
                continue
            if (
                runs_repo.get_active_run_for_binding(db, binding.id) is not None
                or runs_repo.get_active_run_for_target(db, binding.target_id) is not None
            ):
                skipped += 1
                db.commit()
                continue
            collection = collections_repo.get_collection(db, binding.collection_id)
            # JustWatch is an aggregator: it may feed snapshots/previews, but it
            # never triggers an automatic MDBList sync. A real run remains a
            # manual action after the required dry-run.
            if collection is not None and is_justwatch_collection(db, collection):
                logger.info(
                    "scheduler_skips_justwatch_automatic_sync",
                    binding_id=str(binding.id),
                    collection_id=str(collection.id),
                )
                skipped += 1
                db.commit()
                continue
            snapshot = _scheduled_snapshot(db, binding.collection_id, binding.mode)
            if collection is None or snapshot is None:
                skipped += 1
                db.commit()
                continue
            dry_run = binding.schedule_policy == SchedulePolicy.DRY_RUN_ONLY.value
            slot = moment.replace(second=0, microsecond=0).isoformat()
            run = runs_repo.create_run(
                db,
                binding_id=binding.id,
                target_id=binding.target_id,
                media_type=binding.media_type,
                snapshot_id=snapshot.id,
                mode=binding.mode,
                trigger_type="SCHEDULED",
                is_dry_run=dry_run,
                summary={"idempotency_key": f"schedule:{binding.id}:{slot}"},
            )
            bindings_repo.set_last_run(db, binding, run.id)
            db.commit()
            run_ids.append(run.id)
            enqueued += 1
            if dispatch:
                from app.jobs import tasks

                try:
                    tasks.enqueue_sync_run(db, settings, run.id)
                except Exception as exc:  # Celery unavailable: do not leave a PENDING run
                    logger.error(
                        "scheduler_dispatch_failed",
                        binding_id=str(binding.id),
                        run_id=str(run.id),
                        error=type(exc).__name__,
                    )
                    runs_repo.finish_run(
                        db,
                        run,
                        SyncRunStatus.FAILED,
                        error_code="CELERY_UNAVAILABLE",
                        error_message="Invio del task a Celery non riuscito.",
                    )
                    db.commit()
                    skipped += 1
                    enqueued -= 1
                    run_ids.remove(run.id)
        except Exception as exc:
            db.rollback()
            logger.error(
                "scheduler_binding_failed",
                binding_id=str(binding.id),
                error=type(exc).__name__,
            )
            skipped += 1
        finally:
            dispatch_lock.release(f"target:{binding.target_id}", token)
    return SchedulerOutcome(enqueued=enqueued, skipped=skipped, run_ids=run_ids)


def target_binding_owner(bindings: Iterable[SyncBinding]) -> dict[uuid.UUID, uuid.UUID]:
    """Enabled binding that owns each target: the oldest row wins.

    The database already refuses two enabled bindings per target (partial unique
    index) and the API raises ``TARGET_LOCKED`` before writing; this is the last
    line of defence for rows imported or restored by hand.
    """
    owners: dict[uuid.UUID, SyncBinding] = {}
    for binding in bindings:
        current = owners.get(binding.target_id)
        if current is None or (binding.created_at, str(binding.id)) < (
            current.created_at,
            str(current.id),
        ):
            owners[binding.target_id] = binding
    return {target_id: binding.id for target_id, binding in owners.items()}


def _scheduled_snapshot(
    db: Session, collection_id: uuid.UUID, mode: str
) -> CollectionSnapshot | None:
    collection = collections_repo.get_collection(db, collection_id)
    if collection is None:
        return None
    if collection.last_valid_snapshot_id is not None:
        snapshot = snapshots_repo.get_snapshot(db, collection.last_valid_snapshot_id)
        if snapshot is not None:
            return snapshot
    valid = snapshots_repo.latest_snapshots_for(db, [collection_id], valid_only=True)
    if collection_id in valid:
        return valid[collection_id]
    if mode == SyncMode.APPEND_ONLY.value:
        for candidate in snapshots_repo.list_snapshots(db, collection_id, limit=50):
            if candidate.status == "COMPLETE" and candidate.items_count > 0:
                return candidate
    return None


def sweep_stale_runs(
    db: Session,
    settings: Settings,
    *,
    now: datetime | None = None,
    older_than_minutes: int = STALE_RUN_MINUTES,
) -> dict[str, int]:
    """Recover active runs left behind by a worker crash.

    ``APPLYING``/``VERIFYING`` runs are moved to ``VERIFYING`` and re-enqueued
    for reconciliation; earlier states are failed because nothing was written.
    """
    moment = ensure_utc(now or utcnow())
    cutoff = moment - timedelta(minutes=older_than_minutes)
    active_values = tuple(status.value for status in ACTIVE_RUN_STATUSES)
    stale = list(
        db.scalars(
            select(SyncRun).where(
                SyncRun.status.in_(active_values),
                SyncRun.updated_at < cutoff,
            )
        ).all()
    )
    reconciled = 0
    failed = 0
    for run in stale:
        if run.status in {
            SyncRunStatus.APPLYING.value,
            SyncRunStatus.VERIFYING.value,
        }:
            runs_repo.transition_run(db, run, SyncRunStatus.VERIFYING, message="stale sweep")
            db.commit()
            from app.jobs import tasks

            try:
                tasks.enqueue_sync_run(db, settings, run.id, reconcile=True)
            except Exception:
                runs_repo.finish_run(
                    db,
                    run,
                    SyncRunStatus.FAILED,
                    error_code="CELERY_UNAVAILABLE",
                    error_message="Sweep: invio riconciliazione non riuscito.",
                )
                db.commit()
                failed += 1
            else:
                reconciled += 1
        else:
            runs_repo.finish_run(
                db,
                run,
                SyncRunStatus.FAILED,
                error_code="STALE_RUN",
                error_message="Run non terminale troppo vecchio: marcato fallito.",
            )
            db.commit()
            failed += 1
    logger.info("sweep_stale_runs", reconciled=reconciled, failed=failed)
    return {"reconciled": reconciled, "failed": failed}


def sweep_orphan_locks(db: Session, settings: Settings) -> dict[str, int]:
    """Remove Redis dispatch locks that have no active run behind them."""

    def is_active(raw_target_id: str) -> bool:
        try:
            target_id = uuid.UUID(raw_target_id)
        except ValueError:
            return False
        return runs_repo.get_active_run_for_target(db, target_id) is not None

    removed = sweep_orphan_dispatch_locks(settings.redis_url, is_active=is_active)
    logger.info("sweep_orphan_locks", removed=removed)
    return {"removed": removed}


def cleanup_old_data(
    db: Session, settings: Settings, *, now: datetime | None = None
) -> dict[str, int]:
    """Apply the retention policy without touching non-terminal or protected rows."""
    moment = ensure_utc(now or utcnow())
    succeeded_cutoff = moment - timedelta(days=settings.run_retention_days)
    failed_cutoff = moment - timedelta(days=settings.failed_run_retention_days)
    job_cutoff = moment - timedelta(days=settings.job_retention_days)
    session_cutoff = moment - timedelta(days=settings.session_retention_days)
    snapshot_cutoff = moment - timedelta(days=settings.snapshot_retention_days)

    runs_to_delete = select(SyncRun.id).where(
        or_(
            and_(
                SyncRun.status == SyncRunStatus.SUCCEEDED.value,
                SyncRun.finished_at.is_not(None),
                SyncRun.finished_at < succeeded_cutoff,
            ),
            and_(
                SyncRun.status.in_(_FAILED_RUN_STATUSES),
                SyncRun.finished_at.is_not(None),
                SyncRun.finished_at < failed_cutoff,
            ),
        )
    )
    db.execute(
        update(SyncBinding)
        .where(SyncBinding.last_run_id.in_(runs_to_delete))
        .values(last_run_id=None)
    )
    runs_result = db.execute(delete(SyncRun).where(SyncRun.id.in_(runs_to_delete)))
    runs_deleted = int(getattr(runs_result, "rowcount", 0) or 0)
    jobs_result = db.execute(
        delete(JobExecution).where(
            JobExecution.finished_at.is_not(None),
            JobExecution.finished_at < job_cutoff,
            JobExecution.status.in_(
                (JobStatus.SUCCEEDED.value, JobStatus.FAILED.value, JobStatus.CANCELLED.value)
            ),
        )
    )
    jobs_deleted = int(getattr(jobs_result, "rowcount", 0) or 0)
    sessions_result = db.execute(delete(UserSession).where(UserSession.expires_at < session_cutoff))
    sessions_deleted = int(getattr(sessions_result, "rowcount", 0) or 0)

    referenced = select(SyncRun.snapshot_id)
    protected = select(Collection.last_valid_snapshot_id).where(
        Collection.last_valid_snapshot_id.is_not(None)
    )
    # A duplicate verification points at the snapshot that owns its items: the
    # owning snapshot must survive until the last pointer is gone.
    items_referenced = select(CollectionSnapshot.items_from_snapshot_id).where(
        CollectionSnapshot.items_from_snapshot_id.is_not(None)
    )
    snapshots_result = db.execute(
        delete(CollectionSnapshot).where(
            CollectionSnapshot.status != "RUNNING",
            CollectionSnapshot.started_at < snapshot_cutoff,
            CollectionSnapshot.id.not_in(referenced),
            CollectionSnapshot.id.not_in(protected),
            CollectionSnapshot.id.not_in(items_referenced),
        )
    )
    snapshots_deleted = int(getattr(snapshots_result, "rowcount", 0) or 0)
    db.commit()
    result = {
        "runs_deleted": int(runs_deleted),
        "jobs_deleted": int(jobs_deleted),
        "sessions_deleted": int(sessions_deleted),
        "snapshots_deleted": int(snapshots_deleted),
    }
    logger.info("cleanup_old_data", **result)
    return result
