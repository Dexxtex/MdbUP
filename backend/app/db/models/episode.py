"""Season/episode events (table ``episode_event``).

Episodes are never separate ``media`` rows: a new episode produces an event that
points at the show.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.db.base import Base, UuidPrimaryKeyMixin, enum_check
from app.domain.enums import EpisodeEventType


class EpisodeEvent(UuidPrimaryKeyMixin, Base):
    """A season or episode addition/removal observed for a show."""

    __tablename__ = "episode_event"
    __table_args__ = (
        CheckConstraint("media_type = 'SHOW'", name="media_type_show_only"),
        CheckConstraint(enum_check("event_type", EpisodeEventType), name="event_type_valid"),
        ForeignKeyConstraint(
            ["show_media_id", "media_type"],
            ["media.id", "media.media_type"],
            ondelete="CASCADE",
            name="fk_episode_event_media",
        ),
        UniqueConstraint(
            "show_media_id",
            "provider_id",
            "country_code",
            "source_id",
            "event_type",
            "season_number",
            "episode_number",
            name="uq_episode_event_identity",
            postgresql_nulls_not_distinct=True,
        ),
        Index("episode_event_show_idx", "show_media_id", "occurred_at"),
    )

    show_media_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    media_type: Mapped[str] = mapped_column(String(8), nullable=False, default="SHOW")
    provider_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("provider.id"), nullable=False)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source.id"), nullable=False)
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("collection_snapshot.id"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(24), nullable=False)
    season_number: Mapped[int] = mapped_column(Integer, nullable=False)
    episode_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_payload: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
