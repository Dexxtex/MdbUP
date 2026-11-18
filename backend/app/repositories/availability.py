"""Observed availability persistence and first-seen history."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import ensure_utc, utcnow
from app.db.models import Availability


def get_observed(
    db: Session,
    *,
    media_id: uuid.UUID,
    provider_id: uuid.UUID,
    country_code: str,
    offer_type: str,
    source_id: uuid.UUID,
) -> Availability | None:
    return db.scalar(
        select(Availability).where(
            Availability.media_id == media_id,
            Availability.provider_id == provider_id,
            Availability.country_code == country_code,
            Availability.offer_type == offer_type,
            Availability.source_id == source_id,
            Availability.presentation_type.is_(None),
            Availability.channel.is_(None),
            Availability.plan.is_(None),
        )
    )


def upsert_observed(
    db: Session,
    *,
    media_id: uuid.UUID,
    provider_id: uuid.UUID,
    country_code: str,
    offer_type: str,
    source_id: uuid.UUID,
    first_seen_at: datetime,
    seen_at: datetime | None = None,
    metadata: dict[str, object] | None = None,
) -> Availability:
    """Record an observation, preserving the earliest ``first_seen_at``."""
    first_seen = ensure_utc(first_seen_at)
    moment = ensure_utc(seen_at or utcnow())
    row = get_observed(
        db,
        media_id=media_id,
        provider_id=provider_id,
        country_code=country_code,
        offer_type=offer_type,
        source_id=source_id,
    )
    if row is None:
        row = Availability(
            media_id=media_id,
            provider_id=provider_id,
            country_code=country_code,
            offer_type=offer_type,
            source_id=source_id,
            first_seen_at=first_seen,
            last_seen_at=moment,
            last_checked_at=moment,
            is_active=True,
            metadata_json=metadata or {},
        )
        db.add(row)
        db.flush()
        return row
    if first_seen < ensure_utc(row.first_seen_at):
        row.first_seen_at = first_seen
    if moment > ensure_utc(row.last_seen_at):
        row.last_seen_at = moment
    row.last_checked_at = moment
    row.is_active = True
    if metadata:
        merged = dict(row.metadata_json or {})
        merged.update(metadata)
        row.metadata_json = merged
    db.flush()
    return row
