"""Catalog change feed: baseline, ADDED/REMOVED, invalid snapshots and counters."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.db.models import CollectionSnapshot, EpisodeEvent, SnapshotItem
from app.db.session import get_session_factory
from app.repositories import collections as collections_repo
from app.repositories import media as media_repo
from app.services import catalog_changes


@pytest.fixture()
def session(db, seeded) -> Session:
    db_session = get_session_factory()()
    try:
        yield db_session
    finally:
        db_session.close()


def _media(session: Session, tmdb_id: int, media_type: str = "MOVIE"):
    media = media_repo.resolve_media(
        session,
        media_type=media_type,
        tmdb_id=tmdb_id,
        imdb_id=None,
        title=f"Media {tmdb_id}",
        year=2020,
    )
    assert media is not None
    return media


def _snapshot(
    session: Session,
    collection,
    media_list,
    *,
    started_at: datetime,
    finished_at: datetime | None = None,
    status: str = "COMPLETE",
    quality: str = "CLEAN",
    is_valid: bool = True,
) -> CollectionSnapshot:
    snapshot = CollectionSnapshot(
        collection_id=collection.id,
        status=status,
        quality=quality,
        is_valid=is_valid,
        started_at=started_at,
        finished_at=finished_at or started_at,
        items_count=len(media_list),
        resolved_count=len(media_list),
        unresolved_count=0,
        duplicate_count=0,
        error_count=0,
        checksum="checksum",
    )
    session.add(snapshot)
    session.flush()
    for position, media in enumerate(media_list):
        session.add(
            SnapshotItem(
                snapshot_id=snapshot.id,
                media_id=media.id,
                position=position,
                source_payload={},
                date_basis="UNKNOWN",
                resolution_status="RESOLVED",
            )
        )
    if is_valid:
        collection.last_valid_snapshot_id = snapshot.id
    session.commit()
    return snapshot


def _clone_collection(session: Session, source, slug: str):
    return collections_repo.upsert_collection(
        session,
        slug=slug,
        source_id=source.source_id,
        provider_id=source.provider_id,
        country_code=source.country_code,
        media_type=source.media_type,
        kind=source.kind,
        origin=source.origin,
        date_basis=source.date_basis,
        name=f"{source.name} alt",
        description="Test",
        source_collection_key=f"custom:{slug}",
        offer_types=["FLATRATE"],
        filters={},
        quality_flags={},
        sort_mode="POPULARITY",
        is_active=True,
    )


def test_first_valid_snapshot_is_the_baseline(session: Session) -> None:
    collection = collections_repo.get_collection_by_slug(session, "netflix-movie")
    assert collection is not None
    now = datetime(2024, 1, 15, 12, 0, tzinfo=UTC)
    _snapshot(
        session,
        collection,
        [_media(session, 1), _media(session, 2)],
        started_at=now - timedelta(hours=2),
    )

    page = catalog_changes.list_catalog_changes(session, window="30d", now=now)
    assert page.items == []
    assert page.total == 0


def test_added_and_removed_between_two_valid_snapshots(session: Session) -> None:
    collection = collections_repo.get_collection_by_slug(session, "netflix-movie")
    assert collection is not None
    now = datetime(2024, 1, 15, 12, 0, tzinfo=UTC)
    _snapshot(
        session,
        collection,
        [_media(session, 1), _media(session, 2)],
        started_at=now - timedelta(days=2),
    )
    current = _snapshot(
        session,
        collection,
        [_media(session, 2), _media(session, 3)],
        started_at=now - timedelta(hours=1),
        finished_at=now,
    )

    page = catalog_changes.list_catalog_changes(session, window="24h", now=now)
    assert page.total == 2
    events = {event.media_id: event for event in page.items}
    assert events[_media(session, 3).id].direction == "ADDED"
    assert events[_media(session, 1).id].direction == "REMOVED"
    added = events[_media(session, 3).id]
    assert added.current_snapshot_id == current.id
    assert added.previous_snapshot_id is not None
    assert added.detected_at == now
    assert added.detected_at_rome.tzinfo is not None
    assert added.source_key == "tmdb"
    assert added.provider_slug == "netflix"


def test_incomplete_snapshot_is_ignored_between_valid_snapshots(session: Session) -> None:
    collection = collections_repo.get_collection_by_slug(session, "netflix-movie")
    assert collection is not None
    now = datetime(2024, 1, 15, 12, 0, tzinfo=UTC)
    baseline = _snapshot(
        session, collection, [_media(session, 1)], started_at=now - timedelta(days=3)
    )
    invalid = _snapshot(
        session,
        collection,
        [_media(session, 2)],
        started_at=now - timedelta(days=2),
        status="INCOMPLETE",
        quality="ANOMALY",
        is_valid=False,
    )
    current = _snapshot(
        session,
        collection,
        [_media(session, 1), _media(session, 3)],
        started_at=now - timedelta(hours=1),
        finished_at=now,
    )

    page = catalog_changes.list_catalog_changes(session, window="7d", now=now)
    assert page.total == 1
    [event] = page.items
    assert event.direction == "ADDED"
    assert event.media_id == _media(session, 3).id
    assert event.previous_snapshot_id == baseline.id
    assert event.current_snapshot_id == current.id
    assert event.previous_snapshot_id != invalid.id


def test_events_are_deduplicated_across_collections_of_the_same_provider(
    session: Session,
) -> None:
    collection = collections_repo.get_collection_by_slug(session, "netflix-movie")
    assert collection is not None
    clone = _clone_collection(session, collection, "netflix-movie-alt-test")
    now = datetime(2024, 1, 15, 12, 0, tzinfo=UTC)
    for target in (collection, clone):
        _snapshot(session, target, [_media(session, 1)], started_at=now - timedelta(days=2))
        _snapshot(
            session,
            target,
            [_media(session, 1), _media(session, 2)],
            started_at=now - timedelta(hours=1),
            finished_at=now,
        )

    page = catalog_changes.list_catalog_changes(session, window="24h", now=now)
    assert page.total == 1
    assert page.items[0].media_id == _media(session, 2).id


def test_show_events_carry_episode_event_details(session: Session) -> None:
    collection = collections_repo.get_collection_by_slug(session, "netflix-show")
    assert collection is not None
    show_one = _media(session, 101, "SHOW")
    show_two = _media(session, 102, "SHOW")
    now = datetime(2024, 1, 15, 12, 0, tzinfo=UTC)
    _snapshot(session, collection, [show_one], started_at=now - timedelta(days=2))
    current = _snapshot(
        session,
        collection,
        [show_one, show_two],
        started_at=now - timedelta(hours=1),
        finished_at=now,
    )
    session.add(
        EpisodeEvent(
            show_media_id=show_two.id,
            media_type="SHOW",
            provider_id=collection.provider_id,
            country_code="IT",
            source_id=collection.source_id,
            snapshot_id=current.id,
            event_type="EPISODE_ADDED",
            season_number=2,
            episode_number=5,
            occurred_at=now,
        )
    )
    session.commit()

    page = catalog_changes.list_catalog_changes(session, window="24h", now=now)
    [event] = page.items
    assert event.media_id == show_two.id
    assert event.media_type == "SHOW"
    assert event.season_number == 2
    assert event.episode_number == 5
    assert event.episode_event_type == "EPISODE_ADDED"


def test_filters_and_pagination(session: Session) -> None:
    netflix = collections_repo.get_collection_by_slug(session, "netflix-movie")
    prime = collections_repo.get_collection_by_slug(session, "prime-video-movie")
    assert netflix is not None and prime is not None
    now = datetime(2024, 1, 15, 12, 0, tzinfo=UTC)
    for target, baseline_id, added_id in (
        (netflix, 1, 2),
        (prime, 3, 4),
    ):
        _snapshot(
            session, target, [_media(session, baseline_id)], started_at=now - timedelta(days=2)
        )
        _snapshot(
            session,
            target,
            [_media(session, baseline_id), _media(session, added_id)],
            started_at=now - timedelta(hours=1),
            finished_at=now,
        )

    by_provider = catalog_changes.list_catalog_changes(
        session, window="24h", provider_id=netflix.provider_id, now=now
    )
    assert [event.media_id for event in by_provider.items] == [_media(session, 2).id]

    by_search = catalog_changes.list_catalog_changes(
        session, window="24h", search="Media 4", now=now
    )
    assert [event.media_id for event in by_search.items] == [_media(session, 4).id]

    by_direction = catalog_changes.list_catalog_changes(
        session, window="24h", direction="REMOVED", now=now
    )
    assert by_direction.total == 0

    first_page = catalog_changes.list_catalog_changes(
        session, window="24h", page=1, page_size=1, now=now
    )
    second_page = catalog_changes.list_catalog_changes(
        session, window="24h", page=2, page_size=1, now=now
    )
    assert first_page.total == 2
    assert len(first_page.items) == 1
    assert len(second_page.items) == 1
    assert first_page.items[0].media_id != second_page.items[0].media_id


def test_counters_use_the_europe_rome_day_and_the_requested_window(session: Session) -> None:
    netflix = collections_repo.get_collection_by_slug(session, "netflix-movie")
    prime = collections_repo.get_collection_by_slug(session, "prime-video-movie")
    assert netflix is not None and prime is not None
    now = datetime(2024, 1, 15, 23, 30, tzinfo=UTC)
    # 23:15 UTC is 00:15 in Rome (CET): today, 15 January in UTC is yesterday.
    _snapshot(session, netflix, [_media(session, 1)], started_at=now - timedelta(days=2))
    _snapshot(
        session,
        netflix,
        [_media(session, 1), _media(session, 2)],
        started_at=now - timedelta(hours=1),
        finished_at=datetime(2024, 1, 15, 23, 15, tzinfo=UTC),
    )
    # 22:45 UTC is 23:45 in Rome: still the previous Rome day.
    _snapshot(session, prime, [_media(session, 3)], started_at=now - timedelta(days=2))
    _snapshot(
        session,
        prime,
        [_media(session, 3), _media(session, 4)],
        started_at=now - timedelta(hours=2),
        finished_at=datetime(2024, 1, 15, 22, 45, tzinfo=UTC),
    )

    page = catalog_changes.list_catalog_changes(session, window="24h", now=now)
    assert page.counters.added_window == 2
    assert page.counters.removed_window == 0
    assert page.counters.added_today == 1
    assert page.counters.removed_today == 0
    rome_days = {event.detected_at_rome.date() for event in page.items}
    assert rome_days == {datetime(2024, 1, 15).date(), datetime(2024, 1, 16).date()}
