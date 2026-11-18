"""Catalog sources and their healthcheck history."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.db.models import Source, SourceHealthcheck


def list_sources(db: Session) -> list[Source]:
    return list(db.scalars(select(Source).order_by(Source.name)).all())


def get_source(db: Session, source_id: uuid.UUID) -> Source | None:
    return db.get(Source, source_id)


def get_source_by_key(db: Session, key: str) -> Source | None:
    return db.scalar(select(Source).where(Source.key == key))


def record_healthcheck(
    db: Session,
    source: Source,
    *,
    status: str,
    latency_ms: int | None,
    message: str | None,
    details: dict[str, Any] | None = None,
    checked_at: datetime | None = None,
) -> SourceHealthcheck:
    """Append a healthcheck row and refresh the denormalized source status."""
    moment = checked_at or utcnow()
    entry = SourceHealthcheck(
        source_id=source.id,
        status=status,
        latency_ms=latency_ms,
        message=message,
        details=details or {},
        checked_at=moment,
    )
    db.add(entry)
    source.status = status
    source.status_message = message
    source.last_healthcheck_at = moment
    if status == "OK":
        source.last_success_at = moment
    db.flush()
    return entry
