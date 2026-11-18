"""Acquisition service: valid, incomplete, empty, duplicate and unresolved runs."""

from __future__ import annotations

import uuid
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field

import pytest
from sqlalchemy.orm import Session

from app.api.errors import ConflictError
from app.connectors.base import (
    ConnectorCapabilities,
    HealthStatus,
    NormalizedItem,
    Page,
    RawItem,
    SourceCollection,
    SourceProvider,
)
from app.domain.enums import DateBasis, MediaType, SnapshotQuality, SnapshotStatus
from app.repositories import collections as collections_repo
from app.repositories import snapshots as snapshots_repo
from app.services import acquisition
from app.services import snapshots as snapshots_service


@dataclass
class FakeConnector:
    """In-memory connector with scripted pages."""

    pages: list[Page]
    fail_on_page: int | None = None
    key: str = "fake"
    capabilities: ConnectorCapabilities = field(
        default_factory=lambda: ConnectorCapabilities(max_page_size=2)
    )

    def healthcheck(self) -> HealthStatus:
        return HealthStatus(ok=True)

    def list_providers(self, country_code: str) -> Sequence[SourceProvider]:
        return ()

    def list_collections(self, country_code: str) -> Sequence[SourceCollection]:
        return ()

    def fetch_collection_page(
        self, collection: SourceCollection, cursor: str | None, page_size: int
    ) -> Page:
        index = int(cursor) if cursor else 1
        if self.fail_on_page == index:
            raise RuntimeError("boom di rete")
        return self.pages[index - 1]

    def normalize_item(self, raw: RawItem) -> NormalizedItem:
        return NormalizedItem(
            media_type=raw.media_type,
            tmdb_id=raw.tmdb_id,
            imdb_id=raw.imdb_id,
            title=raw.title,
            year=raw.year,
            offer_types=raw.offer_types,
            source_date_created=None,
            date_basis=DateBasis.UNKNOWN,
            raw=dict(raw.source_payload),
        )

    def close(self) -> None:
        return None


def _raw(
    tmdb_id: int | None,
    media_type: MediaType = MediaType.MOVIE,
    title: str = "Titolo",
    imdb_id: str | None = None,
) -> RawItem:
    return RawItem(
        source_item_id=str(tmdb_id or imdb_id or "unknown"),
        media_type=media_type,
        title=title,
        year=2020,
        tmdb_id=tmdb_id,
        imdb_id=imdb_id,
        offer_types=frozenset({"FLATRATE"}),
        source_payload={"id": tmdb_id},
    )


def _page(items: list[RawItem], *, next_cursor: str | None, total_pages: int) -> Page:
    return Page(items=items, next_cursor=next_cursor, total_pages=total_pages)


@pytest.fixture()
def session(db, seeded) -> Iterator[Session]:
    from app.db.session import get_session_factory

    db_session = get_session_factory()()
    yield db_session
    db_session.close()


def _collection(session: Session, slug: str = "netflix-movie"):
    collection = collections_repo.get_collection_by_slug(session, slug)
    assert collection is not None
    return collection


def test_valid_snapshot_updates_last_valid_pointer(session: Session) -> None:
    collection = _collection(session)
    connector = FakeConnector(
        pages=[
            _page([_raw(101), _raw(102)], next_cursor="2", total_pages=2),
            _page([_raw(103)], next_cursor=None, total_pages=2),
        ]
    )
    outcome = acquisition.acquire_collection(session, collection.id, connector)

    assert outcome.status is SnapshotStatus.COMPLETE
    assert outcome.quality is SnapshotQuality.CLEAN
    assert outcome.is_valid is True
    assert outcome.items_count == 3
    assert outcome.resolved_count == 3
    assert outcome.unresolved_count == 0
    assert outcome.pages_fetched == 2
    assert outcome.pages_expected == 2
    assert outcome.checksum is not None and len(outcome.checksum) == 64

    session.refresh(collection)
    assert collection.last_valid_snapshot_id == outcome.snapshot_id
    snapshot = snapshots_repo.get_snapshot(session, outcome.snapshot_id)
    assert snapshot is not None
    assert snapshot.status == SnapshotStatus.COMPLETE.value
    assert snapshot.is_valid is True
    items, total = snapshots_service.list_snapshot_items(session, snapshot.id)
    assert total == 3
    assert len(items) == 3


