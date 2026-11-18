"""Persistent Celery task state (table ``job_execution``)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, CheckConstraint, DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UuidPrimaryKeyMixin, enum_check
from app.domain.enums import JobStatus


class JobExecution(UuidPrimaryKeyMixin, TimestampMixin, Base):
    """Status of an enqueued background task, exposed by the dashboard."""

    __tablename__ = "job_execution"
    __table_args__ = (
        CheckConstraint(enum_check("status", JobStatus), name="status_valid"),
        Index("job_execution_status_idx", "status", "created_at"),
    )

    task_id: Mapped[str | None] = mapped_column(String(120), nullable=True, unique=True)
    task_name: Mapped[str] = mapped_column(String(120), nullable=False)
    queue: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=JobStatus.QUEUED.value)
    payload: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)
    result: Mapped[Any] = mapped_column(JSON, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
