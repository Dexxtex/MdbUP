"""JustWatch TV timeline: baseline on first sight, episode events afterwards."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Collection, CollectionSnapshot, EpisodeEvent, Media, SnapshotItem
from app.db.session import get_session_factory
from app.integrations.justwatch.models import JustWatchEpisode, JustWatchSeason
from app.repositories import collections as collections_repo
from app.repositories import media as media_repo
from app.services import justwatch_tv_events


class _FakeJustWatchConnector:
    def __init__(self, seasons: dict[str, list[str]]) -> None:
        self.seasons_map = seasons
        self.season_calls: list[str] = []

    def list_seasons(self, show_id: str, country_code: str = "IT"):
        return [
            JustWatchSeason(node_id=season_id, title=f"Stagione {index + 1}")
            for index, season_id in enumerate(self.seasons_map)
        ]

    def list_episodes(self, season_id: str, country_code: str = "IT"):
        self.season_calls.append(season_id)
        return [
            JustWatchEpisode(
                node_id=episode_id,
                title=f"Episodio {episode_id}",
                season_number=1,
                episode_number=position + 1,
            )
            for position, episode_id in enumerate(self.seasons_map.get(season_id, []))
        ]


@pytest.fixture()
def session(db) -> Session:
    factory = get_session_factory()
    db_session = factory()
    try:
        yield db_session
    finally:
        db_session.close()


def _justwatch_show_collection(db_session: Session) -> tuple[Collection, Media]:
    show = media_repo.resolve_media(
        db_session,
        media_type="SHOW",
        tmdb_id=6001,
        imdb_id=None,
        title="Serie JustWatch",
        year=2020,
    )
    assert show is not None
    source = None
    from app.repositories import sources as sources_repo

    source = sources_repo.get_source_by_key(db_session, "justwatch")
    assert source is not None
    netflix = collections_repo.get_collection_by_slug(db_session, "netflix-show")
    assert netflix is not None
    collection = collections_repo.upsert_collection(
        db_session,
        slug="netflix-show-justwatch",
        source_id=source.id,
        provider_id=netflix.provider_id,
        country_code="IT",
        media_type="SHOW",
        kind="CATALOG",
        origin="AGGREGATOR",
        date_basis="UNKNOWN",
        name="Netflix — Serie — Catalogo JustWatch",
        description=None,
        source_collection_key="nfx:SHOW",
        source_url=None,
        offer_types=["FLATRATE"],
        filters={"packages": ["nfx"], "watch_region": "IT", "media_type": "SHOW"},
        quality_flags={},
        sort_mode="SOURCE_ORDER",
        is_active=True,
    )
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
    db_session.add(snapshot)
    db_session.flush()
    db_session.add(
        SnapshotItem(
            snapshot_id=snapshot.id,
            media_id=show.id,
            position=0,
            source_payload={"id": "ts4"},
            date_basis="UNKNOWN",
            resolution_status="RESOLVED",
        )
    )
    collection.last_valid_snapshot_id = snapshot.id
    db_session.commit()
    return collection, show


def test_first_observation_stores_the_baseline_without_events(session: Session, seeded) -> None:
    collection, show = _justwatch_show_collection(session)
    connector = _FakeJustWatchConnector({"tss26": ["tse412", "tse413"]})

    outcome = justwatch_tv_events.observe_tv_events(
        session, collection=collection, connector=connector
    )

    assert outcome.shows == 1
    assert outcome.baselines == 1
    assert outcome.season_events == 0
    assert outcome.episode_events == 0
    assert session.scalars(select(EpisodeEvent)).all() == []
    session.refresh(show)
    baseline = show.metadata_json["justwatch_tv"]
    assert baseline["seasons"]["tss26"]["episodes"] == ["tse412", "tse413"]
    assert baseline["baseline_at"]


def test_new_episode_and_season_produce_events_on_the_parent_show(session: Session, seeded) -> None:
    collection, show = _justwatch_show_collection(session)
    justwatch_tv_events.observe_tv_events(
        session,
        collection=collection,
        connector=_FakeJustWatchConnector({"tss26": ["tse412"]}),
    )
    media_before = session.query(Media).count()

    outcome = justwatch_tv_events.observe_tv_events(
        session,
        collection=collection,
        connector=_FakeJustWatchConnector({"tss26": ["tse412", "tse413"], "tss27": ["tse500"]}),
    )

    assert outcome.season_events == 1
    assert outcome.episode_events == 2
    events = list(session.scalars(select(EpisodeEvent)).all())
    assert {event.event_type for event in events} == {"SEASON_ADDED", "EPISODE_ADDED"}
    assert {event.show_media_id for event in events} == {show.id}
    assert session.query(Media).count() == media_before  # no episode media rows
    episode_event = next(event for event in events if event.event_type == "EPISODE_ADDED")
    assert episode_event.episode_number == 2
    assert episode_event.season_number == 1

    # Idempotent: the same observation adds nothing.
    again = justwatch_tv_events.observe_tv_events(
        session,
        collection=collection,
        connector=_FakeJustWatchConnector({"tss26": ["tse412", "tse413"], "tss27": ["tse500"]}),
    )
    assert again.season_events == 0
    assert again.episode_events == 0
    assert len(session.scalars(select(EpisodeEvent)).all()) == len(events)


def test_tv_failures_are_warnings_and_never_break_the_catalog(session: Session, seeded) -> None:
    collection, _show = _justwatch_show_collection(session)

    class BrokenConnector:
        def list_seasons(self, show_id: str, country_code: str = "IT"):
            raise RuntimeError("JustWatch ha risposto 429")

        def list_episodes(self, season_id: str, country_code: str = "IT"):
            raise RuntimeError("JustWatch ha risposto 429")

    outcome = justwatch_tv_events.observe_tv_events(
        session, collection=collection, connector=BrokenConnector()
    )

    assert outcome.errors == 1
    assert outcome.warnings
    # The warning carries the exception type, never the sensitive message.
    assert "JustWatch ha risposto" not in " ".join(outcome.warnings)
    assert "RuntimeError" in " ".join(outcome.warnings)
    assert session.scalars(select(EpisodeEvent)).all() == []


def test_episode_budget_caps_the_observation(session: Session, seeded) -> None:
    collection, _show = _justwatch_show_collection(session)
    connector = _FakeJustWatchConnector({"tss26": [f"tse{index}" for index in range(10)]})

    outcome = justwatch_tv_events.observe_tv_events(
        session, collection=collection, connector=connector, max_episodes=3
    )

    assert outcome.shows == 1
    assert connector.season_calls == ["tss26"]
    session.refresh(_show)
    assert len(_show.metadata_json["justwatch_tv"]["seasons"]["tss26"]["episodes"]) == 3
