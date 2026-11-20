"""System status for the UI topbar/dashboard and Prometheus metrics.

Both surfaces are built from the same collectors so the JSON and the text
exposition can never disagree:

* database/Redis probes and a Celery control ping with a short timeout;
* Celery queue depths read with ``LLEN`` on the Redis broker;
* sync-run counters, pending approvals and the next scheduled bindings;
* outbound TMDb/MDBList call counters;
* the backup status file written by ``deploy/scripts/backup.sh`` / ``backup-verify``.

No collector ever raises: a missing broker, an unreadable status file or a
missing credential degrade the reported value instead of failing the request.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, cast

import redis
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import APP_VERSION, Settings
from app.core.crypto import encryption_key_available
from app.core.logging import get_logger
from app.core.metrics import api_usage_snapshot
from app.core.time import ensure_utc, utcnow
from app.db.models import (
    Collection,
    CollectionSnapshot,
    MdblistTarget,
    SnapshotItem,
    SyncBinding,
    SyncRun,
)
from app.domain.enums import SourceStatus, SyncRunStatus
from app.domain.errors import AppError
from app.repositories import sources as sources_repo
from app.services import catalog_schedule
from app.services import credentials as credentials_service
from app.services.credentials import CredentialKind

logger = get_logger(__name__)

QUEUES = ("celery", "maintenance", "sync", "acquisitions")
REPORTED_RUN_STATUSES = (
    SyncRunStatus.SUCCEEDED,
    SyncRunStatus.FAILED,
    SyncRunStatus.AWAITING_APPROVAL,
    SyncRunStatus.PARTIAL,
)
WORKER_PING_TIMEOUT_SECONDS = 3.0
PROMETHEUS_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"

HEALTH_OK = "OK"
HEALTH_MISSING = "MISSING_CREDENTIAL"
HEALTH_DEGRADED = "DEGRADED"
HEALTH_ERROR = "ERROR"
HEALTH_DISABLED = "DISABLED"


@dataclass(frozen=True)
class BackupStatus:
    """Content of ``BACKUP_STATUS_FILE`` (written by the backup scripts)."""

    status: str = "MISSING"
    last_valid_at: datetime | None = None
    file: str | None = None
    age_hours: float | None = None
    size_bytes: int | None = None
    sha256: str | None = None
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "last_valid_at": self.last_valid_at,
            "file": self.file,
            "status": self.status,
            "age_hours": self.age_hours,
        }


def _redis_client(url: str) -> redis.Redis | None:
    if not url:
        return None
    return redis.Redis.from_url(
        url,
        socket_timeout=0.5,
        socket_connect_timeout=0.5,
        decode_responses=True,
    )


def database_ready(db: Session) -> bool:
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        logger.error("system_status_db_unavailable", error=type(exc).__name__)
        return False
    return True


def redis_ready(settings: Settings) -> bool:
    client = _redis_client(settings.redis_url)
    if client is None:
        return False
    try:
        return bool(client.ping())
    except redis.RedisError as exc:
        logger.warning("system_status_redis_unavailable", error=type(exc).__name__)
        return False


def _broker_available(settings: Settings) -> bool:
    """Tests run without a broker; without a URL there is nothing to probe."""
    return bool(settings.celery_broker_url) and settings.app_env != "test"


def queue_depths(settings: Settings) -> dict[str, int]:
    """``LLEN`` for every queue the worker consumes; zeros when Redis is down."""
    depths = dict.fromkeys(QUEUES, 0)
    if not _broker_available(settings):
        return depths
    client = _redis_client(settings.celery_broker_url)
    if client is None:
        return depths
    try:
        for queue in QUEUES:
            depths[queue] = int(cast(int, client.llen(queue)) or 0)
    except redis.RedisError as exc:
        logger.warning("system_status_queue_depth_failed", error=type(exc).__name__)
    return depths


def worker_ready(settings: Settings) -> bool:
    """Celery control ping with a short timeout; never raises if the broker is down."""
    if not _broker_available(settings):
        return False
    try:
        from app.jobs.celery_app import celery_app

        inspector = celery_app.control.inspect(timeout=WORKER_PING_TIMEOUT_SECONDS, limit=1)
        pong = inspector.ping() if inspector is not None else None
        return bool(pong)
    except Exception as exc:  # noqa: BLE001 - broker down must not break the endpoint
        logger.warning("system_status_worker_ping_failed", error=type(exc).__name__)
        return False


def _credential_state(db: Session, settings: Settings, kind: CredentialKind) -> str:
    try:
        credentials_service.get_secret(db, settings, kind)
    except AppError:
        return HEALTH_MISSING
    return HEALTH_OK


def _source_state(db: Session, settings: Settings, kind: CredentialKind, source_key: str) -> str:
    source = sources_repo.get_source_by_key(db, source_key)
    if source is not None and source.status in (
        SourceStatus.DISABLED.value,
        SourceStatus.ERROR.value,
        SourceStatus.DEGRADED.value,
    ):
        return source.status
    return _credential_state(db, settings, kind)


def service_health(db: Session, settings: Settings) -> dict[str, str]:
    """TMDb/MDBList/TVDB state from the source row and stored credential."""
    return {
        "tmdb": _source_state(db, settings, CredentialKind.TMDB, "tmdb"),
        "mdblist": _credential_state(db, settings, CredentialKind.MDBLIST),
        "tvdb": _source_state(db, settings, CredentialKind.TVDB, "tvdb"),
    }


def run_counts(db: Session) -> dict[str, int]:
    stmt = select(SyncRun.status, func.count()).group_by(SyncRun.status)
    counts = {status: int(total) for status, total in db.execute(stmt).all()}
    for status in REPORTED_RUN_STATUSES:
        counts.setdefault(status.value, 0)
    return counts


def pending_approvals(db: Session) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(SyncRun)
            .where(SyncRun.status == SyncRunStatus.AWAITING_APPROVAL.value)
        )
        or 0
    )


def upcoming_bindings(db: Session, *, limit: int = 5) -> list[dict[str, Any]]:
    rows = db.execute(
        select(SyncBinding, Collection.name, MdblistTarget.name)
        .join(Collection, Collection.id == SyncBinding.collection_id)
        .join(MdblistTarget, MdblistTarget.id == SyncBinding.target_id)
        .where(SyncBinding.is_enabled.is_(True), SyncBinding.next_run_at.is_not(None))
        .order_by(SyncBinding.next_run_at)
        .limit(limit)
    ).all()
    return [
        {
            "binding_id": binding.id,
            "collection_name": collection_name,
            "target_name": target_name,
            "next_run_at": binding.next_run_at,
        }
        for binding, collection_name, target_name in rows
    ]


def upcoming_catalog_acquisitions(
    db: Session, *, now: datetime | None = None
) -> list[dict[str, Any]]:
    """Next 24h of staggered JustWatch acquisitions, one entry per collection."""
    return [
        {
            "collection_id": item.collection_id,
            "collection_name": item.collection_name,
            "provider_name": item.provider_name,
            "next_acquire_at": item.next_acquire_at,
        }
        for item in catalog_schedule.upcoming_acquisitions(db, now=now)
    ]


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return ensure_utc(datetime.fromisoformat(value.strip().replace("Z", "+00:00")))
    except ValueError:
        return None


def read_backup_status(settings: Settings, *, now: datetime | None = None) -> BackupStatus:
    """Read ``BACKUP_STATUS_FILE``; a missing or broken file is not an error."""
    path = Path(settings.effective_backup_status_file)
    if not path.is_file():
        return BackupStatus(status="MISSING")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("backup_status_unreadable", path=str(path), error=type(exc).__name__)
        return BackupStatus(status="UNREADABLE", file=path.name)
    if not isinstance(raw, dict):
        return BackupStatus(status="UNREADABLE", file=path.name)
    status = str(raw.get("status") or "UNKNOWN")
    timestamp = _parse_timestamp(raw.get("timestamp"))
    last_valid_at = timestamp if status == HEALTH_OK else None
    age_hours = None
    if last_valid_at is not None:
        delta = ensure_utc(now or utcnow()) - last_valid_at
        age_hours = round(delta.total_seconds() / 3600, 2)
    size = raw.get("size")
    return BackupStatus(
        status=status,
        last_valid_at=last_valid_at,
        file=str(raw["file"]) if raw.get("file") else path.name,
        age_hours=age_hours,
        size_bytes=int(size) if isinstance(size, (int, float)) else None,
        sha256=str(raw["sha256"]) if raw.get("sha256") else None,
        error=str(raw["error"]) if raw.get("error") else None,
    )


def storage_usage(db: Session) -> dict[str, Any]:
    """Physical size of snapshot/run tables, when the dialect exposes it.

    PostgreSQL uses ``pg_total_relation_size`` (indexes and TOAST included);
    SQLite tests report database bytes and let the UI show a dash for the
    per-table split.
    """
    bind = db.get_bind()
    dialect = bind.dialect.name
    snapshot_bytes = 0
    run_bytes = 0
    database_bytes = 0
    size_supported = dialect == "postgresql"
    if dialect == "postgresql":
        row = db.execute(
            text(
                "SELECT "
                "pg_total_relation_size('snapshot_item') + "
                "pg_total_relation_size('collection_snapshot'), "
                "pg_total_relation_size('sync_run') + "
                "pg_total_relation_size('sync_operation') + "
                "pg_total_relation_size('sync_run_event')"
            )
        ).one()
        snapshot_bytes = int(row[0] or 0)
        run_bytes = int(row[1] or 0)
        database_bytes = int(
            db.execute(text("SELECT pg_database_size(current_database())")).scalar() or 0
        )
    else:
        try:
            page_count = int(db.execute(text("PRAGMA page_count")).scalar() or 0)
            page_size = int(db.execute(text("PRAGMA page_size")).scalar() or 0)
            database_bytes = page_count * page_size
        except SQLAlchemyError:
            database_bytes = 0
    snapshot_rows = int(db.scalar(select(func.count()).select_from(CollectionSnapshot)) or 0)
    snapshot_item_rows = int(db.scalar(select(func.count()).select_from(SnapshotItem)) or 0)
    run_rows = int(db.scalar(select(func.count()).select_from(SyncRun)) or 0)
    return {
        "snapshot_bytes": snapshot_bytes,
        "run_bytes": run_bytes,
        "total_bytes": snapshot_bytes + run_bytes,
        "database_bytes": database_bytes,
        "snapshot_rows": snapshot_rows,
        "snapshot_item_rows": snapshot_item_rows,
        "run_rows": run_rows,
        "size_supported": size_supported,
    }


def get_system_status(
    db: Session, settings: Settings, *, now: datetime | None = None
) -> dict[str, Any]:
    """Aggregate for ``GET /api/system/status`` (admin session)."""
    services = service_health(db, settings)
    return {
        "health": {
            "api": True,
            "database": database_ready(db),
            "redis": redis_ready(settings),
            "worker": worker_ready(settings),
            "tmdb": services["tmdb"],
            "mdblist": services["mdblist"],
            "tvdb": services["tvdb"],
        },
        "queues": queue_depths(settings),
        "runs": run_counts(db),
        "api_usage": api_usage_snapshot(),
        "backup": read_backup_status(settings, now=now).as_dict(),
        "pending_approvals": pending_approvals(db),
        "upcoming": upcoming_bindings(db),
        "catalog_acquisitions": upcoming_catalog_acquisitions(db, now=now),
        "storage": storage_usage(db),
    }


def _metric(
    lines: list[str],
    name: str,
    help_text: str,
    samples: list[tuple[str, float | int]],
    *,
    type_: str = "gauge",
) -> None:
    lines.append(f"# HELP {name} {help_text}")
    lines.append(f"# TYPE {name} {type_}")
    for labels, value in samples:
        lines.append(f"{name}{labels} {value}")


def _labels(**items: str) -> str:
    if not items:
        return ""
    rendered = ",".join(f'{key}="{value}"' for key, value in items.items())
    return "{" + rendered + "}"


def render_metrics(db: Session, settings: Settings, *, now: datetime | None = None) -> str:
    """Prometheus text exposition (version 0.0.4)."""
    services = service_health(db, settings)
    backup = read_backup_status(settings, now=now)
    usage = api_usage_snapshot()
    runs = run_counts(db)
    lines: list[str] = []

    _metric(lines, "mdbup_up", "1 when the API process answers this endpoint.", [("", 1)])
    _metric(
        lines,
        "mdbup_info",
        "Build information.",
        [(_labels(version=APP_VERSION), 1)],
    )
    _metric(
        lines,
        "mdbup_database_up",
        "1 when PostgreSQL answers SELECT 1.",
        [("", 1 if database_ready(db) else 0)],
    )
    _metric(
        lines,
        "mdbup_redis_up",
        "1 when Redis answers PING.",
        [("", 1 if redis_ready(settings) else 0)],
    )
    _metric(
        lines,
        "mdbup_encryption_key_ready",
        "1 when the encryption keyring can decrypt stored secrets.",
        [("", 1 if encryption_key_available(settings) else 0)],
    )
    _metric(
        lines,
        "mdbup_worker_up",
        "1 when a Celery worker answers the control ping.",
        [("", 1 if worker_ready(settings) else 0)],
    )
    _metric(
        lines,
        "mdbup_service_up",
        "1 when the integration has a usable credential and an active source.",
        [
            (_labels(service=name), 1 if state == HEALTH_OK else 0)
            for name, state in sorted(services.items())
        ],
    )
    _metric(
        lines,
        "mdbup_celery_queue_depth",
        "Messages waiting in each Celery queue (Redis LLEN).",
        [(_labels(queue=queue), depth) for queue, depth in queue_depths(settings).items()],
    )
    _metric(
        lines,
        "mdbup_sync_runs",
        "Sync runs by status.",
        [(_labels(status=status), total) for status, total in sorted(runs.items())],
    )
    _metric(
        lines,
        "mdbup_pending_approvals",
        "Runs waiting for an operator decision.",
        [("", pending_approvals(db))],
    )
    _metric(
        lines,
        "mdbup_api_calls",
        "Outbound integration calls recorded today and in the current hour.",
        [
            (_labels(provider=provider, window=window), value)
            for provider, windows in sorted(usage.items())
            for window, value in (("hour", windows["hour"]), ("day", windows["today"]))
        ],
    )
    _metric(
        lines,
        "mdbup_last_backup_valid_timestamp_seconds",
        "Unix timestamp of the last verified backup (0 when unknown).",
        [("", int(backup.last_valid_at.timestamp()) if backup.last_valid_at else 0)],
    )
    _metric(
        lines,
        "mdbup_backup_age_hours",
        "Hours since the last verified backup (-1 when unknown).",
        [("", backup.age_hours if backup.age_hours is not None else -1)],
    )
    _metric(
        lines,
        "mdbup_backup_status_ok",
        "1 when the backup status file reports OK.",
        [("", 1 if backup.status == HEALTH_OK else 0)],
    )
    return "\n".join(lines) + "\n"
