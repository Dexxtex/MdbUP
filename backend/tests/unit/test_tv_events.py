"""TV season/episode events stay attached to the parent show."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AuditLog, CollectionSnapshot, Media, SnapshotItem
from app.db.session import get_session_factory
from app.integrations.tmdb.models import TMDbSeason, TMDbTvDetails
from app.repositories import collections as collections_repo
from app.repositories import media as media_repo
from app.services.tv_events import detect_tv_changes


class _FakeTvClient:
    def __init__(self, seasons: int, episodes: int) -> None:
        self.seasons = seasons
        self.episodes = episodes

    def tv_details(self, tmdb_id: int) -> TMDbTvDetails:
        return TMDbTvDetails(
            tmdb_id=tmdb_id,
            name="Test Show",
            number_of_seasons=self.seasons,
            number_of_episodes=self.episodes,
            seasons=(
                TMDbSeason(season_number=1, episode_count=10),
                TMDbSeason(season_number=2, episode_count=10),
            ),
        )


@pytest.fixture()
def session(db) -> Session:
    factory = get_session_factory()
    db_session = factory()
    try:
        yield db_session
    finally:
        db_session.close()


def test_new_season_and_episode_create_audit_events_without_media_rows(
    session: Session, seeded
) -> None:
    show = media_repo.resolve_media(
        session,
        media_type="SHOW",
        tmdb_id=1399,
        imdb_id=None,
        title="Il Trono di Spade",
        year=2011,
    )
    assert show is not None
    show.metadata_json = {"number_of_seasons": 1, "number_of_episodes": 10}
    collection = collections_repo.get_collection_by_slug(session, "netflix-show")
    assert collection is not None
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
            media_id=show.id,
            position=0,
            date_basis="UNKNOWN",
            resolution_status="RESOLVED",
        )
    )
    collection.last_valid_snapshot_id = snapshot.id
    session.commit()
    media_before = session.query(Media).count()

    outcome = detect_tv_changes(session, _FakeTvClient(2, 20), limit=10)
    assert outcome.checked == 1
    assert outcome.season_events == 1
    assert outcome.episode_events == 1
    assert session.query(Media).count() == media_before
    events = list(
        session.scalars(
            select(AuditLog).where(
                AuditLog.entity_id == str(show.id),
                AuditLog.action.in_(["tv_season_added", "tv_episode_added"]),
            )
        ).all()
    )
    assert {event.action for event in events} == {"tv_season_added", "tv_episode_added"}
    session.refresh(show)
    assert show.metadata_json["number_of_seasons"] == 2
    assert show.metadata_json["number_of_episodes"] == 20

    again = detect_tv_changes(session, _FakeTvClient(2, 20), limit=10)
    assert again.season_events == 0
    assert again.episode_events == 0
    assert session.query(Media).count() == media_before
