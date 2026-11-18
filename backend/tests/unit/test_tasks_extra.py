"""Celery task wrappers and dispatch failure paths."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.time import utcnow
from app.db.session import get_session_factory
from app.domain.enums import JobStatus
from app.domain.errors import ServiceUnavailableError
from app.jobs import tasks
from app.repositories import bindings as bindings_repo
from app.repositories import collections as collections_repo
from app.repositories import runs as runs_repo
from app.repositories import targets as targets_repo


@pytest.fixture()
def session(db) -> Session:
    db_session = get_session_factory()()
    try:
        yield db_session
    finally:
        db_session.close()


def _settings(app_settings, **overrides) -> Settings:
    values = {
        "database_url": app_settings.database_url,
        "app_encryption_key": app_settings.app_encryption_key,
        "redis_url": "",
        "app_env": "production",
        "celery_task_always_eager": False,
    }
    values.update(overrides)
    return Settings(**values)


def test_job_ledger_helpers(session: Session) -> None:
    job = tasks.create_job_execution(session, task_name="x", payload={"a": 1})
    assert job.status == JobStatus.QUEUED.value
    tasks.mark_job_running(session, job)
    assert job.status == JobStatus.RUNNING.value
    tasks.mark_job_finished(session, job, status=JobStatus.FAILED, error_message="x" * 1200)
    assert job.error_message is not None and len(job.error_message) == 1000


def test_control_task_wrappers(session: Session, seeded, app_settings, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.jobs.scheduler.enqueue_due_bindings",
        lambda db, settings: SimpleNamespace(enqueued=1, skipped=2, run_ids=[uuid.uuid4()]),
    )
    monkeypatch.setattr("app.jobs.scheduler.cleanup_old_data", lambda db, settings: {"runs": 1})
    monkeypatch.setattr("app.jobs.scheduler.sweep_stale_runs", lambda db, settings: {"stale": 1})
    monkeypatch.setattr("app.jobs.scheduler.sweep_orphan_locks", lambda db, settings: {"locks": 1})
    monkeypatch.setattr(
        "app.services.catalog_schedule.enqueue_due_catalog_acquisitions",
        lambda db, settings, now=None: SimpleNamespace(
            due=True,
            enqueued=False,
            collection_id=None,
            job_id=None,
            reason="NO_DUE",
        ),
    )
    monkeypatch.setattr(
        "app.services.notifications.scan_run_notifications", lambda db, settings: {"sent": 1}
    )
    monkeypatch.setattr(
        "app.services.notifications.send_periodic_summary", lambda db, settings: {"sent": 2}
    )
    monkeypatch.setattr(
        "app.services.notifications.retry_due_notifications", lambda db, settings: {"retried": 3}
    )
    monkeypatch.setattr(tasks, "get_settings", lambda: app_settings)

    assert tasks.enqueue_due_bindings()["enqueued"] == 1
    assert tasks.cleanup_old_data() == {"runs": 1}
    assert tasks.sweep_stale_runs() == {"stale": 1}
    assert tasks.sweep_orphan_locks() == {"locks": 1}
    assert (
        tasks.enqueue_scheduled_catalog_acquisitions(now="2026-01-01T00:00:00")["reason"]
        == "NO_DUE"
    )
    assert tasks.send_run_notifications() == {"sent": 1}
    assert tasks.send_periodic_summary() == {"sent": 2}
    assert tasks.retry_failed_notifications() == {"retried": 3}


def test_enqueue_acquire_inline_and_celery(
    session: Session, seeded, app_settings, monkeypatch
) -> None:
    collection = collections_repo.get_collection_by_slug(session, "netflix-movie")
    assert collection is not None
    monkeypatch.setattr(tasks, "acquire_collection_task", lambda *a, **k: {"ok": True})

    inline = tasks.enqueue_acquire_collection(session, app_settings, collection.id)
    assert inline.status == JobStatus.QUEUED.value

    class FakeAsync:
        id = "task-1"

    class FakeCelery:
        def send_task(self, *args, **kwargs):
            return FakeAsync()

    monkeypatch.setattr(tasks, "_celery_app", lambda: FakeCelery())
    job = tasks.enqueue_acquire_collection(session, _settings(app_settings), collection.id)
    assert job.task_id == "task-1"

    class BrokenCelery:
        def send_task(self, *args, **kwargs):
            raise RuntimeError("broker down")

    monkeypatch.setattr(tasks, "_celery_app", lambda: BrokenCelery())
    with pytest.raises(Exception) as error:
        tasks.enqueue_acquire_collection(session, _settings(app_settings), collection.id)
    assert getattr(error.value, "code", None) == "SERVICE_UNAVAILABLE"


def test_enqueue_sync_and_reconcile(session: Session, seeded, app_settings, monkeypatch) -> None:
    run_id = uuid.uuid4()
    monkeypatch.setattr(tasks, "run_sync_task", lambda *a, **k: {"ok": True})
    inline = tasks.enqueue_sync_run(session, app_settings, run_id)
    assert inline.status == JobStatus.QUEUED.value

    class FakeAsync:
        id = "sync-task"

    class FakeCelery:
        def send_task(self, *args, **kwargs):
            return FakeAsync()

    monkeypatch.setattr(tasks, "_celery_app", lambda: FakeCelery())
    job = tasks.enqueue_sync_run(session, _settings(app_settings), run_id, reconcile=True)
    assert job.task_id == "sync-task" and job.task_name == tasks.RECONCILE_SYNC_RUN_TASK

    class BrokenCelery:
        def send_task(self, *args, **kwargs):
            raise RuntimeError("down")

    monkeypatch.setattr(tasks, "_celery_app", lambda: BrokenCelery())
    with pytest.raises(ServiceUnavailableError):
        tasks.enqueue_sync_run(session, _settings(app_settings), run_id)

    control = tasks.record_control_job(
        session, task_name="control", payload={"x": 1}, result={"ok": True}
    )
    assert control.status == JobStatus.SUCCEEDED.value


def test_acquire_collection_task_missing_and_success(
    session: Session, seeded, app_settings, monkeypatch
) -> None:
    monkeypatch.setattr(tasks, "get_settings", lambda: app_settings)
    missing = tasks.acquire_collection_task(uuid.uuid4())
    assert missing["status"] == JobStatus.FAILED.value
    assert missing["error_code"] == "RESOURCE_NOT_FOUND"

    collection = collections_repo.get_collection_by_slug(session, "netflix-movie")
    assert collection is not None
    outcome = SimpleNamespace(
        snapshot_id=uuid.uuid4(),
        status=SimpleNamespace(value="COMPLETE"),
        is_valid=True,
        items_count=3,
        errors=[],
    )

    class FakeConnector:
        def close(self):
            pass

    monkeypatch.setattr(tasks.registry, "create_connector", lambda *a, **k: FakeConnector())
    monkeypatch.setattr(tasks.acquisition, "acquire_collection", lambda *a, **k: outcome)
    result = tasks.acquire_collection_task(collection.id)
    assert result["status"] == JobStatus.SUCCEEDED.value
    assert result["items_count"] == 3


def test_run_sync_task_missing_run_and_credential_error(
    session: Session, app_settings, monkeypatch
) -> None:
    monkeypatch.setattr(tasks, "get_settings", lambda: app_settings)
    missing = tasks.run_sync_task(uuid.uuid4())
    assert missing["error_code"] == "RUN_NOT_FOUND"


def _run_fixture(session: Session, seeded):
    from app.db.models import CollectionSnapshot, SnapshotItem
    from app.repositories import media as media_repo

    collection = collections_repo.get_collection_by_slug(session, "netflix-movie")
    assert collection is not None
    media = media_repo.resolve_media(
        session, media_type="MOVIE", tmdb_id=9911, imdb_id=None, title="Task media", year=2020
    )
    assert media is not None
    snapshot = CollectionSnapshot(
        collection_id=collection.id,
        status="COMPLETE",
        quality="CLEAN",
        is_valid=True,
        items_count=1,
        resolved_count=1,
        unresolved_count=0,
        duplicate_count=0,
        error_count=0,
        checksum="task-checksum",
    )
    session.add(snapshot)
    session.flush()
    session.add(
        SnapshotItem(
            snapshot_id=snapshot.id,
            media_id=media.id,
            position=0,
            date_basis="UNKNOWN",
            resolution_status="RESOLVED",
        )
    )
    collection.last_valid_snapshot_id = snapshot.id
    target = targets_repo.create_target(
        session, remote_list_id=5551, name="Task", mediatype="MOVIE"
    )
    binding = bindings_repo.create_binding(
        session,
        collection_id=collection.id,
        target_id=target.id,
        media_type="MOVIE",
        mode="MIRROR",
        schedule_cron="",
        timezone="Europe/Rome",
        is_enabled=True,
        policy_version="v1",
        policy_accepted_at=utcnow(),
        policy_accepted_by=None,
        max_removal_absolute=50,
        max_removal_percent=10.0,
        max_addition_percent=50.0,
        preserve_order=False,
        reorder_enabled=True,
        require_manual_review=True,
        schedule_policy="AUTO_APPLY_IF_SAFE",
        auto_apply_max_removals=5,
        auto_apply_max_removal_ratio=2.0,
        max_plan_age_minutes=60,
        next_run_at=None,
    )
    run = runs_repo.create_run(
        session,
        binding_id=binding.id,
        target_id=target.id,
        media_type="MOVIE",
        snapshot_id=snapshot.id,
        mode="MIRROR",
        trigger_type="MANUAL",
        is_dry_run=False,
    )
    session.commit()
    return run


def test_run_sync_task_success_and_errors(
    session: Session, seeded, app_settings, monkeypatch
) -> None:
    run = _run_fixture(session, seeded)
    monkeypatch.setattr(tasks, "get_settings", lambda: app_settings)

    class FakeClient:
        def close(self):
            pass

    monkeypatch.setattr(tasks.sync_service, "build_client", lambda db, settings: FakeClient())
    monkeypatch.setattr(
        tasks.sync_service,
        "execute_run",
        lambda *a, **k: SimpleNamespace(
            run_id=run.id,
            status="SUCCEEDED",
            added=1,
            removed=0,
            failed=0,
            uncertain=0,
            order_enforced=True,
            warnings=[],
            abort_reason=None,
        ),
    )
    result = tasks.run_sync_task(run.id)
    assert result["status"] == "SUCCEEDED"

    # Auth abort sends a notification without failing the task.
    called: list[str] = []
    monkeypatch.setattr(
        tasks.sync_service,
        "execute_run",
        lambda *a, **k: SimpleNamespace(
            run_id=run.id,
            status="BLOCKED",
            added=0,
            removed=0,
            failed=0,
            uncertain=0,
            order_enforced=False,
            warnings=[],
            abort_reason="MDBLIST_AUTH_FAILED",
        ),
    )
    monkeypatch.setattr(
        "app.services.notifications.notify_auth_error", lambda *a, **k: called.append("notified")
    )
    result = tasks.run_sync_task(run.id)
    assert called == ["notified"]
    assert result["abort_reason"] == "MDBLIST_AUTH_FAILED"

    monkeypatch.setattr(
        tasks.sync_service,
        "build_client",
        lambda db, settings: (_ for _ in ()).throw(tasks.CredentialMissingError("missing")),
    )
    result = tasks.run_sync_task(run.id)
    assert result["error_code"] == "CREDENTIAL_MISSING"

    monkeypatch.setattr(tasks.sync_service, "build_client", lambda db, settings: FakeClient())
    monkeypatch.setattr(
        tasks.sync_service,
        "execute_run",
        lambda *a, **k: (_ for _ in ()).throw(tasks.NotFoundError("not found")),
    )
    result = tasks.run_sync_task(run.id)
    assert result["error_code"] == "RESOURCE_NOT_FOUND"

    monkeypatch.setattr(
        tasks.sync_service,
        "reconcile_run",
        lambda *a, **k: SimpleNamespace(
            run_id=run.id,
            status="SUCCEEDED",
            added=0,
            removed=0,
            failed=0,
            uncertain=0,
            order_enforced=True,
            warnings=[],
            abort_reason=None,
        ),
    )
    result = tasks.reconcile_sync_run_task(run.id)
    assert result["status"] == "SUCCEEDED"
