"""Sync bindings, runs, operations and run events."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.db.base import (
    Base,
    BigIntPrimaryKeyMixin,
    TimestampMixin,
    UuidPrimaryKeyMixin,
    enum_check,
)
from app.domain.enums import (
    ACTIVE_RUN_STATUSES,
    TERMINAL_RUN_STATUSES,
    MediaType,
    SchedulePolicy,
    SyncMode,
    SyncOperationAction,
    SyncOperationStatus,
    SyncRunStatus,
)

_ACTIVE_STATUS_SQL = ", ".join(f"'{status.value}'" for status in ACTIVE_RUN_STATUSES)
_TERMINAL_STATUS_SQL = ", ".join(f"'{status.value}'" for status in TERMINAL_RUN_STATUSES)


class SyncBinding(UuidPrimaryKeyMixin, TimestampMixin, Base):
    """A collection-to-target binding with an explicit sync policy.

    ``media_type`` plus the composite foreign keys make it impossible to bind a
    movie collection to a show list.
    """

    __tablename__ = "sync_binding"
    __table_args__ = (
        CheckConstraint(enum_check("media_type", MediaType), name="media_type_valid"),
        CheckConstraint(enum_check("mode", SyncMode), name="mode_valid"),
        CheckConstraint(
            enum_check("schedule_policy", SchedulePolicy), name="schedule_policy_valid"
        ),
        CheckConstraint("max_removal_absolute >= 0", name="max_removal_absolute_non_negative"),
        CheckConstraint(
            "schedule_interval_hours IS NULL OR schedule_interval_hours > 0",
            name="schedule_interval_positive",
        ),
        CheckConstraint(
            "schedule_cron = '' OR schedule_interval_hours IS NULL",
            name="schedule_one_kind",
        ),
        CheckConstraint(
            "max_removal_percent >= 0 AND max_removal_percent <= 100",
            name="max_removal_percent_range",
        ),
        CheckConstraint(
            "max_addition_percent >= 0 AND max_addition_percent <= 100",
            name="max_addition_percent_range",
        ),
        CheckConstraint(
            "NOT is_enabled OR (policy_accepted_at IS NOT NULL AND policy_version IS NOT NULL)",
            name="enabled_binding_requires_policy",
        ),
        UniqueConstraint("collection_id", "target_id", name="uq_sync_binding_collection_target"),
        UniqueConstraint("id", "media_type", name="uq_sync_binding_id_media_type"),
        ForeignKeyConstraint(
            ["collection_id", "media_type"],
            ["collection.id", "collection.media_type"],
            ondelete="CASCADE",
            name="fk_sync_binding_collection",
        ),
        ForeignKeyConstraint(
            ["target_id", "media_type"],
            ["mdblist_target.id", "mdblist_target.mediatype"],
            ondelete="CASCADE",
            name="fk_sync_binding_target",
        ),
        Index(
            "binding_one_active_target_uq",
            "target_id",
            unique=True,
            sqlite_where=text("is_enabled = 1"),
            postgresql_where=text("is_enabled = true"),
        ),
        Index(
            "binding_due_idx",
            "next_run_at",
            sqlite_where=text("is_enabled = 1"),
            postgresql_where=text("is_enabled = true"),
        ),
    )

    collection_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    media_type: Mapped[str] = mapped_column(String(8), nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    schedule_cron: Mapped[str] = mapped_column(String(64), nullable=False)
    # Interval schedules are stored separately from cron: a cron expression
    # cannot represent every "every N hours" request without drift.
    schedule_interval_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Europe/Rome")
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    policy_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    policy_accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    policy_accepted_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_user.id"), nullable=True
    )
    max_removal_absolute: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    max_removal_percent: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=10.00)
    max_addition_percent: Mapped[float] = mapped_column(
        Numeric(5, 2), nullable=False, default=50.00
    )
    preserve_order: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reorder_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    require_manual_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    schedule_policy: Mapped[str] = mapped_column(
        String(24), nullable=False, default=SchedulePolicy.AUTO_APPLY_IF_SAFE.value
    )
    auto_apply_max_removals: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    auto_apply_max_removal_ratio: Mapped[float] = mapped_column(
        Numeric(5, 2), nullable=False, default=2.00
    )
    max_plan_age_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    # Deferrable FK to sync_run is not declared: it would create a table cycle
    # that breaks create_all() on SQLite. Maintained by the sync service.
    last_run_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SyncRun(UuidPrimaryKeyMixin, TimestampMixin, Base):
    """One synchronization attempt for a binding."""

    __tablename__ = "sync_run"
    __table_args__ = (
        CheckConstraint(enum_check("media_type", MediaType), name="media_type_valid"),
        CheckConstraint(enum_check("mode", SyncMode), name="mode_valid"),
        CheckConstraint(enum_check("status", SyncRunStatus), name="status_valid"),
        # ``trigger`` is a reserved word in SQL, so the column is named ``trigger_type``.
        CheckConstraint(
            "trigger_type IN ('MANUAL', 'SCHEDULED', 'RETRY')", name="trigger_type_valid"
        ),
        CheckConstraint(
            "NOT is_dry_run OR (added_count = 0 AND removed_count = 0)", name="dry_run_no_writes"
        ),
        CheckConstraint(
            f"status NOT IN ({_TERMINAL_STATUS_SQL}) OR finished_at IS NOT NULL",
            name="terminal_run_has_finished_at",
        ),
        ForeignKeyConstraint(
            ["binding_id", "media_type"],
            ["sync_binding.id", "sync_binding.media_type"],
            ondelete="CASCADE",
            name="fk_sync_run_binding",
        ),
        ForeignKeyConstraint(
            ["target_id", "media_type"],
            ["mdblist_target.id", "mdblist_target.mediatype"],
            name="fk_sync_run_target",
        ),
        Index(
            "run_one_active_binding_uq",
            "binding_id",
            unique=True,
            sqlite_where=text(f"status IN ({_ACTIVE_STATUS_SQL})"),
            postgresql_where=text(f"status IN ({_ACTIVE_STATUS_SQL})"),
        ),
        Index(
            "run_one_active_target_uq",
            "target_id",
            unique=True,
            sqlite_where=text(f"status IN ({_ACTIVE_STATUS_SQL})"),
            postgresql_where=text(f"status IN ({_ACTIVE_STATUS_SQL})"),
        ),
        Index("run_binding_idx", "binding_id", "created_at"),
        Index("run_notification_idx", "status", "notified_at"),
    )

    binding_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    media_type: Mapped[str] = mapped_column(String(8), nullable=False)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("collection_snapshot.id"), nullable=False
    )
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default=SyncRunStatus.PENDING.value
    )
    is_dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    trigger_type: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_item_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    remote_item_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    to_add_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    to_remove_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    added_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    removed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    uncertain_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    threshold_breached: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    requires_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"), nullable=True)
    plan_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    snapshot_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    order_enforced: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    warnings: Mapped[Any] = mapped_column(JSON, nullable=False, default=list)
    parent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sync_run.id"), nullable=True
    )
    not_before: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    abort_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    correlation_id: Mapped[uuid.UUID] = mapped_column(nullable=False, default=uuid.uuid4)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    # Set by the notification scanner after the first terminal/approval alert.
    # Existing rows are backfilled by migration 0003 so a new channel does not
    # replay the whole history.
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    summary: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)
    lock_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"), nullable=True)


class SyncOperation(UuidPrimaryKeyMixin, TimestampMixin, Base):
    """Operation ledger entry: every remote write is recorded before it is sent."""

    __tablename__ = "sync_operation"
    __table_args__ = (
        CheckConstraint(enum_check("action", SyncOperationAction), name="action_valid"),
        CheckConstraint(enum_check("status", SyncOperationStatus), name="status_valid"),
        CheckConstraint("action = 'REORDER' OR media_id IS NOT NULL", name="media_required"),
        UniqueConstraint("run_id", "action", "media_id", name="uq_sync_operation_run_action_media"),
        Index("sync_operation_run_idx", "run_id", "status"),
        Index("sync_operation_batch_idx", "batch_id"),
    )

    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sync_run.id", ondelete="CASCADE"), nullable=False
    )
    batch_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    media_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("media.id"), nullable=True)
    remote_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=SyncOperationStatus.PENDING.value
    )
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reconciled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    request_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    response: Mapped[Any] = mapped_column(JSON, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SyncRunEvent(BigIntPrimaryKeyMixin, Base):
    """Lightweight state-transition log that feeds the run timeline."""

    __tablename__ = "sync_run_event"
    __table_args__ = (Index("sync_run_event_run_idx", "run_id", "created_at"),)

    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sync_run.id", ondelete="CASCADE"), nullable=False
    )
    from_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    to_status: Mapped[str] = mapped_column(String(24), nullable=False)
    message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
