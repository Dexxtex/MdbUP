"""Preview use cases: invalid snapshots, remote failures and blocked states."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import Session

from app.db.models import CollectionSnapshot, JobExecution, SnapshotItem
from app.db.session import get_session_factory
from app.domain.commands import PreviewRequest, ThresholdsIn
from app.domain.errors import ConflictError, NotFoundError
from app.repositories import collections as collections_repo
from app.repositories import media as media_repo
from app.repositories import targets as targets_repo
from app.services import previews


@pytest.fixture()
def session(db) -> Session:
    db_session = get_session_factory()()
    try:
        yield db_session
    finally:
        db_session.close()


def _collection_snapshot(session: Session, *, count: int = 1):
    collection = collections_repo.get_collection_by_slug(session, "netflix-movie")
    assert collection is not None
    snapshot = CollectionSnapshot(
        collection_id=collection.id,
        status="COMPLETE",
        quality="CLEAN",
        is_valid=True,
        items_count=count,
        resolved_count=count,
        unresolved_count=0,
        duplicate_count=0,
        error_count=0,
        checksum="preview-checksum",
    )
    session.add(snapshot)
    session.flush()
    for index in range(count):
        media = media_repo.resolve_media(
            session,
            media_type="MOVIE",
            tmdb_id=7700 + index,
            imdb_id=None,
            title=f"Preview {index}",
            year=2020,
        )
        assert media is not None
        session.add(
            SnapshotItem(
                snapshot_id=snapshot.id,
                media_id=media.id,
                position=index,
                date_basis="UNKNOWN",
                resolution_status="RESOLVED",
            )
        )
    collection.last_valid_snapshot_id = snapshot.id
    session.commit()
    return collection, snapshot


def test_preview_validation_errors(session: Session, seeded, app_settings) -> None:
    with pytest.raises(NotFoundError):
        previews.create_preview(session, app_settings, PreviewRequest(collection_id=uuid.uuid4()))
    collection, snapshot = _collection_snapshot(session)
    other = CollectionSnapshot(
        collection_id=collections_repo.get_collection_by_slug(session, "prime-video-movie").id,
        status="COMPLETE",
        quality="CLEAN",
        is_valid=True,
        items_count=1,
        resolved_count=1,
        unresolved_count=0,
        duplicate_count=0,
        error_count=0,
    )
    session.add(other)
    session.commit()
    with pytest.raises(ConflictError) as error:
        previews.create_preview(
            session,
            app_settings,
            PreviewRequest(collection_id=collection.id, snapshot_id=other.id),
        )
    assert error.value.code == "SNAPSHOT_INVALID"
    with pytest.raises(NotFoundError):
        previews.create_preview(
            session,
            app_settings,
            PreviewRequest(collection_id=collection.id, target_id=uuid.uuid4()),
        )
    show_target = targets_repo.create_target(
        session, remote_list_id=7788, name="Show list", mediatype="SHOW"
    )
    session.commit()
    with pytest.raises(ConflictError) as error:
        previews.create_preview(
            session,
            app_settings,
            PreviewRequest(collection_id=collection.id, target_id=show_target.id),
        )
    assert error.value.code == "MEDIA_TYPE_MISMATCH"


def test_source_only_preview_and_blocked_source_snapshot(
    session: Session, seeded, app_settings
) -> None:
    collection, _ = _collection_snapshot(session)
    preview_id = previews.create_preview(
        session, app_settings, PreviewRequest(collection_id=collection.id)
    )
    preview = previews.get_preview(session, preview_id)
    assert preview["state"] == "READY"
    assert preview["plan_hash"] is None

    # Unresolved source items block a MIRROR preview without a remote list.
    from app.db.models import SnapshotItem

    snapshot = CollectionSnapshot(
        collection_id=collection.id,
        status="COMPLETE",
        quality="ANOMALY",
        is_valid=False,
        items_count=1,
        resolved_count=0,
        unresolved_count=1,
        duplicate_count=0,
        error_count=0,
        checksum="unresolved-preview",
    )
    session.add(snapshot)
    session.flush()
    session.add(
        SnapshotItem(
            snapshot_id=snapshot.id,
            media_id=None,
            position=0,
            date_basis="UNKNOWN",
            resolution_status="UNRESOLVED",
        )
    )
    collection.last_valid_snapshot_id = snapshot.id
    session.commit()
    preview_id = previews.create_preview(
        session, app_settings, PreviewRequest(collection_id=collection.id)
    )
    assert previews.get_preview(session, preview_id)["state"] == "BLOCKED"


def test_preview_remote_failure_and_threshold_block(
    session: Session, seeded, app_settings, monkeypatch
) -> None:
    collection, _ = _collection_snapshot(session, count=3)
    target = targets_repo.create_target(
        session, remote_list_id=7799, name="Preview list", mediatype="MOVIE"
    )
    session.commit()

    class FakeClient:
        def close(self):
            pass

    monkeypatch.setattr(previews.sync_service, "build_client", lambda *a, **k: FakeClient())
    monkeypatch.setattr(
        previews.reconciliation,
        "read_all_remote_items",
        lambda *a, **k: (_ for _ in ()).throw(previews.MdbListError("read failed")),
    )
    preview_id = previews.create_preview(
        session, app_settings, PreviewRequest(collection_id=collection.id, target_id=target.id)
    )
    assert previews.get_preview(session, preview_id)["state"] == "FAILED"

    monkeypatch.setattr(
        previews.reconciliation, "read_all_remote_items", lambda *a, **k: SimpleNamespace(items=())
    )
    preview_id = previews.create_preview(
        session,
        app_settings,
        PreviewRequest(
            collection_id=collection.id,
            target_id=target.id,
            thresholds=ThresholdsIn(max_addition_pct=1, max_removal_pct=0, max_removal_abs=0),
        ),
    )
    preview = previews.get_preview(session, preview_id)
    assert preview["state"] == "BLOCKED"
    assert preview["blocked"]["reason"]


def test_get_preview_missing_and_status_variants(session: Session) -> None:
    with pytest.raises(NotFoundError):
        previews.get_preview(session, uuid.uuid4())
    job = JobExecution(
        task_name=previews.PREVIEW_TASK_NAME,
        queue=previews.PREVIEW_QUEUE,
        status="RUNNING",
        payload={},
    )
    session.add(job)
    session.commit()
    assert previews.get_preview(session, job.id)["state"] == "RUNNING"
    job.status = "FAILED"
    job.result = {"state": "READY"}
    job.error_message = "boom"
    session.commit()
    preview = previews.get_preview(session, job.id)
    assert preview["state"] == "FAILED"
    assert preview["error"] == "boom"
