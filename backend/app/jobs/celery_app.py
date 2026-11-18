"""Celery application: broker/result backend from settings and beat schedule.

Tasks are plain functions in ``app.jobs.tasks``; they are registered here so
both ``celery -A app.jobs.celery_app worker`` and ``beat`` resolve them by name.
In ``APP_ENV=test`` or with ``CELERY_TASK_ALWAYS_EAGER=true`` the API runs the
same functions inline and never touches the broker.
"""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings
from app.jobs import tasks

settings = get_settings()

celery_app = Celery(
    "mdbup",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_always_eager=settings.celery_task_always_eager,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone=settings.app_timezone,
    enable_utc=True,
    task_track_started=True,
    broker_connection_retry_on_startup=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
)

celery_app.conf.beat_schedule = {
    "enqueue-due-bindings": {
        "task": tasks.ENQUEUE_DUE_BINDINGS_TASK,
        "schedule": 60.0,
        "options": {"queue": "maintenance"},
    },
    "cleanup-old-data": {
        "task": tasks.CLEANUP_OLD_DATA_TASK,
        "schedule": crontab(hour=3, minute=30),
        "options": {"queue": "maintenance"},
    },
    "sweep-stale-runs": {
        "task": tasks.SWEEP_STALE_RUNS_TASK,
        "schedule": 900.0,
        "options": {"queue": "maintenance"},
    },
    "detect-tv-changes": {
        "task": tasks.DETECT_TV_CHANGES_TASK,
        "schedule": crontab(day_of_week=0, hour=4, minute=0),
        "options": {"queue": "maintenance"},
    },
    "send-run-notifications": {
        "task": tasks.SEND_RUN_NOTIFICATIONS_TASK,
        "schedule": 60.0,
        "options": {"queue": "maintenance"},
    },
    "send-periodic-summary": {
        "task": tasks.SEND_PERIODIC_SUMMARY_TASK,
        "schedule": 3600.0,
        "options": {"queue": "maintenance"},
    },
    "sweep-orphan-locks": {
        "task": tasks.SWEEP_ORPHAN_LOCKS_TASK,
        "schedule": 300.0,
        "options": {"queue": "maintenance"},
    },
    "retry-failed-notifications": {
        "task": tasks.RETRY_FAILED_NOTIFICATIONS_TASK,
        "schedule": 60.0,
        "options": {"queue": "maintenance"},
    },
}

celery_app.task(name=tasks.ACQUIRE_COLLECTION_TASK)(tasks.acquire_collection_task)
celery_app.task(name=tasks.RUN_SYNC_TASK)(tasks.run_sync_task)
celery_app.task(name=tasks.RECONCILE_SYNC_RUN_TASK)(tasks.reconcile_sync_run_task)
celery_app.task(name=tasks.ENQUEUE_DUE_BINDINGS_TASK)(tasks.enqueue_due_bindings)
celery_app.task(name=tasks.CLEANUP_OLD_DATA_TASK)(tasks.cleanup_old_data)
celery_app.task(name=tasks.SWEEP_STALE_RUNS_TASK)(tasks.sweep_stale_runs)
celery_app.task(name=tasks.DETECT_TV_CHANGES_TASK)(tasks.detect_tv_changes)
celery_app.task(name=tasks.SEND_RUN_NOTIFICATIONS_TASK)(tasks.send_run_notifications)
celery_app.task(name=tasks.SEND_PERIODIC_SUMMARY_TASK)(tasks.send_periodic_summary)
celery_app.task(name=tasks.SWEEP_ORPHAN_LOCKS_TASK)(tasks.sweep_orphan_locks)
celery_app.task(name=tasks.RETRY_FAILED_NOTIFICATIONS_TASK)(tasks.retry_failed_notifications)