def test_incomplete_snapshot_does_not_move_pointer(session: Session) -> None:
    collection = _collection(session)
    connector = FakeConnector(
        pages=[
            _page([_raw(201)], next_cursor="2", total_pages=2),
            _page([_raw(202)], next_cursor=None, total_pages=2),
        ],
        fail_on_page=2,
    )
    outcome = acquisition.acquire_collection(session, collection.id, connector)

    assert outcome.status is SnapshotStatus.INCOMPLETE
    assert outcome.is_valid is False
    assert outcome.pages_fetched == 1
    assert outcome.pages_expected == 2
    assert outcome.error_count == 1
    assert outcome.invalid_reason is not None
    assert "incomplete_pages" in outcome.invalid_reason
    session.refresh(collection)
    assert collection.last_valid_snapshot_id is None


def test_failed_first_page_marks_snapshot_failed(session: Session) -> None:
    collection = _collection(session)
    connector = FakeConnector(
        pages=[_page([_raw(301)], next_cursor=None, total_pages=1)], fail_on_page=1
    )
    outcome = acquisition.acquire_collection(session, collection.id, connector)

    assert outcome.status is SnapshotStatus.FAILED
    assert outcome.quality is SnapshotQuality.ANOMALY
    assert outcome.is_valid is False
    assert outcome.items_count == 0


def test_empty_catalog_is_complete_but_anomalous(session: Session) -> None:
    collection = _collection(session)
    connector = FakeConnector(pages=[_page([], next_cursor=None, total_pages=1)])
    outcome = acquisition.acquire_collection(session, collection.id, connector)

    assert outcome.status is SnapshotStatus.COMPLETE
    assert outcome.quality is SnapshotQuality.ANOMALY
    assert outcome.is_valid is False
    assert outcome.items_count == 0
    assert outcome.invalid_reason is not None
    assert "empty_catalog" in outcome.invalid_reason


def test_duplicates_across_media_types_are_kept_and_counted(session: Session) -> None:
    collection = _collection(session)
    connector = FakeConnector(
        pages=[
            _page(
                [
                    _raw(1399, MediaType.MOVIE, "Film"),
                    _raw(1399, MediaType.SHOW, "Serie"),
                    _raw(1399, MediaType.MOVIE, "Film duplicato"),
                ],
                next_cursor=None,
                total_pages=1,
            )
        ]
    )
    outcome = acquisition.acquire_collection(session, collection.id, connector)

    assert outcome.items_count == 2
    assert outcome.duplicate_count == 1
    assert outcome.quality is SnapshotQuality.WARNINGS
    assert outcome.is_valid is False
    assert outcome.invalid_reason is not None
    assert "duplicates:1" in outcome.invalid_reason


def test_unresolved_item_is_stored_without_media(session: Session) -> None:
    collection = _collection(session)
    connector = FakeConnector(
        pages=[
            _page(
                [_raw(501), _raw(None, MediaType.MOVIE, "Senza ID")],
                next_cursor=None,
                total_pages=1,
            )
        ]
    )
    outcome = acquisition.acquire_collection(session, collection.id, connector)

    assert outcome.items_count == 2
    assert outcome.resolved_count == 1
    assert outcome.unresolved_count == 1
    assert outcome.is_valid is False
    assert outcome.quality is SnapshotQuality.WARNINGS
    items, _ = snapshots_service.list_snapshot_items(session, outcome.snapshot_id)
    unresolved = [item for item in items if item.resolution_status == "UNRESOLVED"]
    assert len(unresolved) == 1
    assert unresolved[0].media_id is None


