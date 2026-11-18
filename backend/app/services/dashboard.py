"""Dashboard aggregate: counters, alerts and recent activity."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from math import ceil
from typing import Any

from croniter import croniter
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.metrics import api_usage_snapshot
from app.core.time import ensure_utc, utcnow
from app.db.models import (
    Collection,
    CollectionSnapshot,
    JobExecution,
    Source,
    SyncBinding,
    SyncRun,
)
from app.domain.enums import JobStatus, SourceStatus, SyncRunStatus
from app.domain.errors import AppError
from app.repositories import collections as collections_repo
from app.repositories import media as media_repo
from app.repositories import providers as providers_repo
from app.repositories import snapshots as snapshots_repo
from app.repositories import sources as sources_repo
from app.services import credentials as credentials_service
from app.services.credentials import CredentialKind


@dataclass(frozen=True)
class DashboardAlert:
    code: str
    severity: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DashboardSummary:
    counters: dict[str, int]
    alerts: list[DashboardAlert]
    recent_snapshots: list[dict[str, Any]]
    recent_jobs: list[dict[str, Any]]
    recent_sync_runs: list[dict[str, Any]]
    sources: list[dict[str, Any]]
    api_usage: dict[str, Any]


def get_dashboard(db: Session, settings: Settings) -> DashboardSummary:
    sources = sources_repo.list_sources(db)
    collections = collections_repo.list_collections(db)
    latest_snapshots = snapshots_repo.latest_snapshots_for(
        db, [collection.id for collection in collections]
    )
    snapshot_status_counts = snapshots_repo.count_by_status(db)
    job_counts = _job_counts(db)
    run_counts = _run_counts(db)
    counters = {
        "providers": len(providers_repo.list_providers(db)),
        "collections": len(collections),
        "active_collections": sum(1 for collection in collections if collection.is_active),
        "media": media_repo.count_media(db),
        "snapshots": sum(snapshot_status_counts.values()),
        "valid_snapshots": snapshots_repo.count_valid(db),
        "running_snapshots": snapshot_status_counts.get("RUNNING", 0),
        "sources_total": len(sources),
        "sources_ok": sum(1 for source in sources if source.status == SourceStatus.OK.value),
        "sources_unconfigured": sum(
            1 for source in sources if source.status == SourceStatus.UNCONFIGURED.value
        ),
        "sources_disabled": sum(
            1 for source in sources if source.status == SourceStatus.DISABLED.value
        ),
        "jobs_queued": job_counts.get(JobStatus.QUEUED.value, 0),
        "jobs_running": job_counts.get(JobStatus.RUNNING.value, 0),
        "jobs_failed": job_counts.get(JobStatus.FAILED.value, 0),
        "sync_runs_total": sum(run_counts.values()),
        "sync_runs_active": sum(
            run_counts.get(status.value, 0)
            for status in (
                SyncRunStatus.PENDING,
                SyncRunStatus.PREFLIGHT,
                SyncRunStatus.PLANNING,
                SyncRunStatus.AWAITING_APPROVAL,
                SyncRunStatus.APPLYING,
                SyncRunStatus.VERIFYING,
            )
        ),
    }
    alerts = _alerts(db, settings, sources, collections, latest_snapshots)
    return DashboardSummary(
        counters=counters,
        alerts=alerts,
        recent_snapshots=_recent_snapshots(db),
        recent_jobs=_recent_jobs(db),
        recent_sync_runs=_recent_sync_runs(db),
        sources=[
            {
                "id": str(source.id),
                "key": source.key,
                "name": source.name,
                "status": source.status,
                "status_message": source.status_message,
                "last_healthcheck_at": source.last_healthcheck_at,
            }
            for source in sources
        ],
        api_usage=_api_usage(db, sources),
    )


def _runs_per_day(binding: SyncBinding) -> float:
    if binding.schedule_interval_hours:
        return 24.0 / max(1, int(binding.schedule_interval_hours))
    if not binding.schedule_cron:
        return 0.0
    now = ensure_utc(utcnow())
    try:
        iterator = croniter(binding.schedule_cron, now)
    except Exception:
        return 0.0
    count = 0
    for _ in range(1000):
        next_run = ensure_utc(iterator.get_next(datetime))
        if next_run > now + timedelta(days=1):
            break
        count += 1
    return float(count)


def _api_usage(db: Session, sources: list[Source]) -> dict[str, Any]:
    source_key = {source.id: source.key for source in sources}
    bindings = list(db.scalars(select(SyncBinding).where(SyncBinding.is_enabled.is_(True))).all())
    tmdb_per_day = 0.0
    mdblist_per_day = 0.0
    for binding in bindings:
        runs = _runs_per_day(binding)
        if runs <= 0:
            continue
        collection = db.get(Collection, binding.collection_id)
        if collection is None:
            continue
        snapshot = None
        if collection.last_valid_snapshot_id is not None:
            snapshot = snapshots_repo.get_snapshot(db, collection.last_valid_snapshot_id)
        item_count = snapshot.items_count if snapshot is not None else 0
        filters = collection.filters or {}
        derived = bool(filters.get("derivation") or filters.get("shared_snapshot_collection_id"))
        if source_key.get(collection.source_id) == "tmdb" and not derived:
            tmdb_per_day += runs * max(1, ceil(item_count / 20))
        mdblist_per_day += runs * max(1, ceil(item_count / 100)) * 3
    actual = api_usage_snapshot()
    return {
        "tmdb": {
            **actual["tmdb"],
            "estimated_per_hour": round(tmdb_per_day / 24, 2),
            "estimated_per_day": round(tmdb_per_day, 2),
        },
        "mdblist": {
            **actual["mdblist"],
            "estimated_per_hour": round(mdblist_per_day / 24, 2),
            "estimated_per_day": round(mdblist_per_day, 2),
        },
        "active_bindings": len(bindings),
    }


def _alerts(
    db: Session,
    settings: Settings,
    sources: list[Source],
    collections: list[Collection],
    latest_snapshots: dict[Any, CollectionSnapshot],
) -> list[DashboardAlert]:
    alerts: list[DashboardAlert] = []
    for source in sources:
        if source.status == SourceStatus.UNCONFIGURED.value:
            alerts.append(
                DashboardAlert(
                    code="SOURCE_UNCONFIGURED",
                    severity="warning",
                    message=f"Fonte '{source.name}' non configurata.",
                    details={"source_key": source.key},
                )
            )
        elif source.status == SourceStatus.DISABLED.value:
            alerts.append(
                DashboardAlert(
                    code="SOURCE_DISABLED",
                    severity="info",
                    message=(
                        f"Fonte '{source.name}' disabilitata: "
                        f"{source.status_message or 'non attiva'}."
                    ),
                    details={"source_key": source.key},
                )
            )
    if not _tmdb_credential_configured(db, settings):
        alerts.append(
            DashboardAlert(
                code="CREDENTIAL_MISSING",
                severity="error",
                message="Credenziale TMDb non configurata: le acquisizioni sono bloccate.",
                details={"kind": CredentialKind.TMDB.value},
            )
        )
    invalid = [
        collection
        for collection in collections
        if (snapshot := latest_snapshots.get(collection.id)) is not None
        and not snapshot.is_valid
        and snapshot.invalid_reason != "baseline_empty"
    ]
    baseline_pending = [
        collection
        for collection in collections
        if (snapshot := latest_snapshots.get(collection.id)) is not None
        and snapshot.invalid_reason == "baseline_empty"
    ]
    if baseline_pending:
        alerts.append(
            DashboardAlert(
                code="BASELINE_PENDING",
                severity="info",
                message=(
                    f"{len(baseline_pending)} collezioni 'Appena rilevati' sono in attesa "
                    "della prima osservazione successiva alla baseline."
                ),
                details={"collections": [collection.slug for collection in baseline_pending[:10]]},
            )
        )
    if invalid:
        alerts.append(
            DashboardAlert(
                code="INVALID_SNAPSHOTS",
                severity="warning",
                message=f"{len(invalid)} collezioni hanno l'ultimo snapshot non valido.",
                details={"collections": [collection.slug for collection in invalid[:10]]},
            )
        )
    missing = [collection for collection in collections if collection.id not in latest_snapshots]
    if missing:
        alerts.append(
            DashboardAlert(
                code="COLLECTIONS_WITHOUT_SNAPSHOT",
                severity="info",
                message=f"{len(missing)} collezioni non sono mai state acquisite.",
                details={"collections": [collection.slug for collection in missing[:10]]},
            )
        )
    return alerts


def _tmdb_credential_configured(db: Session, settings: Settings) -> bool:
    try:
        credentials_service.get_secret(db, settings, CredentialKind.TMDB)
    except AppError:
        return False
    return True


def _job_counts(db: Session) -> dict[str, int]:
    stmt = select(JobExecution.status, func.count()).group_by(JobExecution.status)
    return {status: int(total) for status, total in db.execute(stmt).all()}


def _run_counts(db: Session) -> dict[str, int]:
    stmt = select(SyncRun.status, func.count()).group_by(SyncRun.status)
    return {status: int(total) for status, total in db.execute(stmt).all()}


def _recent_snapshots(db: Session, *, limit: int = 5) -> list[dict[str, Any]]:
    rows = snapshots_repo.recent(db, limit=limit)
    return [
        {
            "id": str(row.id),
            "collection_id": str(row.collection_id),
            "status": row.status,
            "quality": row.quality,
            "is_valid": row.is_valid,
            "items_count": row.items_count,
            "started_at": row.started_at,
            "finished_at": row.finished_at,
        }
        for row in rows
    ]


def _recent_jobs(db: Session, *, limit: int = 5) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(JobExecution).order_by(JobExecution.created_at.desc()).limit(limit)
    ).all()
    return [
        {
            "id": str(row.id),
            "task_name": row.task_name,
            "status": row.status,
            "created_at": row.created_at,
            "finished_at": row.finished_at,
            "error_code": row.error_code,
        }
        for row in rows
    ]


def _recent_sync_runs(db: Session, *, limit: int = 5) -> list[dict[str, Any]]:
    rows = db.scalars(select(SyncRun).order_by(SyncRun.created_at.desc()).limit(limit)).all()
    return [
        {
            "id": str(row.id),
            "status": row.status,
            "mode": row.mode,
            "media_type": row.media_type,
            "created_at": row.created_at,
            "finished_at": row.finished_at,
        }
        for row in rows
    ]
