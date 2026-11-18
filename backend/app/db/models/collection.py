"""Catalog collections (table ``collection``)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UuidPrimaryKeyMixin, enum_check
from app.domain.enums import (
    CollectionKind,
    CollectionOrigin,
    DateBasis,
    MediaType,
    OfferType,
)

COLLECTION_SORT_MODES = (
    "SOURCE_ORDER",
    "POPULARITY",
    "TITLE",
    "RELEASE_DATE",
    "ADDED_DATE",
    "CUSTOM",
)


class Collection(UuidPrimaryKeyMixin, TimestampMixin, Base):
    """A provider catalog slice with explicit provenance and date basis.

    ``offer_types`` is a JSON array (the PostgreSQL DDL uses ``TEXT[]``) to keep
    the metadata portable across SQLite and PostgreSQL.
    """

    __tablename__ = "collection"
    __table_args__ = (
        CheckConstraint(enum_check("media_type", MediaType), name="media_type_valid"),
        CheckConstraint(enum_check("kind", CollectionKind), name="kind_valid"),
        CheckConstraint(enum_check("origin", CollectionOrigin), name="origin_valid"),
        CheckConstraint(enum_check("date_basis", DateBasis), name="date_basis_valid"),
        CheckConstraint(enum_check("sort_mode", COLLECTION_SORT_MODES), name="sort_mode_valid"),
        UniqueConstraint("id", "media_type", name="uq_collection_id_media_type"),
        Index("collection_provider_idx", "provider_id", "country_code", "media_type"),
        Index("collection_origin_idx", "origin", "kind"),
        Index(
            "collection_source_key_uq",
            "source_id",
            "provider_id",
            "country_code",
            "media_type",
            "kind",
            "source_collection_key",
            unique=True,
            sqlite_where=text("source_collection_key IS NOT NULL"),
            postgresql_where=text("source_collection_key IS NOT NULL"),
        ),
    )

    slug: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source.id"), nullable=False)
    provider_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("provider.id"), nullable=False)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False, default="IT")
    media_type: Mapped[str] = mapped_column(String(8), nullable=False)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    origin: Mapped[str] = mapped_column(String(16), nullable=False)
    date_basis: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    source_collection_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    offer_types: Mapped[Any] = mapped_column(
        JSON, nullable=False, default=lambda: [OfferType.FLATRATE.value]
    )
    filters: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)
    quality_flags: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)
    sort_mode: Mapped[str] = mapped_column(String(24), nullable=False, default="SOURCE_ORDER")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Deferrable FK to collection_snapshot is intentionally not declared in the
    # metadata: it would create a table cycle that breaks create_all() on SQLite.
    # The pointer is maintained by the acquisition service.
    last_valid_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
