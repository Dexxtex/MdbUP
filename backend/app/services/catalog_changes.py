"""Catalog change feed: ADDED/REMOVED between consecutive valid snapshots.

Only snapshots that are both ``COMPLETE`` and ``CLEAN`` are compared. The first
valid snapshot of a collection is its baseline and never produces ADDED events;
an invalid snapshot between two valid ones is skipped, so the comparison always
uses the last two valid snapshots. The feed is deduplicated per provider, media,
direction and Europe/Rome day so the same title is not repeated because it
appears in several collections of the same provider.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import ensure_utc, utcnow
from app.db.models import (
    Collection,
    CollectionSnapshot,
    EpisodeEvent,
    Media,
    SnapshotItem,
)
from app.domain.enums import SnapshotQuality, SnapshotStatus
from app.repositories import collections as collections_repo
from app.repositories import providers as providers_repo
from app.repositories import sources as sources_repo
from app.services.collections import source_label

ROME = ZoneInfo("Europe/Rome")
WINDOW_DELTAS: dict[str, timedelta] = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "14d": timedelta(days=14),
    "30d": timedelta(days=30),
}
DEFAULT_WINDOW = "24h"
MAX_PAGE_SIZE = 200


@dataclass(frozen=True)
class CatalogChange:
    media_id: uuid.UUID
    title: str
    year: int | None
    media_type: str
    provider_id: uuid.UUID
    provider_slug: str
    provider_name: str
    source_key: str
    source_label: str
    direction: str
    detected_at: datetime
    detected_at_rome: datetime
    collection_id: uuid.UUID
    collection_name: str
    collection_slug: str
    previous_snapshot_id: uuid.UUID
    current_snapshot_id: uuid.UUID
    season_number: int | None = None
    episode_number: int | None = None
    episode_event_type: str | None = None


@dataclass(frozen=True)
class CatalogChangeCounters:
    added_today: int
    removed_today: int
    added_window: int
    removed_window: int


@dataclass(frozen=True)
class CatalogChangePage:
    items: list[CatalogChange]
    total: int
    page: int
    page_size: int
    window: str
    generated_at: datetime
    counters: CatalogChangeCounters


def list_catalog_changes(
    db: Session,
    *,
    window: str = DEFAULT_WINDOW,
    provider_id: uuid.UUID | None = None,
    media_type: str | None = None,
    source_key: str | None = None,
    direction: str | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 50,
    now: datetime | None = None,
) -> CatalogChangePage:
    """Return the deduplicated change feed for the requested window."""
    window_name = window if window in WINDOW_DELTAS else DEFAULT_WINDOW
    moment = ensure_utc(now) if now is not None else utcnow()
    cutoff = moment - WINDOW_DELTAS[window_name]
    # Today in Rome can start more than 24h before (DST fall-back): generate
    # from the earlier bound so ``added_today`` never misses an event.
    rome_today_start = datetime.combine(
        moment.astimezone(ROME).date(), time.min, tzinfo=ROME
    ).astimezone(UTC)
    events = _events_in_window(db, cutoff=min(cutoff, rome_today_start))
    counters = _counters(events, moment=moment, cutoff=cutoff)
    filtered = [
        event
        for event in events
        if event.detected_at >= cutoff
        and _matches(
            event,
            provider_id=provider_id,
            media_type=media_type,
            source_key=source_key,
            direction=direction,
            search=search,
        )
    ]
    deduplicated = _deduplicate(filtered)
    effective_page = max(1, page)
    effective_size = max(1, min(page_size, MAX_PAGE_SIZE))
    offset = (effective_page - 1) * effective_size
    return CatalogChangePage(
        items=deduplicated[offset : offset + effective_size],
        total=len(deduplicated),
        page=effective_page,
        page_size=effective_size,
        window=window_name,
        generated_at=moment,
        counters=counters,
    )


def _matches(
    event: CatalogChange,
    *,
    provider_id: uuid.UUID | None,
    media_type: str | None,
    source_key: str | None,
    direction: str | None,
    search: str | None,
) -> bool:
    if provider_id is not None and event.provider_id != provider_id:
        return False
    if media_type is not None and event.media_type != media_type:
        return False
    if source_key is not None and event.source_key != source_key:
        return False
    if direction is not None and event.direction != direction:
        return False
    if search:
        needle = search.strip().lower()
        if needle and needle not in event.title.lower():
            return False
    return True


def _deduplicate(events: list[CatalogChange]) -> list[CatalogChange]:
    """Keep one event per provider/media/direction/day (Europe/Rome)."""
    seen: set[tuple[uuid.UUID, uuid.UUID, str, date]] = set()
    result: list[CatalogChange] = []
    for event in sorted(
        events,
        key=lambda item: (item.detected_at, str(item.collection_id)),
        reverse=True,
    ):
        key = (
            event.provider_id,
            event.media_id,
            event.direction,
            event.detected_at_rome.date(),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(event)
    result.sort(key=lambda item: (item.title.lower(), str(item.media_id)))
    result.sort(key=lambda item: item.detected_at, reverse=True)
    return result


def _counters(
    events: list[CatalogChange],
    *,
    moment: datetime,
    cutoff: datetime,
) -> CatalogChangeCounters:
    deduplicated = _deduplicate(events)
    today = moment.astimezone(ROME).date()
    added_today = sum(
        1
        for event in deduplicated
        if event.direction == "ADDED" and event.detected_at_rome.date() == today
    )
    removed_today = sum(
        1
        for event in deduplicated
        if event.direction == "REMOVED" and event.detected_at_rome.date() == today
    )
    added_window = sum(
        1 for event in deduplicated if event.direction == "ADDED" and event.detected_at >= cutoff
    )
    removed_window = sum(
        1 for event in deduplicated if event.direction == "REMOVED" and event.detected_at >= cutoff
    )
    return CatalogChangeCounters(
        added_today=added_today,
        removed_today=removed_today,
        added_window=added_window,
        removed_window=removed_window,
    )


def _events_in_window(db: Session, *, cutoff: datetime) -> list[CatalogChange]:
    collections = collections_repo.list_collections(db)
    if not collections:
        return []
    collections_by_id = {collection.id: collection for collection in collections}
    providers = {provider.id: provider for provider in providers_repo.list_providers(db)}
    sources = {source.id: source for source in sources_repo.list_sources(db)}
    snapshots = db.scalars(
        select(CollectionSnapshot)
        .where(
            CollectionSnapshot.collection_id.in_(list(collections_by_id)),
            CollectionSnapshot.status == SnapshotStatus.COMPLETE.value,
            CollectionSnapshot.quality == SnapshotQuality.CLEAN.value,
        )
        .order_by(
            CollectionSnapshot.collection_id,
            CollectionSnapshot.started_at,
            CollectionSnapshot.id,
        )
    ).all()
    by_collection: dict[uuid.UUID, list[CollectionSnapshot]] = defaultdict(list)
    for snapshot in snapshots:
        by_collection[snapshot.collection_id].append(snapshot)
    pairs: list[tuple[Collection, CollectionSnapshot, CollectionSnapshot, datetime]] = []
    for collection_id, collection_snapshots in by_collection.items():
        collection = collections_by_id[collection_id]
        for previous, current in zip(collection_snapshots, collection_snapshots[1:], strict=False):
            detected_at = ensure_utc(current.finished_at or current.started_at)
            if detected_at < cutoff:
                continue
            pairs.append((collection, previous, current, detected_at))
    if not pairs:
        return []
    snapshot_ids = {
        snapshot.id for _c, previous, current, _d in pairs for snapshot in (previous, current)
    }
    media_by_snapshot = _snapshot_media(db, snapshot_ids)
    specs: list[
        tuple[Collection, CollectionSnapshot, CollectionSnapshot, datetime, uuid.UUID, str]
    ] = []
    for collection, previous, current, detected_at in pairs:
        previous_ids = media_by_snapshot.get(previous.id, set())
        current_ids = media_by_snapshot.get(current.id, set())
        for media_id in current_ids - previous_ids:
            specs.append((collection, previous, current, detected_at, media_id, "ADDED"))
        for media_id in previous_ids - current_ids:
            specs.append((collection, previous, current, detected_at, media_id, "REMOVED"))
    if not specs:
        return []
    media_ids = {media_id for _c, _p, _curr, _d, media_id, _dir in specs}
    media_by_id = {
        media.id: media for media in db.scalars(select(Media).where(Media.id.in_(media_ids))).all()
    }
    current_snapshot_ids = {current.id for _c, _p, current, _d, _m, _dir in specs}
    episodes = _episode_events(db, current_snapshot_ids)
    events: list[CatalogChange] = []
    for collection, previous, current, detected_at, media_id, direction in specs:
        media = media_by_id.get(media_id)
        if media is None:
            continue
        provider = providers.get(collection.provider_id)
        source = sources.get(collection.source_id)
        season_number = episode_number = episode_event_type = None
        if media.media_type == "SHOW":
            selected = _select_episode(episodes.get((current.id, media_id), []), direction)
            if selected is not None:
                season_number = selected.season_number
                episode_number = selected.episode_number
                episode_event_type = selected.event_type
        events.append(
            CatalogChange(
                media_id=media.id,
                title=media.title,
                year=media.release_year,
                media_type=media.media_type,
                provider_id=collection.provider_id,
                provider_slug=provider.slug if provider is not None else "",
                provider_name=provider.name if provider is not None else "",
                source_key=source.key if source is not None else "",
                source_label=source_label(source, collection.kind) or "",
                direction=direction,
                detected_at=detected_at,
                detected_at_rome=detected_at.astimezone(ROME),
                collection_id=collection.id,
                collection_name=collection.name,
                collection_slug=collection.slug,
                previous_snapshot_id=previous.id,
                current_snapshot_id=current.id,
                season_number=season_number,
                episode_number=episode_number,
                episode_event_type=episode_event_type,
            )
        )
    return events


def _snapshot_media(db: Session, snapshot_ids: set[uuid.UUID]) -> dict[uuid.UUID, set[uuid.UUID]]:
    if not snapshot_ids:
        return {}
    result: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    rows = db.execute(
        select(SnapshotItem.snapshot_id, SnapshotItem.media_id).where(
            SnapshotItem.snapshot_id.in_(snapshot_ids),
            SnapshotItem.media_id.is_not(None),
        )
    ).all()
    for snapshot_id, media_id in rows:
        result[snapshot_id].add(media_id)
    return result


def _episode_events(
    db: Session, snapshot_ids: set[uuid.UUID]
) -> dict[tuple[uuid.UUID, uuid.UUID], list[EpisodeEvent]]:
    if not snapshot_ids:
        return {}
    result: dict[tuple[uuid.UUID, uuid.UUID], list[EpisodeEvent]] = defaultdict(list)
    rows = db.scalars(select(EpisodeEvent).where(EpisodeEvent.snapshot_id.in_(snapshot_ids))).all()
    for event in rows:
        result[(event.snapshot_id, event.show_media_id)].append(event)
    return result


def _select_episode(events: list[EpisodeEvent], direction: str) -> EpisodeEvent | None:
    if not events:
        return None
    suffix = "_ADDED" if direction == "ADDED" else "_REMOVED"
    preferred = [event for event in events if event.event_type.endswith(suffix)]
    pool = preferred or events
    return min(
        pool,
        key=lambda event: (
            event.season_number,
            event.episode_number if event.episode_number is not None else -1,
            event.created_at,
        ),
    )
