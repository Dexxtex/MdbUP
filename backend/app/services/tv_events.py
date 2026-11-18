"""Detect new seasons/episodes for shows without creating season media rows.

MDBList can represent shows, seasons and episodes, but the acquisition pipeline
and the sync planner intentionally operate on the parent show. A new season or
episode is recorded as an audit event on the show; it is never sent as a
separate entity.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.core.time import utcnow
from app.db.models import Collection, CollectionSnapshot, Media, SnapshotItem
from app.domain.enums import AuditActorType, MediaType
from app.domain.errors import NotFoundError, ValidationError
from app.integrations.tmdb.client import TMDbClient, TMDbError
from app.repositories import audit
from app.repositories import collections as collections_repo
from app.repositories import episode_events as episode_events_repo
from app.repositories import sources as sources_repo

logger = get_logger(__name__)


@dataclass(frozen=True)
class TvChangeOutcome:
    checked: int
    season_events: int
    episode_events: int
    errors: int


@dataclass(frozen=True)
class EpisodeEventView:
    media_id: uuid.UUID
    title: str | None
    event_type: str
    season_number: int
    episode_number: int | None
    occurred_at: datetime | None
    source_key: str | None


def list_collection_episode_events(
    db: Session,
    collection_id: uuid.UUID,
    *,
    limit: int = 50,
) -> tuple[list[EpisodeEventView], int]:
    """Season/episode events of the parent shows in a SHOW collection."""
    collection = collections_repo.get_collection(db, collection_id)
    if collection is None:
        raise NotFoundError(
            "Collezione non trovata.", details={"collection_id": str(collection_id)}
        )
    if collection.media_type != MediaType.SHOW.value:
        raise ValidationError(
            "Gli eventi stagione/episodio esistono solo per le collezioni serie.",
            code="COLLECTION_NOT_SHOW",
            details={"media_type": collection.media_type},
        )
    snapshot_id = collection.last_valid_snapshot_id
    if snapshot_id is None:
        return [], 0
    rows = db.execute(
        select(Media.id, Media.title)
        .join(SnapshotItem, SnapshotItem.media_id == Media.id)
        .where(
            SnapshotItem.snapshot_id == snapshot_id,
            Media.media_type == MediaType.SHOW.value,
        )
        .distinct()
    ).all()
    titles = {media_id: title for media_id, title in rows}
    media_ids = list(titles)
    events = episode_events_repo.list_for_media_ids(db, media_ids, limit=limit)
    total = episode_events_repo.count_for_media_ids(db, media_ids)
    source_keys = {source.id: source.key for source in sources_repo.list_sources(db)}
    views = [
        EpisodeEventView(
            media_id=event.show_media_id,
            title=titles.get(event.show_media_id),
            event_type=event.event_type,
            season_number=event.season_number,
            episode_number=event.episode_number,
            occurred_at=event.occurred_at,
            source_key=source_keys.get(event.source_id),
        )
        for event in events
    ]
    return views, total


def _shows_in_tv_collections(db: Session, limit: int) -> list[Media]:
    media_ids = (
        select(SnapshotItem.media_id)
        .join(CollectionSnapshot, CollectionSnapshot.id == SnapshotItem.snapshot_id)
        .join(Collection, Collection.id == CollectionSnapshot.collection_id)
        .where(
            CollectionSnapshot.is_valid.is_(True),
            Collection.media_type == MediaType.SHOW.value,
            SnapshotItem.media_id.is_not(None),
        )
        .distinct()
    )
    stmt = (
        select(Media)
        .where(
            Media.media_type == MediaType.SHOW.value,
            Media.tmdb_id.is_not(None),
            Media.id.in_(media_ids),
        )
        .order_by(Media.updated_at)
        .limit(max(1, limit))
    )
    return list(db.scalars(stmt).all())


def detect_tv_changes(
    db: Session,
    client: TMDbClient,
    *,
    limit: int = 50,
) -> TvChangeOutcome:
    shows = _shows_in_tv_collections(db, limit)
    season_events = 0
    episode_events = 0
    errors = 0
    for media in shows:
        if media.tmdb_id is None:
            continue
        try:
            details = client.tv_details(media.tmdb_id)
        except TMDbError as exc:
            errors += 1
            logger.warning("tv_details_failed", media_id=str(media.id), error=type(exc).__name__)
            continue
        metadata = dict(media.metadata_json or {})
        previous_seasons = metadata.get("number_of_seasons")
        previous_episodes = metadata.get("number_of_episodes")
        new_seasons = details.number_of_seasons
        new_episodes = details.number_of_episodes
        if (
            isinstance(previous_seasons, int)
            and isinstance(new_seasons, int)
            and new_seasons > previous_seasons
        ):
            season_events += 1
            audit.record(
                db,
                action="tv_season_added",
                entity_type="media",
                entity_id=media.id,
                actor_type=AuditActorType.SYSTEM,
                after={
                    "tmdb_id": media.tmdb_id,
                    "title": media.title,
                    "previous_seasons": previous_seasons,
                    "new_seasons": new_seasons,
                    "season_numbers": [
                        season.season_number
                        for season in details.seasons
                        if season.season_number > previous_seasons
                    ],
                },
            )
        if (
            isinstance(previous_episodes, int)
            and isinstance(new_episodes, int)
            and new_episodes > previous_episodes
        ):
            episode_events += 1
            audit.record(
                db,
                action="tv_episode_added",
                entity_type="media",
                entity_id=media.id,
                actor_type=AuditActorType.SYSTEM,
                after={
                    "tmdb_id": media.tmdb_id,
                    "title": media.title,
                    "previous_episodes": previous_episodes,
                    "new_episodes": new_episodes,
                },
            )
        metadata.update(
            {
                "number_of_seasons": new_seasons,
                "number_of_episodes": new_episodes,
                "tv_checked_at": utcnow().isoformat(),
            }
        )
        media.metadata_json = metadata
    db.commit()
    logger.info(
        "detect_tv_changes",
        checked=len(shows),
        season_events=season_events,
        episode_events=episode_events,
        errors=errors,
    )
    return TvChangeOutcome(
        checked=len(shows),
        season_events=season_events,
        episode_events=episode_events,
        errors=errors,
    )
