"""Local multi-criteria and multi-provider collections (no external calls)."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.api.schemas.catalog import CollectionCreateIn
from app.db.models import CollectionSnapshot, SnapshotItem
from app.db.session import get_session_factory
from app.repositories import collections as collections_repo
from app.repositories import media as media_repo
from app.services import acquisition, collection_admin


class _FakeConnector:
    key = "tmdb"

    def fetch_collection_page(self, *_args, **_kwargs):
        raise AssertionError("Una collezione locale non deve chiamare TMDb")


@pytest.fixture()
def session(db) -> Session:
    factory = get_session_factory()
    db_session = factory()
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


def _snapshot(session: Session, collection, payloads: list[dict]) -> CollectionSnapshot:
    snapshot = CollectionSnapshot(
        collection_id=collection.id,
        status="COMPLETE",
        quality="CLEAN",
        is_valid=True,
        items_count=len(payloads),
        resolved_count=len(payloads),
        unresolved_count=0,
        duplicate_count=0,
        error_count=0,
        checksum="checksum",
    )
    session.add(snapshot)
    session.flush()
    for position, payload in enumerate(payloads):
        media = _media(session, int(payload["id"]))
        session.add(
            SnapshotItem(
                snapshot_id=snapshot.id,
                media_id=media.id,
                position=position,
                source_payload=payload,
                date_basis="UNKNOWN",
                resolution_status="RESOLVED",
            )
        )
    collection.last_valid_snapshot_id = snapshot.id
    session.commit()
    return snapshot


def _payload(
    tmdb_id: int,
    *,
    genres: list[int],
    vote_average: float,
    vote_count: int,
    language: str,
    year: int,
) -> dict:
    return {
        "id": tmdb_id,
        "genre_ids": genres,
        "vote_average": vote_average,
        "vote_count": vote_count,
        "original_language": language,
        "release_date": f"{year}-01-01",
        "popularity": 10.0,
    }


def test_custom_filter_unions_providers_and_applies_all_criteria(
    session: Session, seeded, app_settings
) -> None:
    netflix = collections_repo.get_collection_by_slug(session, "netflix-movie")
    prime = collections_repo.get_collection_by_slug(session, "prime-video-movie")
    assert netflix is not None and prime is not None
    _snapshot(
        session,
        netflix,
        [
            _payload(1, genres=[28], vote_average=8.2, vote_count=500, language="en", year=2020),
            _payload(2, genres=[27], vote_average=8.5, vote_count=500, language="en", year=2021),
            _payload(3, genres=[28], vote_average=6.0, vote_count=500, language="en", year=2022),
            _payload(4, genres=[28], vote_average=8.0, vote_count=50, language="en", year=2022),
            _payload(5, genres=[28], vote_average=8.0, vote_count=500, language="it", year=2022),
            _payload(6, genres=[28], vote_average=8.0, vote_count=500, language="en", year=1999),
        ],
    )
    _snapshot(
        session,
        prime,
        [
            # Same media as Netflix: the union must deduplicate it.
            _payload(1, genres=[28], vote_average=8.2, vote_count=500, language="en", year=2020),
            _payload(7, genres=[28], vote_average=8.0, vote_count=500, language="en", year=2022),
        ],
    )

    summary = collection_admin.create_collection(
        session,
        app_settings,
        CollectionCreateIn(
            media_type="MOVIE",
            name="Film Azione IT — combinata",
            slug="film-azione-combinata-test",
            kind="CUSTOM_FILTER",
            source_collection_ids=[netflix.id, prime.id],
            genre_ids=[28],
            exclude_genre_ids=[27],
            min_vote_average=7.0,
            min_vote_count=100,
            year_from=2000,
            year_to=2024,
            original_language="en",
            local_sort_by="vote_average.desc",
        ),
    )
    assert summary.is_local_filter is True
    assert summary.is_multi_provider is True
    assert summary.filters["derivation"] == "LOCAL_FILTER"
    assert len(summary.filters["source_collection_ids"]) == 2

    outcome = acquisition.acquire_collection(
        session, summary.id, _FakeConnector(), actor_type="SYSTEM"
    )
    assert outcome.is_valid is True
    items = session.query(SnapshotItem).filter_by(snapshot_id=outcome.snapshot_id).all()
    assert outcome.items_count == 2
    assert {item.media_id for item in items} == {_media(session, 1).id, _media(session, 7).id}
    assert all(item.source_payload["local_filter"] is True for item in items)


def test_custom_filter_without_sources_is_rejected(session: Session, seeded, app_settings) -> None:
    from app.api.errors import ValidationError

    with pytest.raises(ValidationError) as exc:
        collection_admin.create_collection(
            session,
            app_settings,
            CollectionCreateIn(
                media_type="MOVIE",
                name="Senza sorgenti",
                slug="senza-sorgenti-test",
                kind="CUSTOM_FILTER",
            ),
        )
    assert exc.value.code == "LOCAL_FILTER_SOURCES_MISSING"
