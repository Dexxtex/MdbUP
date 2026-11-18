"""Notification channels (table ``notification_channel``).

The transport secret (webhook URL or Telegram bot token) is encrypted with the
same AES-256-GCM machinery as integration credentials; it is never returned by
the API. Non-secret routing data (Telegram ``chat_id``, event subscriptions)
lives in JSON columns.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    LargeBinary,
    SmallInteger,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UuidPrimaryKeyMixin, enum_check
from app.domain.enums import NotificationChannelKind


class NotificationChannel(UuidPrimaryKeyMixin, TimestampMixin, Base):
    """A webhook/Telegram/Discord destination with per-event subscriptions."""

    __tablename__ = "notification_channel"
    __table_args__ = (
        CheckConstraint(enum_check("kind", NotificationChannelKind), name="kind_valid"),
        CheckConstraint(
            "last_status IS NULL OR last_status IN ('SENT', 'FAILED')",
            name="last_status_valid",
        ),
        UniqueConstraint("name", name="uq_notification_channel_name"),
        Index("notification_retry_idx", "last_status", "next_retry_at"),
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    events: Mapped[Any] = mapped_column(JSON, nullable=False, default=list)
    config: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)
    secret_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    secret_nonce: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    secret_algorithm: Mapped[str] = mapped_column(String(32), nullable=False, default="AES-256-GCM")
    secret_key_version: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    secret_masked_hint: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    # Retry state: ``retry_count`` counts failed deliveries, ``next_retry_at`` is
    # when the maintenance task may resend (NULL once the budget is exhausted).
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Durable copy of the last delivery so a failure survives a restart.
    # ``last_payload`` holds ``{"message": str, "payload": dict}``.
    last_event: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_payload: Mapped[Any | None] = mapped_column(JSON, nullable=True)
