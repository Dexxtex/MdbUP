"""Observed provider availability (table ``availability``)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UuidPrimaryKeyMixin, enum_check
from app.domain.enums import OfferType


class Availability(UuidPrimaryKeyMixin, Base):
    """A provider offer observed for a media item in a country.

    ``first_seen_at`` is the app's first observation, not the provider's
    add date; the source-declared date lives in ``source_date_created``.
    """

    __tablename__ = "availability"
    __table_args__ = (
        CheckConstraint(enum_check("offer_type", OfferType), name="offer_type_valid"),
        UniqueConstraint(
            "media_id",
            "provider_id",
            "country_code",
            "offer_type",
            "presentation_type",
            "channel",
            "plan",
            "source_id",
            name="uq_availability_offer",
            postgresql_nulls_not_distinct=True,
        ),
        Index("availability_lookup_idx", "provider_id", "country_code", "offer_type", "is_active"),
        Index("availability_media_idx", "media_id"),
    )

    media_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("media.id", ondelete="CASCADE"), nullable=False
    )
    provider_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("provider.id"), nullable=False)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False)
    offer_type: Mapped[str] = mapped_column(String(16), nullable=False)
    presentation_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    channel: Mapped[str | None] = mapped_column(String(120), nullable=True)
    plan: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source.id"), nullable=False)
    source_offer_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source_date_created: Mapped[date | None] = mapped_column(Date, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    metadata_json: Mapped[Any] = mapped_column("metadata", JSON, nullable=False, default=dict)
