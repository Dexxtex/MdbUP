"""Append-only audit log writes.

Rows are only ever inserted: the PostgreSQL DDL enforces this with a trigger,
and this module never issues UPDATE/DELETE statements.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import redact_mapping
from app.db.models import AuditLog
from app.domain.enums import AuditActorType


def record(
    db: Session,
    *,
    action: str,
    entity_type: str,
    entity_id: str | uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    actor_type: AuditActorType | str = AuditActorType.SYSTEM,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
) -> AuditLog:
    """Append one audit entry with redacted payloads."""
    entry = AuditLog(
        actor_user_id=actor_user_id,
        actor_type=str(actor_type),
        action=action,
        entity_type=entity_type,
        entity_id=None if entity_id is None else str(entity_id),
        before=redact_mapping(before) if before else None,
        after=redact_mapping(after) if after else None,
        ip=ip,
        user_agent=user_agent,
        request_id=request_id,
    )
    db.add(entry)
    db.flush()
    return entry


def list_recent(db: Session, *, limit: int = 50) -> list[AuditLog]:
    return list(
        db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)).all()
    )
