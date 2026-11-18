"""A failed JustWatch page never yields a valid snapshot, and UPCOMING stays apart."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.justwatch.connector import JustWatchConnector
from app.db.models import Availability, Collection, CollectionSnapshot, SnapshotItem
from app.db.session import get_session_factory
from app.domain.enums import MediaType, SnapshotQuality, SnapshotStatus
from app.integrations.justwatch.client import (
    JustWatchGraphQLError,
    JustWatchRateLimitError,
)
from app.integrations.justwatch.models import (
    JustWatchOffer,
    JustWatchPage,
    JustWatchTitle,
)
from app.repositories import collections as collections_repo
from app.repositories import providers as providers_repo
from app.repositories import snapshots as snapshots_repo
from app.repositories import sources as sources_repo
from app.services import acquisition


class _RaisingClient:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def popular_titles(self, *args, **kwargs):
        raise self.error

    def new_titles(self, *args, **kwargs):
        raise self.error

    def streaming_charts(self, *args, **kwargs):
        raise self.error

    def close(self) -> None:
        return None


class _TitleClient:
    def __init__(self, title: JustWatchTitle) -> None:
        self.title = title

    def new_titles(self, *args, **kwargs) -> JustWatchPage:
        return JustWatchPage(titles=(self.title,), next_cursor=None, total_items=1)

    def popular_titles(self, *args, **kwargs) -> JustWatchPage:
        return JustWatchPage(titles=(self.title,), next_cursor=None, total_items=1)

    def close(self) -> None:
        return None


@pytest.fixture()
def session(db) -> Session:
    factory = get_session_factory()
    db_session = factory()
    try:
        yield db_session
    finally:
        db_session.close()


def _collection(
    session: Session, *, kind: str = "CATALOG", media_type: str = "MOVIE"
) -> Collection:
    source = sources_repo.get_source_by_key(session, "justwatch")
    netflix = providers_repo.get_provider_by_slug(session, "netflix")
    assert source is not None and netflix is not None
    providers_repo.upsert_mapping(
        session,
        provider_id=netflix.id,
        source_id=source.id,
        country_code="IT",
        external_provider_id="nfx",
        external_name="Netflix",
        is_primary=True,
        is_verified=True,
        metadata={"technical_name": "netflix", "monetization_types": ["FLATRATE"]},
    )
    collection = collections_repo.upsert_collection(
        session,
        slug=f"netflix-{media_type.lower()}-justwatch-test-{kind.lower()}",
        source_id=source.id,
        provider_id=netflix.id,
        country_code="IT",
        media_type=media_type,
        kind=kind,
        origin="AGGREGATOR",
        date_basis="UNKNOWN",
        name="Netflix — JustWatch test",
        description=None,
        source_collection_key=f"test:{kind}:{media_type}",
        source_url=None,
        offer_types=["FLATRATE"],
        filters={
            "packages": ["nfx"],
            "watch_region": "IT",
            "media_type": media_type,
            "offer_types": ["FLATRATE"],
        },
        quality_flags={},
        sort_mode="SOURCE_ORDER",
        is_active=True,
    )
    session.commit()
    return collection


def test_rate_limit_on_the_first_page_is_incomplete_not_complete(session: Session, seeded) -> None:
    collection = _collection(session)
    connector = JustWatchConnector(
        _RaisingClient(JustWatchRateLimitError("JustWatch ha risposto 429")),
        language="it",
    )

    outcome = acquisition.acquire_collection(session, collection.id, connector)

    assert outcome.status is SnapshotStatus.INCOMPLETE
    assert outcome.quality is SnapshotQuality.ANOMALY
    assert outcome.is_valid is False
    assert outcome.error_count == 1
    assert "JustWatchRateLimitError" in outcome.errors[0]["code"]
    snapshot = snapshots_repo.get_snapshot(session, outcome.snapshot_id)
    assert snapshot is not None
    assert snapshot.is_valid is False
    assert "incomplete_pages" in (snapshot.invalid_reason or "")
    session.refresh(collection)
    assert collection.last_valid_snapshot_id is None


def test_schema_drift_is_incomplete_and_never_valid(session: Session, seeded) -> None:
    collection = _collection(session)
    connector = JustWatchConnector(
        _RaisingClient(JustWatchGraphQLError("campo mancante", code="SCHEMA_DRIFT")),
        language="it",
    )

    outcome = acquisition.acquire_collection(session, collection.id, connector)

    assert outcome.status is SnapshotStatus.INCOMPLETE
    assert outcome.quality is SnapshotQuality.ANOMALY
    assert outcome.is_valid is False


def test_upcoming_snapshot_marks_items_and_stays_out_of_availability(
    session: Session, seeded
) -> None:
    collection = _collection(session, kind="UPCOMING")
    title = JustWatchTitle(
        node_id="tm-upcoming",
        media_type=MediaType.MOVIE,
        title="In arrivo",
        year=2027,
        tmdb_id=99001,
        imdb_id=None,
        offers=(JustWatchOffer(monetization_type="FLATRATE", package_short_name="nfx"),),
        raw={"id": "tm-upcoming"},
    )
    connector = JustWatchConnector(_TitleClient(title), language="it")

    outcome = acquisition.acquire_collection(session, collection.id, connector)

    assert outcome.status is SnapshotStatus.COMPLETE
    assert outcome.is_valid is True
    items = list(
        session.scalars(
            select(SnapshotItem).where(SnapshotItem.snapshot_id == outcome.snapshot_id)
        ).all()
    )
    assert [item.availability_status for item in items] == ["UPCOMING"]
    # Upcoming titles are not available yet: no availability observation.
    assert session.scalars(select(Availability)).all() == []


def test_catalog_snapshot_marks_items_current(session: Session, seeded) -> None:
    collection = _collection(session)
    title = JustWatchTitle(
        node_id="tm10",
        media_type=MediaType.MOVIE,
        title="Matrix",
        year=1999,
        tmdb_id=603,
        imdb_id=None,
        offers=(JustWatchOffer(monetization_type="FLATRATE", package_short_name="nfx"),),
        raw={"id": "tm10"},
    )
    connector = JustWatchConnector(_TitleClient(title), language="it")

    outcome = acquisition.acquire_collection(session, collection.id, connector)

    assert outcome.is_valid is True
    items = list(
        session.scalars(
            select(SnapshotItem).where(SnapshotItem.snapshot_id == outcome.snapshot_id)
        ).all()
    )
    assert [item.availability_status for item in items] == ["CURRENT"]
    assert len(session.scalars(select(Availability)).all()) == 1


def test_failed_snapshot_never_authorizes_mirror(session: Session, seeded) -> None:
    collection = _collection(session)
    connector = JustWatchConnector(
        _RaisingClient(JustWatchRateLimitError("JustWatch ha risposto 429")),
        language="it",
    )
    acquisition.acquire_collection(session, collection.id, connector)

    snapshot = session.scalar(
        select(CollectionSnapshot).where(CollectionSnapshot.collection_id == collection.id)
    )
    assert snapshot is not None
    assert snapshot.status == SnapshotStatus.INCOMPLETE.value
    assert snapshot.quality == SnapshotQuality.ANOMALY.value
    assert snapshot.is_valid is False
    session.refresh(collection)
    assert collection.last_valid_snapshot_id is None


def test_show_novelty_collection_stays_invalid_when_only_movies_arrive(
    session: Session, seeded
) -> None:
    """``newTitles`` answers only movies: a SHOW novelty collection is empty."""
    collection = _collection(session, kind="RECENTLY_ADDED", media_type="SHOW")
    movie = JustWatchTitle(
        node_id="tm-movie",
        media_type=MediaType.MOVIE,
        title="Film",
        year=2024,
        tmdb_id=97001,
        imdb_id=None,
        offers=(JustWatchOffer(monetization_type="FLATRATE", package_short_name="nfx"),),
        raw={"id": "tm-movie"},
    )
    connector = JustWatchConnector(_TitleClient(movie), language="it")

    outcome = acquisition.acquire_collection(session, collection.id, connector)

    assert outcome.items_count == 0
    assert outcome.quality is SnapshotQuality.ANOMALY
    assert outcome.is_valid is False
    assert outcome.invalid_reason == "empty_catalog"
    session.refresh(collection)
    assert collection.last_valid_snapshot_id is None
