"""Append-only audit log (table ``audit_log``).

The PostgreSQL DDL enforces append-only with a trigger; on SQLite the rule is
enforced by the application (``app/repositories/audit.py`` never updates or
deletes rows).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.db.base import Base, BigIntPrimaryKeyMixin, enum_check
from app.domain.enums import AuditActorType


class AuditLog(BigIntPrimaryKeyMixin, Base):
    """A security-relevant event. ``before``/``after`` payloads are redacted."""

    __tablename__ = "audit_log"
    __table_args__ = (
        CheckConstraint(enum_check("actor_type", AuditActorType), name="actor_type_valid"),
        Index("audit_entity_idx", "entity_type", "entity_id", "created_at"),
        Index("audit_created_idx", "created_at"),
    )

    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_user.id"), nullable=True
    )
    actor_type: Mapped[str] = mapped_column(String(16), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    before: Mapped[Any] = mapped_column(JSON, nullable=True)
    after: Mapped[Any] = mapped_column(JSON, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
