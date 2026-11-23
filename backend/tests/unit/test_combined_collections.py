"""Local JustWatch + TMDb combined collections: union, intersection, no external calls."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.api.errors import ValidationError
from app.api.schemas.catalog import CollectionCreateIn
from app.db.models import CollectionSnapshot, Media, SnapshotItem
from app.db.session import get_session_factory
from app.repositories import collections as collections_repo
from app.repositories import media as media_repo
from app.services import acquisition, collection_admin


class _FakeConnector:
    key = "tmdb"

    def fetch_collection_page(self, *_args, **_kwargs):
        raise AssertionError("Una collezione combinata non deve chiamare fonti esterne")

    def close(self) -> None:
        return None


@pytest.fixture()
def session(db, seeded) -> Session:
    db_session = get_session_factory()()
    try:
        yield db_session
    finally:
        db_session.close()


def _media(session: Session, tmdb_id: int):
    media = media_repo.resolve_media(
        session,
        media_type="MOVIE",
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
    payloads: dict[int, dict] | None = None,
) -> CollectionSnapshot:
    snapshot = CollectionSnapshot(
        collection_id=collection.id,
        status="COMPLETE",
        quality="CLEAN",
        is_valid=True,
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
                source_payload=(payloads or {}).get(media.tmdb_id, {}),
                date_basis="UNKNOWN",
                resolution_status="RESOLVED",
            )
        )
    collection.last_valid_snapshot_id = snapshot.id
    session.commit()
    return snapshot


def _sources(session: Session):
    netflix = collections_repo.get_collection_by_slug(session, "netflix-movie")
    prime = collections_repo.get_collection_by_slug(session, "prime-video-movie")
    assert netflix is not None and prime is not None
    return netflix, prime


def _create_combined(
    session: Session,
    app_settings,
    *,
    slug: str,
    sources,
    combine_mode: str = "UNION",
    **kwargs,
):
    return collection_admin.create_collection(
        session,
        app_settings,
        CollectionCreateIn(
            media_type="MOVIE",
            name="Combinata test",
            slug=slug,
            kind="CUSTOM_FILTER",
            source_key="combined",
            source_collection_ids=[source.id for source in sources],
            combine_mode=combine_mode,
            **kwargs,
        ),
    )


def test_combined_union_deduplicates_media_and_never_creates_media(
    session: Session, app_settings
) -> None:
    netflix, prime = _sources(session)
    _snapshot(session, netflix, [_media(session, 1), _media(session, 2)])
    _snapshot(session, prime, [_media(session, 2), _media(session, 3)])
    media_count = session.query(Media).count()

    summary = _create_combined(
        session, app_settings, slug="combined-union-test", sources=[netflix, prime]
    )
    assert summary.source_key == "combined"
    assert summary.source_label == "Combinata locale (JustWatch + TMDb)"
    assert summary.filters["derivation"] == "COMBINED_LOCAL"
    assert summary.filters["combine_mode"] == "UNION"
    assert len(summary.filters["source_collection_ids"]) == 2

    outcome = acquisition.acquire_collection(
        session, summary.id, _FakeConnector(), actor_type="SYSTEM"
    )
    assert outcome.is_valid is True
    items = session.query(SnapshotItem).filter_by(snapshot_id=outcome.snapshot_id).all()
    assert outcome.items_count == 3
    assert {item.media_id for item in items} == {
        _media(session, 1).id,
        _media(session, 2).id,
        _media(session, 3).id,
    }
    assert all(item.source_payload["combined_local"] is True for item in items)
    assert all(item.source_payload["combine_mode"] == "UNION" for item in items)
    assert session.query(Media).count() == media_count


def test_combined_intersection_keeps_only_common_media(session: Session, app_settings) -> None:
    netflix, prime = _sources(session)
    _snapshot(session, netflix, [_media(session, 1), _media(session, 2), _media(session, 3)])
    _snapshot(session, prime, [_media(session, 2), _media(session, 3), _media(session, 4)])
    summary = _create_combined(
        session,
        app_settings,
        slug="combined-intersection-test",
        sources=[netflix, prime],
        combine_mode="INTERSECTION",
    )

    outcome = acquisition.acquire_collection(
        session, summary.id, _FakeConnector(), actor_type="SYSTEM"
    )
    items = session.query(SnapshotItem).filter_by(snapshot_id=outcome.snapshot_id).all()
    assert outcome.items_count == 2
    assert {item.media_id for item in items} == {_media(session, 2).id, _media(session, 3).id}


def test_combined_applies_local_filters(session: Session, app_settings) -> None:
    netflix, prime = _sources(session)
    _snapshot(
        session,
        netflix,
        [_media(session, 1), _media(session, 2)],
        payloads={
            1: {"id": 1, "genre_ids": [28], "vote_average": 8.0, "vote_count": 500},
            2: {"id": 2, "genre_ids": [27], "vote_average": 9.0, "vote_count": 500},
        },
    )
    _snapshot(
        session,
        prime,
        [_media(session, 3)],
        payloads={3: {"id": 3, "genre_ids": [28], "vote_average": 6.0, "vote_count": 500}},
    )
    summary = _create_combined(
        session,
        app_settings,
        slug="combined-filters-test",
        sources=[netflix, prime],
        genre_ids=[28],
        min_vote_average=7.0,
    )

    outcome = acquisition.acquire_collection(
        session, summary.id, _FakeConnector(), actor_type="SYSTEM"
    )
    items = session.query(SnapshotItem).filter_by(snapshot_id=outcome.snapshot_id).all()
    assert {item.media_id for item in items} == {_media(session, 1).id}


def test_combined_requires_two_sources_with_valid_snapshots(session: Session, app_settings) -> None:
    netflix, prime = _sources(session)
    _snapshot(session, netflix, [_media(session, 1)])

    with pytest.raises(ValidationError) as too_few:
        _create_combined(session, app_settings, slug="combined-one-source", sources=[netflix])
    assert too_few.value.code == "COMBINED_LOCAL_SOURCES_MIN"

    with pytest.raises(ValidationError) as no_snapshot:
        _create_combined(
            session, app_settings, slug="combined-missing-snapshot", sources=[netflix, prime]
        )
    assert no_snapshot.value.code == "COMBINED_LOCAL_SOURCE_INVALID"
