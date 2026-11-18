"""MDBList targets (table ``mdblist_target``)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UuidPrimaryKeyMixin, enum_check
from app.domain.enums import TargetMediaType


class MdblistTarget(UuidPrimaryKeyMixin, TimestampMixin, Base):
    """A remote MDBList list. ``remote_list_id`` is the stable key; slug/URL display only."""

    __tablename__ = "mdblist_target"
    __table_args__ = (
        CheckConstraint(enum_check("mediatype", TargetMediaType), name="mediatype_valid"),
        UniqueConstraint("id", "mediatype", name="uq_mdblist_target_id_mediatype"),
    )

    remote_list_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    remote_slug: Mapped[str] = mapped_column(String(200), nullable=False)
    remote_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    mediatype: Mapped[str] = mapped_column(String(16), nullable=False)
    is_private: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    item_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_remote_read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    capabilities: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)
