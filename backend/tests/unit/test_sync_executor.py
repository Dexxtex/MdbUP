"""Sync executor unit tests with a fake MDBList client (SQLite, no network)."""

from __future__ import annotations

import uuid
from collections.abc import Iterator, Sequence

import pytest
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.db.models import CollectionSnapshot, SnapshotItem
from app.db.session import get_session_factory
from app.domain.enums import SyncOperationStatus, SyncRunStatus
from app.integrations.mdblist.client import MdbListPermissionError, MdbListTimeout
from app.integrations.mdblist.models import (
    MdbListId,
    MdbListItemPage,
    MdbListList,
    MdbListListItem,
    MdbListMutationResult,
    MdbListReorderResult,
    MdbListUser,
)
from app.repositories import bindings as bindings_repo
from app.repositories import collections as collections_repo
from app.repositories import media as media_repo
from app.repositories import runs as runs_repo
from app.repositories import targets as targets_repo
from app.services import sync as sync_service


class FakeMdbListClient:
    def __init__(
        self,
        items: Sequence[MdbListListItem] = (),
        *,
        timeout_once: bool = False,
        not_found: bool = False,
        reorder_error: bool = False,
    ) -> None:
        self.items = list(items)
        self.timeout_once = timeout_once
        self.not_found = not_found
        self.reorder_error = reorder_error
        self.add_calls: list[list[MdbListId]] = []
        self.remove_calls: list[list[MdbListId]] = []
        self.reorder_calls: list[list[tuple[str, MdbListId]]] = []

    def get_list(self, list_id: int) -> MdbListList:
        return MdbListList(
            id=list_id,
            name="Test list",
            mediatype="MOVIE",
            user_id=5,
            private=False,
            item_count=len(self.items),
        )

    def get_user(self) -> MdbListUser:
        return MdbListUser(id=5, user_name="owner")

    def get_items(self, list_id: int, **kwargs: object) -> MdbListItemPage:
        return MdbListItemPage(items=tuple(self.items), next_cursor=None, has_more=False)

    def add_items(
        self, list_id: int, *, movies: Sequence[MdbListId] = (), shows: Sequence[MdbListId] = ()
    ) -> MdbListMutationResult:
        self.add_calls.append(list(movies))
        if self.timeout_once:
            self.timeout_once = False
            self.items.extend(
                MdbListListItem(mediatype="MOVIE", tmdb_id=movie.tmdb) for movie in movies
            )
            raise MdbListTimeout("timeout dopo l'invio")
        if self.not_found:
            return MdbListMutationResult(not_found={"movies": len(movies)})
        self.items.extend(
            MdbListListItem(mediatype="MOVIE", tmdb_id=movie.tmdb) for movie in movies
        )
        return MdbListMutationResult(added={"movies": len(movies)})

    def remove_items(
        self, list_id: int, *, movies: Sequence[MdbListId] = (), shows: Sequence[MdbListId] = ()
    ) -> MdbListMutationResult:
        self.remove_calls.append(list(movies))
        removed_ids = {movie.tmdb for movie in movies}
        self.items = [item for item in self.items if item.tmdb_id not in removed_ids]
        return MdbListMutationResult(removed={"movies": len(removed_ids)})

    def reorder(
        self,
        list_id: int,
        items: Sequence[tuple[str, MdbListId]],
        **kwargs: object,
    ) -> MdbListReorderResult:
        if self.reorder_error:
            raise MdbListPermissionError("reorder non consentito")
        self.reorder_calls.append(list(items))
        return MdbListReorderResult(updated=len(items))


@pytest.fixture()
def session(db) -> Iterator[Session]:
    factory = get_session_factory()
    db_session = factory()
    try:
        yield db_session
    finally:
        db_session.close()


def _snapshot(db: Session, collection, tmdb_ids: Sequence[int]) -> CollectionSnapshot:
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
        checksum="snapshot-checksum",
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


def _binding(
    db: Session,
    collection,
    target,
    *,
    mode: str = "MIRROR",
    preserve_order: bool = False,
    reorder_enabled: bool = True,
):
    binding = bindings_repo.create_binding(
        db,
        collection_id=collection.id,
        target_id=target.id,
        media_type=collection.media_type,
        mode=mode,
        schedule_cron="",
        timezone="Europe/Rome",
        is_enabled=True,
        policy_version="v1",
        policy_accepted_at=utcnow(),
        policy_accepted_by=None,
        max_removal_absolute=100,
        max_removal_percent=100.0,
        max_addition_percent=100.0,
        preserve_order=preserve_order,
        reorder_enabled=reorder_enabled,
        require_manual_review=True,
        schedule_policy="AUTO_APPLY_IF_SAFE",
        auto_apply_max_removals=100,
        auto_apply_max_removal_ratio=100.0,
        max_plan_age_minutes=60,
        next_run_at=None,
    )
    db.commit()
    return binding


def _run(db: Session, binding, snapshot, *, dry_run: bool = False):
    run = runs_repo.create_run(
        db,
        binding_id=binding.id,
        target_id=binding.target_id,
        media_type=binding.media_type,
        snapshot_id=snapshot.id,
        mode=binding.mode,
        trigger_type="MANUAL",
        is_dry_run=dry_run,
    )
    db.commit()
    return run


def _target(db: Session, remote_list_id: int = 42):
    target = targets_repo.create_target(
        db, remote_list_id=remote_list_id, name="Test list", mediatype="MOVIE"
    )
    db.commit()
    return target


