"""Scheduler and retention unit tests (SQLite, no Celery broker)."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.locks import DispatchLock
from app.core.time import ensure_utc, utcnow
from app.db.models import CollectionSnapshot, SnapshotItem, SyncRun
from app.db.session import get_session_factory
from app.domain.enums import SyncRunStatus
from app.jobs import scheduler
from app.repositories import bindings as bindings_repo
from app.repositories import collections as collections_repo
from app.repositories import media as media_repo
from app.repositories import providers as providers_repo
from app.repositories import runs as runs_repo
from app.repositories import sources as sources_repo
from app.repositories import targets as targets_repo


@pytest.fixture()
def session(db) -> Session:
    factory = get_session_factory()
    db_session = factory()
    try:
        yield db_session
    finally:
        db_session.close()


def _snapshot(db: Session, collection, tmdb_ids: list[int]) -> CollectionSnapshot:
    media_ids = []
    for tmdb_id in tmdb_ids:
        media = media_repo.resolve_media(
            db,
            media_type=collection.media_type,
            tmdb_id=tmdb_id,
            imdb_id=None,
            title=f"Media {tmdb_id}",
            year=2020,
        )
        assert media is not None
        media_ids.append(media.id)
    snapshot = CollectionSnapshot(
        collection_id=collection.id,
        status="COMPLETE",
        quality="CLEAN",
        is_valid=True,
        items_count=len(media_ids),
        resolved_count=len(media_ids),
        unresolved_count=0,
        duplicate_count=0,
        error_count=0,
        checksum="checksum",
    )
    db.add(snapshot)
    db.flush()
    for position, media_id in enumerate(media_ids):
        db.add(
            SnapshotItem(
                snapshot_id=snapshot.id,
                media_id=media_id,
                position=position,
                date_basis="UNKNOWN",
                resolution_status="RESOLVED",
            )
        )
    collection.last_valid_snapshot_id = snapshot.id
    db.commit()
    return snapshot


def _succeeded_dry_run(db: Session, binding, snapshot_id) -> None:
    db.add(
        SyncRun(
            binding_id=binding.id,
            target_id=binding.target_id,
            media_type=binding.media_type,
            snapshot_id=snapshot_id,
            mode=binding.mode,
            status="SUCCEEDED",
            is_dry_run=True,
            trigger_type="MANUAL",
            started_at=utcnow(),
            finished_at=utcnow(),
        )
    )
    db.commit()


def _binding(db: Session, collection, *, schedule_policy: str = "AUTO_APPLY_IF_SAFE"):
    target = targets_repo.create_target(db, remote_list_id=42, name="Test list", mediatype="MOVIE")
    binding = bindings_repo.create_binding(
        db,
        collection_id=collection.id,
        target_id=target.id,
        media_type=collection.media_type,
        mode="MIRROR",
        schedule_cron="0 6 * * *",
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
        schedule_policy=schedule_policy,
        auto_apply_max_removals=5,
        auto_apply_max_removal_ratio=2.0,
        max_plan_age_minutes=60,
        next_run_at=None,
    )
    db.commit()
    if collection.last_valid_snapshot_id is not None:
        _succeeded_dry_run(db, binding, collection.last_valid_snapshot_id)
    return binding


def test_due_binding_creates_one_scheduled_run_per_slot(
    session: Session, seeded, app_settings
) -> None:
    collection = collections_repo.get_collection_by_slug(session, "netflix-movie")
    assert collection is not None
    _snapshot(session, collection, [1])
    binding = _binding(session, collection)
    now = utcnow()

    first = scheduler.enqueue_due_bindings(session, app_settings, now=now, dispatch=False)
    assert first.enqueued == 1
    assert first.skipped == 0
    run = runs_repo.get_run(session, first.run_ids[0])
    assert run is not None
    assert run.trigger_type == "SCHEDULED"
    assert run.is_dry_run is False
    session.refresh(binding)
    assert binding.next_run_at is not None
    assert ensure_utc(binding.next_run_at) > now

    second = scheduler.enqueue_due_bindings(session, app_settings, now=now, dispatch=False)
    assert second.enqueued == 0


def test_scheduler_skips_real_run_without_a_dry_run(session: Session, seeded, app_settings) -> None:
    collection = collections_repo.get_collection_by_slug(session, "netflix-movie")
    assert collection is not None
    _snapshot(session, collection, [1])
    binding = _binding(session, collection)
    session.execute(delete(SyncRun).where(SyncRun.binding_id == binding.id))
    session.commit()

    outcome = scheduler.enqueue_due_bindings(session, app_settings, now=utcnow(), dispatch=False)

    assert outcome.enqueued == 0
    assert outcome.skipped == 1


def test_dry_run_only_policy_creates_a_dry_run(session: Session, seeded, app_settings) -> None:
    collection = collections_repo.get_collection_by_slug(session, "netflix-movie")
    assert collection is not None
    _snapshot(session, collection, [1])
    _binding(session, collection, schedule_policy="DRY_RUN_ONLY")

    outcome = scheduler.enqueue_due_bindings(session, app_settings, now=utcnow(), dispatch=False)
    run = runs_repo.get_run(session, outcome.run_ids[0])
    assert run is not None
    assert run.is_dry_run is True


def test_cleanup_deletes_old_terminal_runs_and_keeps_last_valid_snapshot(
    session: Session, seeded, app_settings
) -> None:
    collection = collections_repo.get_collection_by_slug(session, "netflix-movie")
    assert collection is not None
    snapshot = _snapshot(session, collection, [1])
    binding = _binding(session, collection)
    old = utcnow() - timedelta(days=400)
    recent = utcnow() - timedelta(days=1)

    def terminal_run(status: SyncRunStatus, finished_at):
        run = runs_repo.create_run(
            session,
            binding_id=binding.id,
            target_id=binding.target_id,
            media_type=binding.media_type,
            snapshot_id=snapshot.id,
            mode="MIRROR",
            trigger_type="MANUAL",
            is_dry_run=False,
        )
        runs_repo.transition_run(session, run, SyncRunStatus.PREFLIGHT)
        runs_repo.transition_run(session, run, SyncRunStatus.PLANNING)
        if status not in (SyncRunStatus.BLOCKED, SyncRunStatus.FAILED):
            runs_repo.transition_run(session, run, SyncRunStatus.APPLYING)
        if status in (SyncRunStatus.SUCCEEDED, SyncRunStatus.PARTIAL):
            runs_repo.transition_run(session, run, SyncRunStatus.VERIFYING)
        runs_repo.finish_run(session, run, status)
        run.finished_at = finished_at
        session.commit()
        return run

    succeeded = terminal_run(SyncRunStatus.SUCCEEDED, old)
    partial = terminal_run(SyncRunStatus.PARTIAL, old)
    failed = terminal_run(SyncRunStatus.FAILED, old)
    blocked = terminal_run(SyncRunStatus.BLOCKED, old)
    recent_failed = terminal_run(SyncRunStatus.FAILED, recent)

    result = scheduler.cleanup_old_data(session, app_settings, now=utcnow())
    assert result["runs_deleted"] == 4
    for run in (succeeded, partial, failed, blocked):
        assert runs_repo.get_run(session, run.id) is None
    assert runs_repo.get_run(session, recent_failed.id) is not None
    # The last valid snapshot is never deleted.
    assert session.get(CollectionSnapshot, snapshot.id) is not None


def _interval_binding(db: Session, collection, *, hours: int = 2):
    target = targets_repo.create_target(
        db, remote_list_id=77, name="Interval list", mediatype="MOVIE"
    )
    binding = bindings_repo.create_binding(
        db,
        collection_id=collection.id,
        target_id=target.id,
        media_type=collection.media_type,
        mode="MIRROR",
        schedule_cron="",
        schedule_interval_hours=hours,
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
        next_run_at=utcnow() - timedelta(minutes=1),
    )
    db.commit()
    if collection.last_valid_snapshot_id is not None:
        _succeeded_dry_run(db, binding, collection.last_valid_snapshot_id)
    return binding


def test_interval_binding_is_due_and_advances_by_interval(
    session: Session, seeded, app_settings
) -> None:
    collection = collections_repo.get_collection_by_slug(session, "netflix-movie")
    assert collection is not None
    _snapshot(session, collection, [1])
    binding = _interval_binding(session, collection, hours=2)
    now = utcnow()

    outcome = scheduler.enqueue_due_bindings(session, app_settings, now=now, dispatch=False)
    assert outcome.enqueued == 1
    run = runs_repo.get_run(session, outcome.run_ids[0])
    assert run is not None
    assert run.trigger_type == "SCHEDULED"
    session.refresh(binding)
    assert binding.next_run_at is not None
    assert ensure_utc(binding.next_run_at) >= now + timedelta(hours=2) - timedelta(seconds=5)


def test_dispatch_lock_is_exclusive_across_instances() -> None:
    first = DispatchLock("")
    second = DispatchLock("")
    token = first.acquire("target:42")
    assert token is not None
    try:
        assert second.acquire("target:42") is None
    finally:
        first.release("target:42", token)
    token2 = second.acquire("target:42")
    assert token2 is not None
    second.release("target:42", token2)


def test_scheduler_skips_target_while_dispatch_lock_is_held(
    session: Session, seeded, app_settings
) -> None:
    collection = collections_repo.get_collection_by_slug(session, "netflix-movie")
    assert collection is not None
    _snapshot(session, collection, [1])
    binding = _interval_binding(session, collection, hours=1)
    lock = DispatchLock("")
    token = lock.acquire(f"target:{binding.target_id}")
    assert token is not None
    try:
        blocked = scheduler.enqueue_due_bindings(
            session, app_settings, now=utcnow(), dispatch=False
        )
        assert blocked.enqueued == 0
        assert blocked.skipped == 1
    finally:
        lock.release(f"target:{binding.target_id}", token)

    outcome = scheduler.enqueue_due_bindings(session, app_settings, now=utcnow(), dispatch=False)
    assert outcome.enqueued == 1


def test_cron_to_schedule_keeps_arbitrary_cron_visible() -> None:
    from app.services.bindings import cron_to_schedule

    assert cron_to_schedule("") == ("MANUAL", None)
    assert cron_to_schedule("0 4 * * *") == ("DAILY", "04:00")
    assert cron_to_schedule("* * * * *") == ("CRON", None)


def test_dashboard_estimates_api_usage_from_active_bindings(
    session: Session, seeded, app_settings
) -> None:
    from app.services import dashboard

    collection = collections_repo.get_collection_by_slug(session, "netflix-movie")
    assert collection is not None
    _snapshot(session, collection, [1, 2, 3])
    _binding(session, collection)
    summary = dashboard.get_dashboard(session, app_settings)
    assert summary.api_usage["active_bindings"] == 1
    assert summary.api_usage["tmdb"]["estimated_per_day"] > 0
    assert summary.api_usage["mdblist"]["estimated_per_day"] > 0


def test_cleanup_protects_snapshot_that_owns_reused_items(
    session: Session, seeded, app_settings
) -> None:
    from datetime import timedelta

    from app.core.time import utcnow
    from app.domain.enums import SnapshotQuality, SnapshotStatus

    collection = collections_repo.get_collection_by_slug(session, "netflix-movie")
    assert collection is not None
    old = _snapshot(session, collection, [1])
    old.started_at = utcnow() - timedelta(days=400)
    old.finished_at = old.started_at
    duplicate = CollectionSnapshot(
        collection_id=collection.id,
        status=SnapshotStatus.COMPLETE.value,
        quality=SnapshotQuality.CLEAN.value,
        is_valid=True,
        started_at=utcnow(),
        finished_at=utcnow(),
        items_count=1,
        resolved_count=1,
        items_from_snapshot_id=old.id,
    )
    session.add(duplicate)
    session.flush()
    collection.last_valid_snapshot_id = duplicate.id
    session.flush()

    scheduler.cleanup_old_data(session, app_settings, now=utcnow())

    assert session.get(CollectionSnapshot, old.id) is not None
    assert session.get(CollectionSnapshot, duplicate.id) is not None


def test_sweep_orphan_dispatch_locks_removes_only_inactive_targets() -> None:
    from app.core.locks import sweep_orphan_dispatch_locks

    class FakeRedis:
        def __init__(self) -> None:
            self.keys = {
                "mdbup:dispatch:target:11111111-1111-1111-1111-111111111111": "1",
                "mdbup:dispatch:target:22222222-2222-2222-2222-222222222222": "1",
            }

        def scan_iter(self, **_kwargs):
            return iter(list(self.keys))

        def delete(self, key):
            return 1 if self.keys.pop(key, None) is not None else 0

    fake = FakeRedis()
    removed = sweep_orphan_dispatch_locks(
        "",
        is_active=lambda target_id: target_id.startswith("1111"),
        client=fake,  # type: ignore[arg-type]
    )
    assert removed == 1
    assert "mdbup:dispatch:target:11111111-1111-1111-1111-111111111111" in fake.keys
    assert "mdbup:dispatch:target:22222222-2222-2222-2222-222222222222" not in fake.keys


def test_target_owner_uses_oldest_binding() -> None:
    from app.db.models import SyncBinding

    older = SyncBinding(
        id=uuid.uuid4(), target_id=uuid.uuid4(), created_at=utcnow() - timedelta(hours=1)
    )
    newer = SyncBinding(id=uuid.uuid4(), target_id=older.target_id, created_at=utcnow())
    assert scheduler.target_binding_owner([newer, older])[older.target_id] == older.id


def test_scheduled_snapshot_fallbacks(session: Session, seeded) -> None:
    collection = collections_repo.get_collection_by_slug(session, "netflix-movie")
    assert collection is not None
    # No snapshot at all.
    assert scheduler._scheduled_snapshot(session, collection.id, "MIRROR") is None
    snapshot = _snapshot(session, collection, [1])
    # last_valid_snapshot_id is used.
    assert scheduler._scheduled_snapshot(session, collection.id, "MIRROR").id == snapshot.id
    # Missing last_valid pointer falls back to latest valid.
    collection.last_valid_snapshot_id = None
    session.commit()
    assert scheduler._scheduled_snapshot(session, collection.id, "MIRROR").id == snapshot.id
    assert scheduler._scheduled_snapshot(session, uuid.uuid4(), "MIRROR") is None


def test_sweep_stale_runs_reconciles_and_fails(
    session: Session, seeded, app_settings, monkeypatch
) -> None:
    collection = collections_repo.get_collection_by_slug(session, "netflix-movie")
    assert collection is not None
    snapshot = _snapshot(session, collection, [1])
    binding = _binding(session, collection)
    run = runs_repo.create_run(
        session,
        binding_id=binding.id,
        target_id=binding.target_id,
        media_type=binding.media_type,
        snapshot_id=snapshot.id,
        mode="MIRROR",
        trigger_type="MANUAL",
        is_dry_run=False,
    )
    runs_repo.transition_run(session, run, SyncRunStatus.PREFLIGHT)
    runs_repo.transition_run(session, run, SyncRunStatus.PLANNING)
    runs_repo.transition_run(session, run, SyncRunStatus.APPLYING)
    run.updated_at = utcnow() - timedelta(hours=2)
    session.commit()
    calls: list[str] = []
    monkeypatch.setattr("app.jobs.tasks.enqueue_sync_run", lambda *a, **k: calls.append("ok"))
    outcome = scheduler.sweep_stale_runs(session, app_settings, now=utcnow())
    assert outcome == {"reconciled": 1, "failed": 0}
    assert calls == ["ok"]
    assert runs_repo.get_run(session, run.id).status == SyncRunStatus.VERIFYING.value


def test_sweep_stale_runs_dispatch_failure(
    session: Session, seeded, app_settings, monkeypatch
) -> None:
    collection = collections_repo.get_collection_by_slug(session, "netflix-movie")
    assert collection is not None
    snapshot = _snapshot(session, collection, [1])
    binding = _binding(session, collection)
    run = runs_repo.create_run(
        session,
        binding_id=binding.id,
        target_id=binding.target_id,
        media_type=binding.media_type,
        snapshot_id=snapshot.id,
        mode="MIRROR",
        trigger_type="MANUAL",
        is_dry_run=False,
    )
    runs_repo.transition_run(session, run, SyncRunStatus.PREFLIGHT)
    runs_repo.transition_run(session, run, SyncRunStatus.PLANNING)
    runs_repo.transition_run(session, run, SyncRunStatus.APPLYING)
    run.updated_at = utcnow() - timedelta(hours=2)
    session.commit()
    monkeypatch.setattr(
        "app.jobs.tasks.enqueue_sync_run",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")),
    )
    outcome = scheduler.sweep_stale_runs(session, app_settings, now=utcnow())
    assert outcome["failed"] == 1
    assert runs_repo.get_run(session, run.id).status == SyncRunStatus.FAILED.value


def test_sweep_orphan_locks(session: Session, app_settings, monkeypatch) -> None:
    monkeypatch.setattr(scheduler, "sweep_orphan_dispatch_locks", lambda url, is_active: 3)
    assert scheduler.sweep_orphan_locks(session, app_settings) == {"removed": 3}


def test_scheduler_dispatch_failure_marks_run_failed(
    session: Session, seeded, app_settings, monkeypatch
) -> None:
    collection = collections_repo.get_collection_by_slug(session, "netflix-movie")
    assert collection is not None
    _snapshot(session, collection, [1])
    _binding(session, collection)
    monkeypatch.setattr(
        "app.jobs.tasks.enqueue_sync_run",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")),
    )
    outcome = scheduler.enqueue_due_bindings(session, app_settings, now=utcnow(), dispatch=True)
    assert outcome.enqueued == 0
    assert outcome.skipped == 1


def test_scheduler_skips_when_dispatch_lock_is_held(
    session: Session, seeded, app_settings, monkeypatch
) -> None:
    collection = collections_repo.get_collection_by_slug(session, "netflix-movie")
    assert collection is not None
    _snapshot(session, collection, [1])
    _binding(session, collection)

    class NoLock:
        def acquire(self, key):
            return None

        def release(self, key, token):
            return None

    monkeypatch.setattr(scheduler, "build_dispatch_lock", lambda url: NoLock())
    outcome = scheduler.enqueue_due_bindings(session, app_settings, now=utcnow(), dispatch=False)
    assert outcome.skipped == 1


def test_sweep_stale_runs_fails_pending(session: Session, seeded, app_settings) -> None:
    collection = collections_repo.get_collection_by_slug(session, "netflix-movie")
    assert collection is not None
    snapshot = _snapshot(session, collection, [1])
    binding = _binding(session, collection)
    run = runs_repo.create_run(
        session,
        binding_id=binding.id,
        target_id=binding.target_id,
        media_type=binding.media_type,
        snapshot_id=snapshot.id,
        mode="MIRROR",
        trigger_type="MANUAL",
        is_dry_run=False,
    )
    runs_repo.transition_run(session, run, SyncRunStatus.PREFLIGHT)
    run.updated_at = utcnow() - timedelta(hours=2)
    session.commit()
    outcome = scheduler.sweep_stale_runs(session, app_settings, now=utcnow())
    assert outcome == {"reconciled": 0, "failed": 1}
    assert runs_repo.get_run(session, run.id).status == SyncRunStatus.FAILED.value


def test_scheduler_never_enqueues_automatic_justwatch_sync(
    session: Session, seeded, app_settings
) -> None:
    source = sources_repo.get_source_by_key(session, "justwatch")
    provider = providers_repo.get_provider_by_slug(session, "netflix")
    assert source is not None and provider is not None
    collection = collections_repo.upsert_collection(
        session,
        slug="jw-scheduler-guard",
        source_id=source.id,
        provider_id=provider.id,
        country_code="IT",
        media_type="MOVIE",
        kind="CATALOG",
        origin="AGGREGATOR",
        date_basis="UNKNOWN",
        name="JustWatch scheduler guard",
        filters={"packages": ["nfx"], "offer_types": ["FLATRATE"]},
        offer_types=["FLATRATE"],
        sort_mode="SOURCE_ORDER",
        is_active=True,
    )
    _snapshot(session, collection, [1])
    binding = _binding(session, collection)
    binding.next_run_at = utcnow() - timedelta(minutes=1)
    session.commit()

    outcome = scheduler.enqueue_due_bindings(session, app_settings, now=utcnow(), dispatch=False)

    assert outcome.enqueued == 0
    assert outcome.skipped == 1
    assert outcome.run_ids == []
