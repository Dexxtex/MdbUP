"""Staggered acquisition of the JustWatch catalog.

JustWatch is a public endpoint with no rate limit to negotiate: the only safe
policy is a slow, predictable request rate. This module gives every active
JustWatch collection a fixed 15-minute slot of the Italian day
(``sha256(slug) % 96``), so the run of one acquisition never overlaps with the
next one and the whole catalog is refreshed about once a day without a burst at
midnight.

A collection is due when:

* it is an active collection fed by the ``justwatch`` source;
* it has no ``RUNNING`` snapshot (an acquisition is already in flight);
* its latest ``COMPLETE`` snapshot is missing or older than
  ``ACQUISITION_MAX_AGE_HOURS``;
* its latest attempt of any status is older than ``RETRY_BACKOFF_MINUTES``, so a
  failing collection cannot be retried on every tick and starve the others;
* it has no acquisition job still ``QUEUED``/``RUNNING`` (the tick runs every
  five minutes, the job may not have started yet);
* its slot for today has already started.

One tick enqueues at most one acquisition, in slot order, under a dedicated
Redis lock (``mdbup:justwatch:catalog-scheduler``): two scheduler instances can
never build two collections at the same time.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.locks import DispatchLock
from app.core.logging import get_logger
from app.core.time import ensure_utc, utcnow
from app.db.models import Collection, CollectionSnapshot, JobExecution, Provider, Source
from app.domain.enums import JobStatus, SnapshotStatus
from app.jobs.tasks import ACQUIRE_COLLECTION_TASK
from app.repositories import settings as settings_repo

logger = get_logger(__name__)

JUSTWATCH_SOURCE_KEY = "justwatch"
SCHEDULE_TIMEZONE = ZoneInfo("Europe/Rome")
SLOT_COUNT = 96
SLOT_MINUTES = 15
ACQUISITION_MAX_AGE_HOURS = 20
RETRY_BACKOFF_MINUTES = 60
UPCOMING_HORIZON_HOURS = 24
SCHEDULER_LOCK_NAMESPACE = "mdbup:justwatch"
SCHEDULER_LOCK_KEY = "catalog-scheduler"
SCHEDULER_LOCK_TTL_SECONDS = 900


@dataclass(frozen=True)
class CatalogAcquisition:
    """One upcoming acquisition of a JustWatch collection."""

    collection_id: uuid.UUID
    collection_slug: str
    collection_name: str
    provider_name: str
    next_acquire_at: datetime


@dataclass(frozen=True)
class CatalogScheduleOutcome:
    """Result of one scheduler tick."""

    due: int = 0
    enqueued: int = 0
    collection_id: uuid.UUID | None = None
    job_id: uuid.UUID | None = None
    reason: str | None = None


@dataclass(frozen=True)
class _CatalogRow:
    collection_id: uuid.UUID
    slug: str
    name: str
    provider_name: str
    last_complete_at: datetime | None
    last_attempt_at: datetime | None
    running: bool
    pending_job: bool


def slot_index(slug: str) -> int:
    """Deterministic 15-minute slot (0-95) of the day for a collection slug."""
    digest = hashlib.sha256(slug.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % SLOT_COUNT


def slot_start(slug: str, day: date) -> datetime:
    """UTC instant at which the collection's slot starts on an Italian day."""
    minutes = slot_index(slug) * SLOT_MINUTES
    local = datetime.combine(day, time(minutes // 60, minutes % 60), tzinfo=SCHEDULE_TIMEZONE)
    return local.astimezone(UTC)


def next_acquire_at(slug: str, now: datetime) -> datetime:
    """Next slot occurrence strictly after ``now``."""
    moment = ensure_utc(now)
    local_day = moment.astimezone(SCHEDULE_TIMEZONE).date()
    candidate = slot_start(slug, local_day)
    if candidate <= moment:
        candidate = slot_start(slug, local_day + timedelta(days=1))
    return candidate


def schedule_enabled(db: Session, settings: Settings) -> bool:
    """Effective value of the ``catalog_schedule_enabled`` runtime setting."""
    return bool(settings_repo.effective_values(db, settings)["catalog_schedule_enabled"])


def upcoming_acquisitions(
    db: Session,
    *,
    now: datetime | None = None,
    horizon_hours: int = UPCOMING_HORIZON_HOURS,
) -> list[CatalogAcquisition]:
    """Next acquisition per active JustWatch collection within the horizon."""
    moment = ensure_utc(now or utcnow())
    horizon = moment + timedelta(hours=horizon_hours)
    upcoming = [
        CatalogAcquisition(
            collection_id=row.collection_id,
            collection_slug=row.slug,
            collection_name=row.name,
            provider_name=row.provider_name,
            next_acquire_at=next_acquire_at(row.slug, moment),
        )
        for row in _catalog_rows(db)
    ]
    return sorted(
        (item for item in upcoming if item.next_acquire_at <= horizon),
        key=lambda item: (item.next_acquire_at, item.collection_slug),
    )


def enqueue_due_catalog_acquisitions(
    db: Session,
    settings: Settings,
    *,
    now: datetime | None = None,
    enqueue: Callable[[Session, Settings, uuid.UUID], JobExecution] | None = None,
) -> CatalogScheduleOutcome:
    """Enqueue at most one due acquisition, in slot order, under the Redis lock."""
    moment = ensure_utc(now or utcnow())
    if not schedule_enabled(db, settings):
        return CatalogScheduleOutcome(reason="DISABLED")
    due = [row for row in _catalog_rows(db) if _is_due(row, moment)]
    if not due:
        return CatalogScheduleOutcome(reason="NOTHING_DUE")
    due.sort(key=lambda row: (slot_index(row.slug), row.slug))
    selected = due[0]
    lock = DispatchLock(
        settings.redis_url,
        namespace=SCHEDULER_LOCK_NAMESPACE,
        ttl_seconds=SCHEDULER_LOCK_TTL_SECONDS,
    )
    token = lock.acquire(SCHEDULER_LOCK_KEY)
    if token is None:
        return CatalogScheduleOutcome(due=len(due), reason="SCHEDULER_LOCKED")
    try:
        # Re-checked under the lock: a previous tick may have just started it.
        if _has_running_snapshot(db, selected.collection_id):
            return CatalogScheduleOutcome(due=len(due), reason="ACQUISITION_RUNNING")
        dispatch = enqueue or _default_enqueue
        job = dispatch(db, settings, selected.collection_id)
    finally:
        lock.release(SCHEDULER_LOCK_KEY, token)
    logger.info(
        "catalog_acquisition_enqueued",
        collection_id=str(selected.collection_id),
        slug=selected.slug,
        due=len(due),
    )
    return CatalogScheduleOutcome(
        due=len(due),
        enqueued=1,
        collection_id=selected.collection_id,
        job_id=job.id,
    )


def _default_enqueue(db: Session, settings: Settings, collection_id: uuid.UUID) -> JobExecution:
    from app.jobs import tasks

    return tasks.enqueue_acquire_collection(db, settings, collection_id)


def _catalog_rows(db: Session) -> list[_CatalogRow]:
    source = db.scalar(select(Source).where(Source.key == JUSTWATCH_SOURCE_KEY))
    if source is None:
        return []
    collections = list(
        db.scalars(
            select(Collection)
            .where(Collection.source_id == source.id, Collection.is_active.is_(True))
            .order_by(Collection.slug)
        ).all()
    )
    if not collections:
        return []
    collection_ids = [collection.id for collection in collections]
    provider_names = {provider.id: provider.name for provider in db.scalars(select(Provider)).all()}
    completed_at = {
        collection_id: ensure_utc(moment)
        for collection_id, moment in db.execute(
            select(CollectionSnapshot.collection_id, func.max(CollectionSnapshot.started_at))
            .where(
                CollectionSnapshot.collection_id.in_(collection_ids),
                CollectionSnapshot.status == SnapshotStatus.COMPLETE.value,
            )
            .group_by(CollectionSnapshot.collection_id)
        ).all()
    }
    attempted_at = {
        collection_id: ensure_utc(moment)
        for collection_id, moment in db.execute(
            select(CollectionSnapshot.collection_id, func.max(CollectionSnapshot.started_at))
            .where(CollectionSnapshot.collection_id.in_(collection_ids))
            .group_by(CollectionSnapshot.collection_id)
        ).all()
    }
    running_ids = {
        str(collection_id)
        for collection_id in db.scalars(
            select(CollectionSnapshot.collection_id).where(
                CollectionSnapshot.collection_id.in_(collection_ids),
                CollectionSnapshot.status == SnapshotStatus.RUNNING.value,
            )
        ).all()
    }
    pending_jobs: set[str] = set(
        db.scalars(
            select(JobExecution.payload["collection_id"].as_string()).where(
                JobExecution.task_name == ACQUIRE_COLLECTION_TASK,
                JobExecution.status.in_((JobStatus.QUEUED.value, JobStatus.RUNNING.value)),
            )
        ).all()
    )
    return [
        _CatalogRow(
            collection_id=collection.id,
            slug=collection.slug,
            name=collection.name,
            provider_name=provider_names.get(collection.provider_id, ""),
            last_complete_at=completed_at.get(collection.id),
            last_attempt_at=attempted_at.get(collection.id),
            running=str(collection.id) in running_ids,
            pending_job=str(collection.id) in pending_jobs,
        )
        for collection in collections
    ]


def _is_due(row: _CatalogRow, moment: datetime) -> bool:
    if row.running or row.pending_job:
        return False
    if row.last_complete_at is not None and row.last_complete_at >= moment - timedelta(
        hours=ACQUISITION_MAX_AGE_HOURS
    ):
        return False
    if row.last_attempt_at is not None and row.last_attempt_at >= moment - timedelta(
        minutes=RETRY_BACKOFF_MINUTES
    ):
        return False
    local_day = moment.astimezone(SCHEDULE_TIMEZONE).date()
    return slot_start(row.slug, local_day) <= moment


def _has_running_snapshot(db: Session, collection_id: uuid.UUID) -> bool:
    return (
        db.scalar(
            select(CollectionSnapshot.id).where(
                CollectionSnapshot.collection_id == collection_id,
                CollectionSnapshot.status == SnapshotStatus.RUNNING.value,
            )
        )
        is not None
    )