def test_mirror_applies_add_then_remove_and_verifies(
    session: Session, seeded, app_settings
) -> None:
    collection = collections_repo.get_collection_by_slug(session, "netflix-movie")
    assert collection is not None
    snapshot = _snapshot(session, collection, [1, 2])
    target = _target(session)
    binding = _binding(session, collection, target)
    run = _run(session, binding, snapshot)
    client = FakeMdbListClient(
        [
            MdbListListItem(mediatype="MOVIE", tmdb_id=2),
            MdbListListItem(mediatype="MOVIE", tmdb_id=3),
        ]
    )

    outcome = sync_service.execute_run(
        session, app_settings, run.id, client=client, sleep=lambda _: None
    )

    assert outcome.status == SyncRunStatus.SUCCEEDED.value
    assert outcome.added == 1
    assert outcome.removed == 1
    assert client.add_calls == [[MdbListId(tmdb=1)]]
    assert client.remove_calls == [[MdbListId(tmdb=3)]]
    operations = runs_repo.list_operations(session, run.id)
    assert {operation.status for operation in operations} == {SyncOperationStatus.SUCCEEDED.value}


def test_timeout_marks_uncertain_then_reconciles_from_remote(
    session: Session, seeded, app_settings
) -> None:
    collection = collections_repo.get_collection_by_slug(session, "netflix-movie")
    assert collection is not None
    snapshot = _snapshot(session, collection, [1])
    target = _target(session)
    binding = _binding(session, collection, target)
    run = _run(session, binding, snapshot)
    client = FakeMdbListClient(timeout_once=True)

    outcome = sync_service.execute_run(
        session, app_settings, run.id, client=client, sleep=lambda _: None
    )

    assert outcome.status == SyncRunStatus.SUCCEEDED.value
    assert outcome.added == 1
    operations = runs_repo.list_operations(session, run.id)
    assert operations[0].status == SyncOperationStatus.SUCCEEDED.value
    assert operations[0].reconciled_at is not None


def test_reorder_failure_is_a_warning_not_a_partial(session: Session, seeded, app_settings) -> None:
    collection = collections_repo.get_collection_by_slug(session, "netflix-movie")
    assert collection is not None
    snapshot = _snapshot(session, collection, [1, 2])
    target = _target(session)
    binding = _binding(session, collection, target, preserve_order=True)
    run = _run(session, binding, snapshot)
    client = FakeMdbListClient(
        [
            MdbListListItem(mediatype="MOVIE", tmdb_id=2),
            MdbListListItem(mediatype="MOVIE", tmdb_id=1),
        ],
        reorder_error=True,
    )

    outcome = sync_service.execute_run(
        session, app_settings, run.id, client=client, sleep=lambda _: None
    )

    assert outcome.status == SyncRunStatus.SUCCEEDED.value
    assert outcome.order_enforced is False
    assert "ORDER_NOT_ENFORCED" in outcome.warnings


def test_not_found_is_recorded_and_suppresses_after_three_runs(
    session: Session, seeded, app_settings
) -> None:
    collection = collections_repo.get_collection_by_slug(session, "netflix-movie")
    assert collection is not None
    snapshot = _snapshot(session, collection, [1])
    target = _target(session)
    binding = _binding(session, collection, target)

    for _ in range(3):
        run = _run(session, binding, snapshot)
        client = FakeMdbListClient(not_found=True)
        outcome = sync_service.execute_run(
            session, app_settings, run.id, client=client, sleep=lambda _: None
        )
        assert outcome.status == SyncRunStatus.FAILED.value

    media = media_repo.find_by_tmdb(session, "MOVIE", 1)
    assert media is not None
    assert media.not_found_count == 3
    assert media.sync_suppressed_until is not None

    suppressed_run = _run(session, binding, snapshot)
    suppressed_client = FakeMdbListClient()
    outcome = sync_service.execute_run(
        session, app_settings, suppressed_run.id, client=suppressed_client, sleep=lambda _: None
    )
    assert outcome.status == SyncRunStatus.SUCCEEDED.value
    assert suppressed_client.add_calls == []
    assert "SUPPRESSED_MEDIA_SKIPPED" in outcome.warnings


def test_dry_run_never_writes(session: Session, seeded, app_settings) -> None:
    collection = collections_repo.get_collection_by_slug(session, "netflix-movie")
    assert collection is not None
    snapshot = _snapshot(session, collection, [1])
    target = _target(session)
    binding = _binding(session, collection, target)
    run = _run(session, binding, snapshot, dry_run=True)
    client = FakeMdbListClient()

    outcome = sync_service.execute_run(
        session, app_settings, run.id, client=client, sleep=lambda _: None
    )

    assert outcome.status == SyncRunStatus.SUCCEEDED.value
    assert client.add_calls == []
    assert client.remove_calls == []
    assert run.to_add_count == 1


def test_threshold_breach_waits_for_approval(session: Session, seeded, app_settings) -> None:
    collection = collections_repo.get_collection_by_slug(session, "netflix-movie")
    assert collection is not None
    snapshot = _snapshot(session, collection, [1, 2])
    target = _target(session)
    binding = _binding(session, collection, target)
    binding.max_addition_percent = 10.0
    session.commit()
    run = _run(session, binding, snapshot)
    client = FakeMdbListClient([MdbListListItem(mediatype="MOVIE", tmdb_id=1)])

    outcome = sync_service.execute_run(
        session, app_settings, run.id, client=client, sleep=lambda _: None
    )

    assert outcome.status == SyncRunStatus.AWAITING_APPROVAL.value
    assert run.plan_hash is not None
    assert client.add_calls == []


def test_lock_is_exclusive_per_target(session: Session) -> None:
    target_id = uuid.uuid4()
    first = sync_service.TargetLock(session, target_id)
    second = sync_service.TargetLock(session, target_id)
    assert first.acquire() is True
    try:
        assert second.acquire() is False
    finally:
        first.release()
    assert second.acquire() is True
    second.release()
