"""One active binding per MDBList target: API service and scheduler guardrails."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.errors import ConflictError
from app.api.schemas_sync import BindingCreateIn, BindingUpdateIn
from app.core.time import utcnow
from app.db.models import CollectionSnapshot, SyncBinding, SyncRun
from app.db.session import get_session_factory
from app.jobs import scheduler
from app.repositories import bindings as bindings_repo
from app.repositories import collections as collections_repo
from app.repositories import media as media_repo
from app.repositories import targets as targets_repo
from app.services import bindings as bindings_service


@pytest.fixture()
def session(db) -> Session:
    factory = get_session_factory()
    db_session = factory()
    try:
        yield db_session
    finally:
        db_session.close()


def _target(session: Session):
    target = targets_repo.create_target(
        session, remote_list_id=777, name="Lista condivisa", mediatype="MOVIE"
    )
    session.commit()
    return target


def _collection(session: Session, slug: str):
    collection = collections_repo.get_collection_by_slug(session, slug)
    assert collection is not None
    return collection


def _payload(collection_id, target_id, *, enabled: bool, policy_version: str | None = "v1"):
    return BindingCreateIn(
        collection_id=collection_id,
        target_id=target_id,
        enabled=enabled,
        policy_version=policy_version,
        thresholds={"max_removal_pct": 10, "max_removal_abs": 50, "max_addition_pct": 50},
    )


def _snapshot(session: Session, collection) -> None:
    media = media_repo.resolve_media(
        session,
        media_type=collection.media_type,
        tmdb_id=101,
        imdb_id=None,
        title="Media 101",
        year=2020,
    )
    assert media is not None
    snapshot = CollectionSnapshot(
        collection_id=collection.id,
        status="COMPLETE",
        quality="CLEAN",
        is_valid=True,
        started_at=utcnow(),
        finished_at=utcnow(),
        items_count=1,
        resolved_count=1,
        unresolved_count=0,
        duplicate_count=0,
        error_count=0,
        checksum="checksum",
    )
    session.add(snapshot)
    session.flush()
    collection.last_valid_snapshot_id = snapshot.id
    session.commit()


def _detached_binding(target_id: uuid.UUID, *, created_at) -> SyncBinding:
    binding = SyncBinding(
        collection_id=uuid.uuid4(),
        target_id=target_id,
        media_type="MOVIE",
        mode="MIRROR",
        schedule_cron="0 6 * * *",
        schedule_interval_hours=None,
        timezone="Europe/Rome",
        is_enabled=True,
        policy_version="v1",
        policy_accepted_at=created_at,
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
    )
    binding.created_at = created_at
    return binding


def _dry_run(session: Session, binding: SyncBinding, collection) -> None:
    assert collection.last_valid_snapshot_id is not None
    session.add(
        SyncRun(
            binding_id=binding.id,
            target_id=binding.target_id,
            media_type=binding.media_type,
            snapshot_id=collection.last_valid_snapshot_id,
            mode=binding.mode,
            status="SUCCEEDED",
            is_dry_run=True,
            trigger_type="MANUAL",
            started_at=utcnow(),
            finished_at=utcnow(),
        )
    )
    session.commit()


def _legacy_binding(
    session: Session, collection, target, *, created_at, enabled: bool = True
) -> SyncBinding:
    binding = bindings_repo.create_binding(
        session,
        collection_id=collection.id,
        target_id=target.id,
        media_type=collection.media_type,
        mode="MIRROR",
        schedule_cron="0 6 * * *",
        timezone="Europe/Rome",
        is_enabled=enabled,
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
    binding.created_at = created_at
    session.commit()
    return binding


def test_second_enabled_binding_on_a_target_is_rejected(
    session: Session, seeded, app_settings
) -> None:
    first_collection = _collection(session, "netflix-movie")
    second_collection = _collection(session, "prime-video-movie")
    target = _target(session)
    bindings_service.create_binding(
        session, app_settings, _payload(first_collection.id, target.id, enabled=True)
    )

    with pytest.raises(ConflictError) as excinfo:
        bindings_service.create_binding(
            session, app_settings, _payload(second_collection.id, target.id, enabled=True)
        )

    assert excinfo.value.code == "TARGET_LOCKED"
    active = bindings_repo.list_bindings(session, target_id=target.id, enabled=True)
    assert len(active) == 1


def test_enabling_a_second_binding_on_a_target_is_rejected(
    session: Session, seeded, app_settings
) -> None:
    first_collection = _collection(session, "netflix-movie")
    second_collection = _collection(session, "prime-video-movie")
    target = _target(session)
    bindings_service.create_binding(
        session, app_settings, _payload(first_collection.id, target.id, enabled=True)
    )
    dormant = bindings_service.create_binding(
        session, app_settings, _payload(second_collection.id, target.id, enabled=False)
    )

    with pytest.raises(ConflictError) as excinfo:
        bindings_service.update_binding(
            session, app_settings, dormant.id, BindingUpdateIn(enabled=True)
        )

    assert excinfo.value.code == "TARGET_LOCKED"
    stored = bindings_repo.get_binding(session, dormant.id)
    assert stored is not None
    assert stored.is_enabled is False


def test_database_rejects_two_enabled_bindings_on_the_same_target(
    session: Session, seeded, app_settings
) -> None:
    """The partial unique index is the last line of defence, not only the API."""
    first_collection = _collection(session, "netflix-movie")
    second_collection = _collection(session, "prime-video-movie")
    target = _target(session)
    bindings_service.create_binding(
        session, app_settings, _payload(first_collection.id, target.id, enabled=True)
    )
    dormant = _legacy_binding(
        session, second_collection, target, created_at=utcnow(), enabled=False
    )
    dormant.is_enabled = True

    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_scheduler_owner_is_the_oldest_enabled_binding() -> None:
    now = utcnow()
    target_id = uuid.uuid4()
    other_target = uuid.uuid4()
    owner = _detached_binding(target_id, created_at=now - timedelta(days=1))
    intruder = _detached_binding(target_id, created_at=now)
    alone = _detached_binding(other_target, created_at=now)

    owners = scheduler.target_binding_owner([intruder, alone, owner])

    assert owners[target_id] == owner.id
    assert owners[other_target] == alone.id


def test_scheduler_skips_a_non_owner_binding_of_a_locked_target(
    session: Session, seeded, app_settings, monkeypatch
) -> None:
    first_collection = _collection(session, "netflix-movie")
    second_collection = _collection(session, "prime-video-movie")
    _snapshot(session, first_collection)
    _snapshot(session, second_collection)
    target = _target(session)
    owner = _legacy_binding(
        session, first_collection, target, created_at=utcnow() - timedelta(days=1)
    )
    _dry_run(session, owner, first_collection)
    # Disabled in the database (one enabled row per target is enforced there),
    # but presented as due to the scheduler to exercise its own guard.
    intruder = _legacy_binding(
        session, second_collection, target, created_at=utcnow(), enabled=False
    )
    monkeypatch.setattr(bindings_repo, "list_due_bindings", lambda *_a, **_k: [intruder, owner])
    monkeypatch.setattr(bindings_repo, "list_bindings", lambda *_a, **_k: [owner, intruder])

    outcome = scheduler.enqueue_due_bindings(session, app_settings, now=utcnow(), dispatch=False)

    assert outcome.enqueued == 1
    assert outcome.skipped == 1
    runs = list(session.scalars(select(SyncRun)).all())
    scheduled = [run for run in runs if not run.is_dry_run]
    assert len(scheduled) == 1
    assert scheduled[0].binding_id == owner.id
