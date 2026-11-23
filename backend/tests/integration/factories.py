"""Shared fixtures for provider/collection deletion integration tests."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import utcnow
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
from app.db.session import get_session_factory
from app.domain.enums import ACTIVE_RUN_STATUSES
from app.repositories import media as media_repo
from app.repositories import targets as targets_repo


def provider_with_collection(client, admin) -> tuple[dict, dict]:
    created = client.post(
        "/api/providers",
        json={"slug": "in-uso", "name": "In uso", "tmdb_movie_id": "77777"},
        headers=admin,
    )
    assert created.status_code == 201, created.text
    provider = created.json()
    collection = client.post(
        "/api/collections",
        json={
            "provider_id": provider["id"],
            "media_type": "MOVIE",
            "name": "Collezione del provider",
            "slug": "collezione-provider",
        },
        headers=admin,
    )
    assert collection.status_code == 201, collection.text
    return provider, collection.json()


def attach_local_history(
    provider_id: str, collection_id: str, *, run_status: str
) -> dict[str, str]:
    """Attach a snapshot, item, binding, run, operation and episode event."""
    session = get_session_factory()()
    try:
        collection = session.get(Collection, uuid.UUID(collection_id))
        assert collection is not None
        movie = media_repo.resolve_media(
            session,
            media_type="MOVIE",
            tmdb_id=4242,
            imdb_id=None,
            title="Film locale",
            year=2020,
        )
        show = media_repo.resolve_media(
            session,
            media_type="SHOW",
            tmdb_id=4343,
            imdb_id=None,
            title="Serie locale",
            year=2021,
        )
        assert movie is not None and show is not None
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
            checksum="checksum",
        )
        session.add(snapshot)
        session.flush()
        session.add(
            SnapshotItem(
                snapshot_id=snapshot.id,
                media_id=movie.id,
                position=0,
                date_basis="UNKNOWN",
                resolution_status="RESOLVED",
            )
        )
        collection.last_valid_snapshot_id = snapshot.id
        target = targets_repo.create_target(
            session,
            remote_list_id=98765,
            name="Lista locale",
            mediatype="MOVIE",
        )
        binding = SyncBinding(
            collection_id=collection.id,
            target_id=target.id,
            media_type="MOVIE",
            mode="MIRROR",
            schedule_cron="",
            schedule_interval_hours=None,
            timezone="Europe/Rome",
            is_enabled=False,
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
        session.add(binding)
        session.flush()
        run = SyncRun(
            binding_id=binding.id,
            target_id=target.id,
            media_type="MOVIE",
            snapshot_id=snapshot.id,
            mode="MIRROR",
            status=run_status,
            is_dry_run=False,
            trigger_type="MANUAL",
            started_at=utcnow(),
            finished_at=(
                None if run_status in {status.value for status in ACTIVE_RUN_STATUSES} else utcnow()
            ),
        )
        session.add(run)
        session.flush()
        session.add(SyncRunEvent(run_id=run.id, to_status=run_status))
        session.add(
            SyncOperation(
                run_id=run.id,
                action="ADD",
                media_id=movie.id,
                idempotency_key=f"delete-test-{uuid.uuid4()}",
            )
        )
        session.add(
            EpisodeEvent(
                show_media_id=show.id,
                media_type="SHOW",
                provider_id=uuid.UUID(provider_id),
                country_code="IT",
                source_id=collection.source_id,
                snapshot_id=snapshot.id,
                event_type="SEASON_ADDED",
                season_number=1,
            )
        )
        session.commit()
        return {
            "target": str(target.id),
            "binding": str(binding.id),
            "snapshot": str(snapshot.id),
            "run": str(run.id),
        }
    finally:
        session.close()


def assert_local_history_deleted(ids: dict[str, str]) -> None:
    run_id = uuid.UUID(ids["run"])
    session: Session = get_session_factory()()
    try:
        assert session.get(SyncBinding, uuid.UUID(ids["binding"])) is None
        assert session.get(CollectionSnapshot, uuid.UUID(ids["snapshot"])) is None
        assert session.get(SyncRun, run_id) is None
        assert session.scalar(select(SyncOperation).where(SyncOperation.run_id == run_id)) is None
        assert session.scalar(select(SyncRunEvent).where(SyncRunEvent.run_id == run_id)) is None
    finally:
        session.close()


def assert_no_episode_events() -> None:
    session: Session = get_session_factory()()
    try:
        assert session.scalar(select(EpisodeEvent)) is None
    finally:
        session.close()


def assert_episode_events_detached() -> None:
    """The provider survives a collection delete: its event loses the snapshot link."""
    session: Session = get_session_factory()()
    try:
        event = session.scalar(select(EpisodeEvent))
        assert event is not None
        assert event.snapshot_id is None
    finally:
        session.close()
