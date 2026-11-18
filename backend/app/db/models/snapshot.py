"""Immutable collection snapshots and their items."""

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
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.db.base import Base, UuidPrimaryKeyMixin, enum_check
from app.domain.enums import (
    DateBasis,
    ResolutionStatus,
    SnapshotQuality,
    SnapshotStatus,
)


class CollectionSnapshot(UuidPrimaryKeyMixin, Base):
    """One acquisition attempt. Only valid snapshots authorize MIRROR removals."""

    __tablename__ = "collection_snapshot"
    __table_args__ = (
        CheckConstraint(enum_check("status", SnapshotStatus), name="status_valid"),
        CheckConstraint(enum_check("quality", SnapshotQuality), name="quality_valid"),
        CheckConstraint(
            "quality <> 'CLEAN' OR unresolved_count = 0", name="clean_snapshot_fully_resolved"
        ),
        CheckConstraint(
            "NOT is_valid OR (status = 'COMPLETE' AND quality = 'CLEAN'"
            " AND items_count > 0 AND error_count = 0 AND unresolved_count = 0)",
            name="valid_snapshot_complete",
        ),
        Index(
            "snapshot_one_running_uq",
            "collection_id",
            unique=True,
            sqlite_where=text("status = 'RUNNING'"),
            postgresql_where=text("status = 'RUNNING'"),
        ),
        Index("snapshot_collection_idx", "collection_id", "started_at"),
        Index("snapshot_items_source_idx", "items_from_snapshot_id"),
    )

    collection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("collection.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    quality: Mapped[str] = mapped_column(
        String(16), nullable=False, default=SnapshotQuality.CLEAN.value
    )
    is_valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pages_expected: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pages_fetched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    items_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    resolved_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unresolved_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    errors: Mapped[Any] = mapped_column(JSON, nullable=False, default=list)
    warnings: Mapped[Any] = mapped_column(JSON, nullable=False, default=list)
    source_revision: Mapped[str | None] = mapped_column(String(200), nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # A verified snapshot identical to the previous valid one reuses its items
    # instead of copying thousands of rows. ``items_from_snapshot_id`` points at
    # the snapshot that owns the rows; readers must resolve it transparently.
    items_from_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("collection_snapshot.id", ondelete="SET NULL"), nullable=True
    )
    last_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    invalid_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    job_execution_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("job_execution.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class SnapshotItem(UuidPrimaryKeyMixin, Base):
    """One item inside a snapshot; unresolved items keep ``media_id`` NULL."""

    __tablename__ = "snapshot_item"
    __table_args__ = (
        CheckConstraint(enum_check("date_basis", DateBasis), name="date_basis_valid"),
        CheckConstraint(
            enum_check("resolution_status", ResolutionStatus), name="resolution_status_valid"
        ),
        CheckConstraint(
            "availability_status IS NULL OR availability_status IN "
            "('CURRENT', 'UPCOMING', 'LEAVING')",
            name="availability_status_valid",
        ),
        UniqueConstraint("snapshot_id", "position", name="uq_snapshot_item_position"),
        Index(
            "snapshot_item_media_uq",
            "snapshot_id",
            "media_id",
            unique=True,
            sqlite_where=text("media_id IS NOT NULL"),
            postgresql_where=text("media_id IS NOT NULL"),
        ),
        Index("snapshot_item_media_idx", "media_id"),
    )

    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("collection_snapshot.id", ondelete="CASCADE"), nullable=False
    )
    media_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("media.id"), nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    source_item_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source_payload: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)
    source_date_created: Mapped[date | None] = mapped_column(Date, nullable=True)
    date_basis: Mapped[str] = mapped_column(String(32), nullable=False)
    resolution_status: Mapped[str] = mapped_column(String(16), nullable=False)
    resolution_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # NULL for sources that declare no availability state (TMDb, manual CSV).
    availability_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
