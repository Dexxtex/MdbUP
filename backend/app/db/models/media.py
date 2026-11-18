"""Canonical media identities (table ``media``)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UuidPrimaryKeyMixin, enum_check
from app.domain.enums import MediaType, ResolutionStatus


class Media(UuidPrimaryKeyMixin, TimestampMixin, Base):
    """A movie or a show.

    Identity is ``(media_type, tmdb_id)`` with ``(media_type, imdb_id)`` as
    fallback; the title is never a key. A row always carries at least one
    external id.
    """

    __tablename__ = "media"
    __table_args__ = (
        CheckConstraint(enum_check("media_type", MediaType), name="media_type_valid"),
        CheckConstraint(
            enum_check("resolution_status", ResolutionStatus), name="resolution_status_valid"
        ),
        CheckConstraint(
            "tmdb_id IS NOT NULL OR imdb_id IS NOT NULL"
            " OR tvdb_id IS NOT NULL OR trakt_id IS NOT NULL",
            name="external_id_required",
        ),
        UniqueConstraint("id", "media_type", name="uq_media_id_media_type"),
        Index(
            "media_tmdb_uq",
            "tmdb_id",
            "media_type",
            unique=True,
            sqlite_where=text("tmdb_id IS NOT NULL"),
            postgresql_where=text("tmdb_id IS NOT NULL"),
        ),
        Index(
            "media_imdb_uq",
            "imdb_id",
            "media_type",
            unique=True,
            sqlite_where=text("imdb_id IS NOT NULL"),
            postgresql_where=text("imdb_id IS NOT NULL"),
        ),
        Index("media_title_idx", "title"),
    )

    media_type: Mapped[str] = mapped_column(String(8), nullable=False)
    tmdb_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    imdb_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    tvdb_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    trakt_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    original_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    release_year: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    metadata_json: Mapped[Any] = mapped_column("metadata", JSON, nullable=False, default=dict)
    resolution_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ResolutionStatus.RESOLVED.value
    )
    not_found_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sync_suppressed_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
