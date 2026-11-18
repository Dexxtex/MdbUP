"""Canonical streaming providers and their per-source mappings."""

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

PROVIDER_KINDS = ("SVOD", "TVOD", "AVOD", "TVE", "STORE", "CINEMA", "CHANNEL")


class Provider(UuidPrimaryKeyMixin, TimestampMixin, Base):
    """Canonical provider identity (``netflix``, ``prime-video``, ...)."""

    __tablename__ = "provider"
    __table_args__ = (CheckConstraint(enum_check("kind", PROVIDER_KINDS), name="kind_valid"),)

    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="SVOD")
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    website_url: Mapped[str | None] = mapped_column(String(500), nullable=True)


class ProviderMapping(UuidPrimaryKeyMixin, TimestampMixin, Base):
    """Mapping between a canonical provider and an external provider id.

    Provider ids are never hardcoded: they are resolved on every sync and mapped
    onto the canonical registry. Variants (Amazon Channel, with Ads, ...) are
    separate mappings, not the same provider.
    """

    __tablename__ = "provider_mapping"
    __table_args__ = (
        UniqueConstraint(
            "source_id",
            "country_code",
            "external_provider_id",
            name="uq_provider_mapping_source_country_external",
        ),
        Index("provider_mapping_provider_idx", "provider_id", "country_code"),
        Index(
            "provider_mapping_one_primary",
            "provider_id",
            "source_id",
            "country_code",
            unique=True,
            sqlite_where=text("is_primary = 1"),
            postgresql_where=text("is_primary = true"),
        ),
    )

    provider_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("provider.id", ondelete="CASCADE"), nullable=False
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source.id", ondelete="CASCADE"), nullable=False
    )
    country_code: Mapped[str] = mapped_column(String(2), nullable=False)
    external_provider_id: Mapped[str] = mapped_column(String(64), nullable=False)
    external_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    metadata_json: Mapped[Any] = mapped_column("metadata", JSON, nullable=False, default=dict)
