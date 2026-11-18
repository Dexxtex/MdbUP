"""Season/episode event persistence (episodes are never media rows)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import EpisodeEvent


def get_event(
    db: Session,
    *,
    show_media_id: uuid.UUID,
    provider_id: uuid.UUID,
    country_code: str,
    source_id: uuid.UUID,
    event_type: str,
    season_number: int,
    episode_number: int | None,
) -> EpisodeEvent | None:
    """Look up an event by its identity, ``episode_number`` NULL included."""
    stmt = select(EpisodeEvent).where(
        EpisodeEvent.show_media_id == show_media_id,
        EpisodeEvent.provider_id == provider_id,
        EpisodeEvent.country_code == country_code,
        EpisodeEvent.source_id == source_id,
        EpisodeEvent.event_type == event_type,
        EpisodeEvent.season_number == season_number,
    )
    if episode_number is None:
        stmt = stmt.where(EpisodeEvent.episode_number.is_(None))
    else:
        stmt = stmt.where(EpisodeEvent.episode_number == episode_number)
    return db.scalar(stmt)


def get_or_create_event(
    db: Session,
    *,
    show_media_id: uuid.UUID,
    provider_id: uuid.UUID,
    country_code: str,
    source_id: uuid.UUID,
    snapshot_id: uuid.UUID | None,
    event_type: str,
    season_number: int,
    episode_number: int | None,
    occurred_at: datetime | None,
    source_payload: dict[str, Any],
) -> tuple[EpisodeEvent, bool]:
    """Return the event and whether it was created, keeping observation idempotent."""
    existing = get_event(
        db,
        show_media_id=show_media_id,
        provider_id=provider_id,
        country_code=country_code,
        source_id=source_id,
        event_type=event_type,
        season_number=season_number,
        episode_number=episode_number,
    )
    if existing is not None:
        return existing, False
    event = EpisodeEvent(
        show_media_id=show_media_id,
        media_type="SHOW",
        provider_id=provider_id,
        country_code=country_code,
        source_id=source_id,
        snapshot_id=snapshot_id,
        event_type=event_type,
        season_number=season_number,
        episode_number=episode_number,
        occurred_at=occurred_at,
        source_payload=source_payload,
    )
    db.add(event)
    db.flush()
    return event, True


def count_for_media_ids(db: Session, media_ids: Sequence[uuid.UUID]) -> int:
    if not media_ids:
        return 0
    return int(
        db.scalar(
            select(func.count())
            .select_from(EpisodeEvent)
            .where(EpisodeEvent.show_media_id.in_(list(media_ids)))
        )
        or 0
    )


def list_for_media_ids(
    db: Session,
    media_ids: Sequence[uuid.UUID],
    *,
    limit: int = 50,
) -> list[EpisodeEvent]:
    if not media_ids:
        return []
    stmt = (
        select(EpisodeEvent)
        .where(EpisodeEvent.show_media_id.in_(list(media_ids)))
        .order_by(EpisodeEvent.occurred_at.desc(), EpisodeEvent.created_at.desc())
        .limit(max(1, limit))
    )
    return list(db.scalars(stmt).all())
