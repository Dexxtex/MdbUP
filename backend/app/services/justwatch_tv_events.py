"""Season/episode timeline for JustWatch SHOW collections.

``newTitles(pageType=NEW)`` ignores ``objectTypes``: in Italy it answers only
movies, so a SHOW collection cannot be driven by the novelties endpoint (a SHOW
novelty collection stays empty and therefore invalid). The timeline is therefore
observed on the shows already acquired by a JustWatch SHOW ``CATALOG`` /
``RECENTLY_ADDED`` snapshot, comparing seasons and episodes with the baseline
stored in ``media.metadata_json``.

- First observation stores the baseline and emits **no** event.
- Later observations insert ``episode_event`` rows (``SEASON_ADDED`` /
  ``EPISODE_ADDED``) attached to the parent show; an episode never becomes a
  media row.
- Per-run caps: 20 shows, 5 seasons, 50 episodes.
- TV failures are best-effort: they become warnings on the catalog snapshot and
  never invalidate it.
- The operation is idempotent: the event identity is checked before insert.

``occurred_at`` is the observation moment, not a provider date: the public
endpoint publishes no add date (``date_basis=UNKNOWN``).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.justwatch.connector import JustWatchConnector
from app.core.logging import get_logger
from app.core.time import utcnow
from app.db.models import Collection, Media, SnapshotItem
from app.domain.enums import EpisodeEventType, MediaType
from app.repositories import episode_events as episode_events_repo

logger = get_logger(__name__)

MAX_SHOWS = 20
MAX_SEASONS = 5
MAX_EPISODES = 50

BASELINE_KEY = "justwatch_tv"


@dataclass(frozen=True)
class JustWatchTvOutcome:
    shows: int
    baselines: int
    season_events: int
    episode_events: int
    errors: int
    warnings: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class _ShowTarget:
    media: Media
    node_id: str
    provider_id: uuid.UUID
    country_code: str
    source_id: uuid.UUID


def observe_tv_events(
    db: Session,
    *,
    collection: Collection,
    connector: JustWatchConnector,
    snapshot_id: uuid.UUID | None = None,
    max_shows: int = MAX_SHOWS,
    max_seasons: int = MAX_SEASONS,
    max_episodes: int = MAX_EPISODES,
) -> JustWatchTvOutcome:
    """Compare seasons/episodes of the shows in one JustWatch SHOW collection."""
    targets = _show_targets(db, collection, limit=max_shows)
    baselines = 0
    season_events = 0
    episode_events = 0
    errors = 0
    warnings: list[str] = []
    for target in targets:
        try:
            created_baseline, seasons, episodes = _observe_show(
                db,
                target=target,
                connector=connector,
                snapshot_id=snapshot_id,
                max_seasons=max_seasons,
                max_episodes=max_episodes,
            )
        except Exception as exc:  # best-effort: TV must not break the catalog
            errors += 1
            warnings.append(f"TV_EVENTS_FAILED:{target.media.id}:{type(exc).__name__}")
            logger.warning(
                "justwatch_tv_events_failed",
                media_id=str(target.media.id),
                error=type(exc).__name__,
            )
            continue
        if created_baseline:
            baselines += 1
        season_events += seasons
        episode_events += episodes
    return JustWatchTvOutcome(
        shows=len(targets),
        baselines=baselines,
        season_events=season_events,
        episode_events=episode_events,
        errors=errors,
        warnings=tuple(warnings),
    )


def _show_targets(db: Session, collection: Collection, *, limit: int) -> list[_ShowTarget]:
    """Shows of the collection's last valid snapshot, with their JustWatch node id."""
    snapshot_id = collection.last_valid_snapshot_id
    if snapshot_id is None:
        return []
    rows = db.execute(
        select(SnapshotItem, Media)
        .join(Media, SnapshotItem.media_id == Media.id)
        .where(
            SnapshotItem.snapshot_id == snapshot_id,
            SnapshotItem.media_id.is_not(None),
            Media.media_type == MediaType.SHOW.value,
        )
        .order_by(SnapshotItem.position)
    ).all()
    targets: list[_ShowTarget] = []
    for item, media in rows:
        node_id = str((item.source_payload or {}).get("id") or "").strip()
        if not node_id:
            continue
        targets.append(
            _ShowTarget(
                media=media,
                node_id=node_id,
                provider_id=collection.provider_id,
                country_code=collection.country_code,
                source_id=collection.source_id,
            )
        )
        if len(targets) >= max(1, limit):
            break
    return targets


