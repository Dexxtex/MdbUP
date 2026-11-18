"""Source healthcheck history (table ``source_healthcheck``)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.db.base import Base, BigIntPrimaryKeyMixin


class SourceHealthcheck(BigIntPrimaryKeyMixin, Base):
    """One connectivity probe result for a source."""

    __tablename__ = "source_healthcheck"
    __table_args__ = (Index("source_healthcheck_source_idx", "source_id", "checked_at"),)

    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    details: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
