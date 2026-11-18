"""External data sources (table ``source``)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UuidPrimaryKeyMixin, enum_check
from app.domain.enums import CollectionOrigin, SourceStatus, SourceType


class Source(UuidPrimaryKeyMixin, TimestampMixin, Base):
    """A catalog source (TMDb, JustWatch partner/export, manual CSV)."""

    __tablename__ = "source"
    __table_args__ = (
        CheckConstraint(enum_check("type", SourceType), name="type_valid"),
        CheckConstraint(enum_check("status", SourceStatus), name="status_valid"),
        CheckConstraint(
            enum_check("origin_default", CollectionOrigin), name="origin_default_valid"
        ),
        CheckConstraint(
            "NOT is_official OR origin_default = 'OFFICIAL'", name="official_origin_consistent"
        ),
    )

    key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    config: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)
    capabilities: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)
    is_official: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    origin_default: Mapped[str] = mapped_column(
        String(16), nullable=False, default=CollectionOrigin.AGGREGATOR.value
    )
    requires_contract: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=SourceStatus.UNCONFIGURED.value
    )
    status_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_healthcheck_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