def _observe_show(
    db: Session,
    *,
    target: _ShowTarget,
    connector: JustWatchConnector,
    snapshot_id: uuid.UUID | None,
    max_seasons: int,
    max_episodes: int,
) -> tuple[bool, int, int]:
    """Return ``(created_baseline, season_events, episode_events)`` for one show."""
    observed_at = utcnow()
    seasons = list(connector.list_seasons(target.node_id, target.country_code))[
        : max(1, max_seasons)
    ]
    observed_seasons: dict[str, dict[str, object]] = {}
    episode_budget = max(0, max_episodes)
    episode_numbers: dict[str, tuple[int, int | None]] = {}
    for position, season in enumerate(seasons):
        if episode_budget <= 0:
            break
        episodes = list(connector.list_episodes(season.node_id, target.country_code))[
            :episode_budget
        ]
        episode_budget -= len(episodes)
        season_number = next(
            (episode.season_number for episode in episodes if episode.season_number is not None),
            None,
        )
        if season_number is None:
            # The endpoint does not expose a season number on the season node:
            # fall back to the 1-based position of the season in the answer.
            season_number = position + 1
        observed_seasons[season.node_id] = {
            "season_number": season_number,
            "episodes": [episode.node_id for episode in episodes],
        }
        for episode in episodes:
            episode_numbers[episode.node_id] = (season_number, episode.episode_number)

    metadata = dict(target.media.metadata_json or {})
    previous = metadata.get(BASELINE_KEY)
    baseline_record = {
        "baseline_at": (previous or {}).get("baseline_at") if isinstance(previous, dict) else None,
        "observed_at": observed_at.isoformat(),
        "seasons": observed_seasons,
    }
    if not isinstance(previous, dict) or not isinstance(previous.get("seasons"), dict):
        # First observation: baseline only, never events.
        baseline_record["baseline_at"] = observed_at.isoformat()
        metadata[BASELINE_KEY] = baseline_record
        target.media.metadata_json = metadata
        db.flush()
        return True, 0, 0

    previous_seasons: dict[str, object] = previous["seasons"]
    baseline_record["baseline_at"] = previous.get("baseline_at") or observed_at.isoformat()
    season_events = 0
    episode_events = 0
    for season_id, season_data in observed_seasons.items():
        season_number = int(season_data["season_number"])  # type: ignore[arg-type]
        previous_season = previous_seasons.get(season_id)
        if not isinstance(previous_season, dict):
            _, created = episode_events_repo.get_or_create_event(
                db,
                show_media_id=target.media.id,
                provider_id=target.provider_id,
                country_code=target.country_code,
                source_id=target.source_id,
                snapshot_id=snapshot_id,
                event_type=EpisodeEventType.SEASON_ADDED.value,
                season_number=season_number,
                episode_number=None,
                occurred_at=observed_at,
                source_payload={"source": "justwatch", "season_id": season_id},
            )
            season_events += int(created)
        previous_episodes = (
            previous_season.get("episodes") if isinstance(previous_season, dict) else []
        )
        known_episodes = {str(value) for value in previous_episodes or []}
        for episode_id in season_data["episodes"]:  # type: ignore[union-attr]
            episode_number = episode_numbers.get(str(episode_id), (season_number, None))[1]
            if str(episode_id) in known_episodes:
                continue
            _, created = episode_events_repo.get_or_create_event(
                db,
                show_media_id=target.media.id,
                provider_id=target.provider_id,
                country_code=target.country_code,
                source_id=target.source_id,
                snapshot_id=snapshot_id,
                event_type=EpisodeEventType.EPISODE_ADDED.value,
                season_number=season_number,
                episode_number=episode_number,
                occurred_at=observed_at,
                source_payload={
                    "source": "justwatch",
                    "season_id": season_id,
                    "episode_id": str(episode_id),
                },
            )
            episode_events += int(created)
    metadata[BASELINE_KEY] = baseline_record
    target.media.metadata_json = metadata
    db.flush()
    return False, season_events, episode_events
