"""Acquisition task and its enqueue helper.

Lane C owns the Celery application (``app/jobs/celery_app.py``). This module
keeps the acquisition task callable today: it runs inline in test/eager mode,
and the enqueue helper returns ``503`` when Celery is not configured instead of
pretending the job was queued.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, cast

from sqlalchemy.orm import Session

from app.connectors import registry
from app.connectors.base import SourceConnector
from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.core.time import utcnow
from app.db.models import JobExecution
from app.db.session import session_scope
from app.domain.enums import COMBINED_SOURCE_KEY, AuditActorType, JobStatus, SyncRunStatus
from app.domain.errors import (
    AppError,
    CredentialMissingError,
    NotFoundError,
    ServiceUnavailableError,
    SourceUnavailableError,
)
from app.repositories import collections as collections_repo
from app.repositories import runs as runs_repo
from app.repositories import sources as sources_repo
from app.services import acquisition
from app.services import sync as sync_service

logger = get_logger(__name__)

ACQUIRE_COLLECTION_TASK = "app.jobs.tasks.acquire_collection_task"
ACQUISITION_QUEUE = "acquisitions"
RUN_SYNC_TASK = "app.jobs.tasks.run_sync_task"
RECONCILE_SYNC_RUN_TASK = "app.jobs.tasks.reconcile_sync_run_task"
ENQUEUE_DUE_BINDINGS_TASK = "app.jobs.tasks.enqueue_due_bindings"
ENQUEUE_SCHEDULED_CATALOG_ACQUISITIONS_TASK = (
    "app.jobs.tasks.enqueue_scheduled_catalog_acquisitions"
)
CLEANUP_OLD_DATA_TASK = "app.jobs.tasks.cleanup_old_data"
SWEEP_STALE_RUNS_TASK = "app.jobs.tasks.sweep_stale_runs"
DETECT_TV_CHANGES_TASK = "app.jobs.tasks.detect_tv_changes"
SEND_RUN_NOTIFICATIONS_TASK = "app.jobs.tasks.send_run_notifications"
SEND_PERIODIC_SUMMARY_TASK = "app.jobs.tasks.send_periodic_summary"
SWEEP_ORPHAN_LOCKS_TASK = "app.jobs.tasks.sweep_orphan_locks"
RETRY_FAILED_NOTIFICATIONS_TASK = "app.jobs.tasks.retry_failed_notifications"
SYNC_QUEUE = "sync"


def create_job_execution(
    db: Session,
    *,
    task_name: str,
    payload: dict[str, Any],
    queue: str = ACQUISITION_QUEUE,
) -> JobExecution:
    job = JobExecution(
        task_name=task_name,
        queue=queue,
        status=JobStatus.QUEUED.value,
        payload=payload,
    )
    db.add(job)
    db.flush()
    return job


def mark_job_running(db: Session, job: JobExecution) -> None:
    job.status = JobStatus.RUNNING.value
    job.started_at = utcnow()
    db.flush()


def mark_job_finished(
    db: Session,
    job: JobExecution,
    *,
    status: JobStatus,
    result: dict[str, Any] | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> None:
    job.status = status.value
    job.finished_at = utcnow()
    job.result = result
    job.error_code = error_code
    job.error_message = error_message[:1000] if error_message else None
    db.flush()


class _LocalOnlyConnector:
    """Placeholder for a source whose acquisition is entirely local."""

    key = COMBINED_SOURCE_KEY

    def close(self) -> None:
        return None


def acquire_collection_task(
    collection_id: str | uuid.UUID,
    job_execution_id: str | uuid.UUID | None = None,
) -> dict[str, Any]:
    """Acquire one collection and record the outcome on the job row.

    Expected failures are recorded and returned, not raised, so the API keeps
    its ``202`` contract and the job row stays the source of truth.
    """
    settings = get_settings()
    collection_uuid = uuid.UUID(str(collection_id))
    job_uuid = uuid.UUID(str(job_execution_id)) if job_execution_id else None
    with session_scope() as db:
        job = db.get(JobExecution, job_uuid) if job_uuid is not None else None
        if job is not None:
            mark_job_running(db, job)
            db.commit()
        try:
            collection = collections_repo.get_collection(db, collection_uuid)
            if collection is None:
                raise NotFoundError(
                    "Collezione non trovata.",
                    details={"collection_id": str(collection_uuid)},
                )
            source = sources_repo.get_source(db, collection.source_id)
            if source is None:
                raise SourceUnavailableError(
                    "Fonte della collezione non trovata.",
                    details={"collection_id": str(collection_uuid)},
                )
            if source.key == COMBINED_SOURCE_KEY:
                outcome = acquisition.acquire_collection(
                    db,
                    collection_uuid,
                    cast(SourceConnector, _LocalOnlyConnector()),
                    actor_type=AuditActorType.SYSTEM,
                    job_execution_id=job_uuid,
                )
            else:
                connector = registry.create_connector(db, settings, source.key)
                try:
                    outcome = acquisition.acquire_collection(
                        db,
                        collection_uuid,
                        connector,
                        actor_type=AuditActorType.SYSTEM,
                        job_execution_id=job_uuid,
                    )
                finally:
                    connector.close()
        except AppError as exc:
            db.rollback()
            if exc.code in {"CREDENTIAL_MISSING", "ENCRYPTION_KEY_MISSING"}:
                from app.services import notifications as notifications_service

                notifications_service.notify_auth_error(
                    db,
                    settings,
                    service="TMDb",
                    status_code=None,
                    detail=exc.message,
                )
            _finish_failed(db, job_uuid, exc.code, exc.message)
            return {
                "job_id": str(job_uuid) if job_uuid else None,
                "collection_id": str(collection_uuid),
                "status": JobStatus.FAILED.value,
                "error_code": exc.code,
                "error_message": exc.message,
            }
        except Exception as exc:  # pragma: no cover - defensive task boundary
            logger.exception(
                "acquire_collection_task_failed",
                collection_id=str(collection_uuid),
                error=type(exc).__name__,
            )
            db.rollback()
            _finish_failed(db, job_uuid, "TASK_ERROR", str(exc))
            return {
                "job_id": str(job_uuid) if job_uuid else None,
                "collection_id": str(collection_uuid),
                "status": JobStatus.FAILED.value,
                "error_code": "TASK_ERROR",
                "error_message": str(exc)[:1000],
            }
        if any(
            "TMDbAuthError" in str(error.get("code", ""))
            for error in (outcome.errors if hasattr(outcome, "errors") else [])
        ):
            from app.services import notifications as notifications_service

            notifications_service.notify_auth_error(
                db,
                settings,
                service="TMDb",
                status_code=401,
                detail="TMDb ha rifiutato la credenziale durante l'acquisizione.",
            )
        result = {
            "job_id": str(job_uuid) if job_uuid else None,
            "collection_id": str(collection_uuid),
            "snapshot_id": str(outcome.snapshot_id),
            "status": JobStatus.SUCCEEDED.value,
            "snapshot_status": outcome.status.value,
            "is_valid": outcome.is_valid,
            "items_count": outcome.items_count,
        }
        if job_uuid is not None:
            _finish_succeeded(db, job_uuid, result)
        return result


def enqueue_acquire_collection(
    db: Session,
    settings: Settings,
    collection_id: uuid.UUID,
    *,
    actor_user_id: uuid.UUID | None = None,
) -> JobExecution:
    """Create the job row and dispatch it (inline in test/eager mode)."""
    job = create_job_execution(
        db,
        task_name=ACQUIRE_COLLECTION_TASK,
        payload={
            "collection_id": str(collection_id),
            "requested_by": str(actor_user_id) if actor_user_id else None,
        },
    )
    db.commit()
    if _runs_inline(settings):
        acquire_collection_task(str(collection_id), str(job.id))
        db.refresh(job)
        return job
    celery_app = _celery_app()
    try:
        async_result = celery_app.send_task(
            ACQUIRE_COLLECTION_TASK,
            args=[str(collection_id), str(job.id)],
            queue=ACQUISITION_QUEUE,
        )
    except Exception as exc:
        mark_job_finished(
            db,
            job,
            status=JobStatus.FAILED,
            error_code="CELERY_UNAVAILABLE",
            error_message="Invio del task a Celery non riuscito.",
        )
        db.commit()
        raise ServiceUnavailableError(
            "Coda Celery non raggiungibile: acquisizione non accodata.",
        ) from exc
    job.task_id = async_result.id
    db.commit()
    return job


def _runs_inline(settings: Settings) -> bool:
    return settings.app_env == "test" or settings.celery_task_always_eager


def _celery_app() -> Any:
    try:
        from app.jobs.celery_app import celery_app
    except ImportError as exc:
        raise ServiceUnavailableError(
            "Celery non configurato: impossibile accodare l'acquisizione.",
            details={"task": ACQUIRE_COLLECTION_TASK},
        ) from exc
    return celery_app


def _finish_succeeded(db: Session, job_id: uuid.UUID, result: dict[str, Any]) -> None:
    job = db.get(JobExecution, job_id)
    if job is None:  # pragma: no cover - job row always exists in this flow
        return
    mark_job_finished(db, job, status=JobStatus.SUCCEEDED, result=result)


def _finish_failed(
    db: Session, job_id: uuid.UUID | None, error_code: str, error_message: str
) -> None:
    if job_id is None:
        return
    job = db.get(JobExecution, job_id)
    if job is None:  # pragma: no cover - job row always exists in this flow
        return
    mark_job_finished(
        db,
        job,
        status=JobStatus.FAILED,
        error_code=error_code,
        error_message=error_message,
    )


def run_sync_task(
    run_id: str | uuid.UUID,
    job_execution_id: str | uuid.UUID | None = None,
    reconcile: bool = False,
) -> dict[str, Any]:
    """Execute (or reconcile) one sync run and record the job outcome.

    Expected failures are recorded on the run and on the job row instead of
    escaping, so the API keeps its ``202`` contract.
    """
    settings = get_settings()
    run_uuid = uuid.UUID(str(run_id))
    job_uuid = uuid.UUID(str(job_execution_id)) if job_execution_id else None
    with session_scope() as db:
        job = db.get(JobExecution, job_uuid) if job_uuid is not None else None
        if job is not None:
            mark_job_running(db, job)
            db.commit()
        run = runs_repo.get_run(db, run_uuid)
        if run is None:
            _finish_failed(db, job_uuid, "RUN_NOT_FOUND", "Run non trovato.")
            db.commit()
            return {
                "run_id": str(run_uuid),
                "status": SyncRunStatus.FAILED.value,
                "error_code": "RUN_NOT_FOUND",
            }
        client = None
        try:
            client = sync_service.build_client(db, settings)
        except CredentialMissingError as exc:
            from app.services import notifications as notifications_service

            notifications_service.notify_auth_error(
                db,
                settings,
                service="MDBList",
                status_code=None,
                detail=exc.message,
            )
            runs_repo.finish_run(
                db,
                run,
                SyncRunStatus.BLOCKED,
                abort_reason="CREDENTIAL_MISSING",
                error_message=exc.message,
            )
            db.commit()
            _finish_failed(db, job_uuid, exc.code, exc.message)
            db.commit()
            return {
                "run_id": str(run_uuid),
                "status": SyncRunStatus.BLOCKED.value,
                "error_code": exc.code,
            }
        except AppError as exc:
            runs_repo.finish_run(
                db,
                run,
                SyncRunStatus.FAILED,
                error_code=exc.code,
                error_message=exc.message,
            )
            db.commit()
            _finish_failed(db, job_uuid, exc.code, exc.message)
            db.commit()
            return {
                "run_id": str(run_uuid),
                "status": SyncRunStatus.FAILED.value,
                "error_code": exc.code,
            }
        try:
            if reconcile:
                outcome = sync_service.reconcile_run(db, settings, run_uuid, client=client)
            else:
                outcome = sync_service.execute_run(
                    db,
                    settings,
                    run_uuid,
                    client=client,
                    throttle=(None if settings.app_env == "test" else sync_service.WRITE_THROTTLE),
                )
        except AppError as exc:
            db.rollback()
            _fail_run_after_error(db, run_uuid, exc.code, exc.message)
            _finish_failed(db, job_uuid, exc.code, exc.message)
            db.commit()
            return {
                "run_id": str(run_uuid),
                "status": SyncRunStatus.FAILED.value,
                "error_code": exc.code,
            }
        except Exception as exc:  # pragma: no cover - defensive task boundary
            logger.exception("run_sync_task_failed", run_id=str(run_uuid), error=type(exc).__name__)
            db.rollback()
            _fail_run_after_error(db, run_uuid, "TASK_ERROR", str(exc))
            _finish_failed(db, job_uuid, "TASK_ERROR", str(exc))
            db.commit()
            return {
                "run_id": str(run_uuid),
                "status": SyncRunStatus.FAILED.value,
                "error_code": "TASK_ERROR",
            }
        finally:
            if client is not None:
                client.close()
        if outcome.abort_reason in {"MDBLIST_AUTH_FAILED", "MDBLIST_PERMISSION_DENIED"}:
            from app.services import notifications as notifications_service

            notifications_service.notify_auth_error(
                db,
                settings,
                service="MDBList",
                status_code=401 if outcome.abort_reason == "MDBLIST_AUTH_FAILED" else 403,
                detail="La sincronizzazione è stata bloccata prima di scrivere sulla lista.",
            )
        result = {
            "run_id": str(outcome.run_id),
            "status": outcome.status,
            "added": outcome.added,
            "removed": outcome.removed,
            "failed": outcome.failed,
            "uncertain": outcome.uncertain,
            "order_enforced": outcome.order_enforced,
            "warnings": outcome.warnings,
            "abort_reason": outcome.abort_reason,
        }
        if job_uuid is not None:
            _finish_succeeded(db, job_uuid, result)
            db.commit()
        return result


def reconcile_sync_run_task(
    run_id: str | uuid.UUID,
    job_execution_id: str | uuid.UUID | None = None,
) -> dict[str, Any]:
    return run_sync_task(run_id, job_execution_id, reconcile=True)


def enqueue_sync_run(
    db: Session,
    settings: Settings,
    run_id: uuid.UUID,
    *,
    reconcile: bool = False,
) -> JobExecution:
    """Create the job row and dispatch the sync task (inline in test/eager mode)."""
    task_name = RECONCILE_SYNC_RUN_TASK if reconcile else RUN_SYNC_TASK
    job = create_job_execution(
        db,
        task_name=task_name,
        payload={"run_id": str(run_id)},
        queue=SYNC_QUEUE,
    )
    db.commit()
    if _runs_inline(settings):
        run_sync_task(str(run_id), str(job.id), reconcile=reconcile)
        db.refresh(job)
        return job
    celery_app = _celery_app()
    try:
        args: list[object] = [str(run_id), str(job.id)]
        if not reconcile:
            args.append(False)
        async_result = celery_app.send_task(
            task_name,
            args=args,
            queue=SYNC_QUEUE,
        )
    except Exception as exc:
        mark_job_finished(
            db,
            job,
            status=JobStatus.FAILED,
            error_code="CELERY_UNAVAILABLE",
            error_message="Invio del task di sync a Celery non riuscito.",
        )
        db.commit()
        raise ServiceUnavailableError(
            "Coda Celery non raggiungibile: sync non accodata.",
        ) from exc
    job.task_id = async_result.id
    db.commit()
    return job


def record_control_job(
    db: Session,
    *,
    task_name: str,
    payload: dict[str, Any],
    result: dict[str, Any],
) -> JobExecution:
    """Record a synchronous control action (cancel/reconcile) as a job row."""
    job = create_job_execution(db, task_name=task_name, payload=payload, queue=SYNC_QUEUE)
    mark_job_finished(db, job, status=JobStatus.SUCCEEDED, result=result)
    db.commit()
    return job


def enqueue_due_bindings() -> dict[str, Any]:
    """Celery beat task: create runs for bindings whose schedule is due."""
    from app.jobs import scheduler

    settings = get_settings()
    with session_scope() as db:
        outcome = scheduler.enqueue_due_bindings(db, settings)
    return {
        "enqueued": outcome.enqueued,
        "skipped": outcome.skipped,
        "run_ids": [str(run_id) for run_id in outcome.run_ids],
    }


def enqueue_scheduled_catalog_acquisitions(now: str | None = None) -> dict[str, Any]:
    """Celery beat task: enqueue at most one staggered JustWatch acquisition.

    ``now`` is an ISO timestamp used by the tests to pin the slot; production
    leaves it empty and the task reads the clock.
    """
    from app.services import catalog_schedule

    settings = get_settings()
    moment = datetime.fromisoformat(now) if now else None
    with session_scope() as db:
        outcome = catalog_schedule.enqueue_due_catalog_acquisitions(db, settings, now=moment)
    return {
        "due": outcome.due,
        "enqueued": outcome.enqueued,
        "collection_id": str(outcome.collection_id) if outcome.collection_id else None,
        "job_id": str(outcome.job_id) if outcome.job_id else None,
        "reason": outcome.reason,
    }


def detect_tv_changes(limit: int = 50) -> dict[str, int]:
    """Celery beat task: detect new seasons/episodes without creating media rows."""
    from app.integrations.tmdb.client import TMDbClient
    from app.services import credentials as credentials_service
    from app.services.credentials import CredentialKind
    from app.services.tv_events import detect_tv_changes as detect

    settings = get_settings()
    with session_scope() as db:
        token = credentials_service.get_secret(db, settings, CredentialKind.TMDB)
        with TMDbClient(token) as client:
            outcome = detect(db, client, limit=limit)
    return {
        "checked": outcome.checked,
        "season_events": outcome.season_events,
        "episode_events": outcome.episode_events,
        "errors": outcome.errors,
    }


def cleanup_old_data() -> dict[str, int]:
    """Celery beat task: apply the retention policy."""
    from app.jobs import scheduler

    settings = get_settings()
    with session_scope() as db:
        return scheduler.cleanup_old_data(db, settings)


def sweep_stale_runs() -> dict[str, int]:
    """Celery beat task: recover runs left behind by a crashed worker."""
    from app.jobs import scheduler

    settings = get_settings()
    with session_scope() as db:
        return scheduler.sweep_stale_runs(db, settings)


def send_run_notifications() -> dict[str, int]:
    """Celery beat task: alert on pending approval, failed and uncertain runs."""
    from app.services import notifications as notifications_service

    settings = get_settings()
    with session_scope() as db:
        return notifications_service.scan_run_notifications(db, settings)


def send_periodic_summary() -> dict[str, Any]:
    """Celery beat task: optional daily summary of the last 24 hours."""
    from app.services import notifications as notifications_service

    settings = get_settings()
    with session_scope() as db:
        return notifications_service.send_periodic_summary(db, settings)


def retry_failed_notifications() -> dict[str, int]:
    """Celery beat task: resend failed notification deliveries due for a retry."""
    from app.services import notifications as notifications_service

    settings = get_settings()
    with session_scope() as db:
        return notifications_service.retry_due_notifications(db, settings)


def sweep_orphan_locks() -> dict[str, int]:
    """Celery beat task: remove dispatch locks with no active run behind them."""
    from app.jobs import scheduler

    settings = get_settings()
    with session_scope() as db:
        return scheduler.sweep_orphan_locks(db, settings)


def _fail_run_after_error(
    db: Session, run_id: uuid.UUID, error_code: str, error_message: str
) -> None:
    run = runs_repo.get_run(db, run_id)
    if run is None:
        return
    if run.status in {
        SyncRunStatus.SUCCEEDED.value,
        SyncRunStatus.PARTIAL.value,
        SyncRunStatus.FAILED.value,
        SyncRunStatus.BLOCKED.value,
        SyncRunStatus.CANCELLED.value,
    }:
        return
    runs_repo.finish_run(
        db,
        run,
        SyncRunStatus.FAILED,
        error_code=error_code,
        error_message=error_message,
    )