def test_two_keys_resolving_to_same_media_are_deduplicated(session: Session) -> None:
    collection = _collection(session)
    with_both = RawItem(
        source_item_id="603",
        media_type=MediaType.MOVIE,
        title="Matrix",
        year=1999,
        tmdb_id=603,
        imdb_id="tt0133093",
        offer_types=frozenset({"FLATRATE"}),
        source_payload={"id": 603},
    )
    imdb_only = RawItem(
        source_item_id="tt0133093",
        media_type=MediaType.MOVIE,
        title="Matrix",
        year=1999,
        imdb_id="tt0133093",
        offer_types=frozenset({"FLATRATE"}),
        source_payload={"id": 603},
    )
    connector = FakeConnector(
        pages=[_page([with_both, imdb_only], next_cursor=None, total_pages=1)]
    )
    outcome = acquisition.acquire_collection(session, collection.id, connector)

    assert outcome.items_count == 1
    assert outcome.duplicate_count == 1
    assert outcome.is_valid is False
    items, _ = snapshots_service.list_snapshot_items(session, outcome.snapshot_id)
    assert len(items) == 1
    assert items[0].media_id is not None


def test_second_acquisition_while_running_is_rejected(session: Session) -> None:
    collection = _collection(session)
    snapshots_repo.create_running_snapshot(session, collection.id)
    session.commit()
    connector = FakeConnector(pages=[_page([], next_cursor=None, total_pages=1)])
    with pytest.raises(ConflictError):
        acquisition.acquire_collection(session, collection.id, connector)


def test_missing_collection_raises_not_found(session: Session) -> None:
    from app.api.errors import NotFoundError

    connector = FakeConnector(pages=[_page([], next_cursor=None, total_pages=1)])
    with pytest.raises(NotFoundError):
        acquisition.acquire_collection(session, uuid.uuid4(), connector)


def test_identical_snapshot_reuses_items_and_preserves_catalog_changes(session: Session) -> None:
    """An unchanged catalog adds a verification, not another 5k item rows."""
    from sqlalchemy import func, select

    from app.db.models import CollectionSnapshot, SnapshotItem
    from app.services import catalog_changes

    collection = _collection(session)
    connector = FakeConnector(
        pages=[
            _page([_raw(101), _raw(102)], next_cursor="2", total_pages=2),
            _page([_raw(103)], next_cursor=None, total_pages=2),
        ]
    )
    first = acquisition.acquire_collection(session, collection.id, connector)
    second = acquisition.acquire_collection(session, collection.id, connector)
    session.flush()

    first_snapshot = snapshots_repo.get_snapshot(session, first.snapshot_id)
    second_snapshot = snapshots_repo.get_snapshot(session, second.snapshot_id)
    assert first_snapshot is not None and second_snapshot is not None
    assert second_snapshot.items_from_snapshot_id == first_snapshot.id
    assert second_snapshot.last_verified_at is not None
    assert session.scalar(select(func.count()).select_from(SnapshotItem)) == 3
    views, total = snapshots_service.list_snapshot_items(session, second_snapshot.id)
    assert total == 3 and len(views) == 3

    # A duplicate does not create ADDED/REMOVED events on its own.
    changes = catalog_changes.list_catalog_changes(session, window="30d")
    assert changes.total == 0

    changed_connector = FakeConnector(
        pages=[
            _page([_raw(101), _raw(102)], next_cursor="2", total_pages=2),
            _page([_raw(104)], next_cursor=None, total_pages=2),
        ]
    )
    third = acquisition.acquire_collection(session, collection.id, changed_connector)
    session.flush()
    third_snapshot = snapshots_repo.get_snapshot(session, third.snapshot_id)
    assert third_snapshot is not None
    assert third_snapshot.items_from_snapshot_id is None
    changes = catalog_changes.list_catalog_changes(session, window="30d")
    assert {(event.direction, event.title) for event in changes.items} == {
        ("ADDED", "Titolo"),
        ("REMOVED", "Titolo"),
    }
    assert session.scalar(select(func.count()).select_from(CollectionSnapshot)) == 3
