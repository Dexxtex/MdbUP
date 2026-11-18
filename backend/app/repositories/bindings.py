"""Sync binding persistence and the scheduler's due-binding query."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.db.models import SyncBinding


def get_binding(db: Session, binding_id: uuid.UUID) -> SyncBinding | None:
    return db.get(SyncBinding, binding_id)


def get_by_collection_target(
    db: Session, *, collection_id: uuid.UUID, target_id: uuid.UUID
) -> SyncBinding | None:
    return db.scalar(
        select(SyncBinding).where(
            SyncBinding.collection_id == collection_id,
            SyncBinding.target_id == target_id,
        )
    )


def list_bindings(
    db: Session,
    *,
    collection_id: uuid.UUID | None = None,
    target_id: uuid.UUID | None = None,
    enabled: bool | None = None,
) -> list[SyncBinding]:
    stmt = select(SyncBinding)
    if collection_id is not None:
        stmt = stmt.where(SyncBinding.collection_id == collection_id)
    if target_id is not None:
        stmt = stmt.where(SyncBinding.target_id == target_id)
    if enabled is not None:
        stmt = stmt.where(SyncBinding.is_enabled.is_(enabled))
    return list(db.scalars(stmt.order_by(SyncBinding.created_at.desc())).all())


def create_binding(
    db: Session,
    *,
    collection_id: uuid.UUID,
    target_id: uuid.UUID,
    media_type: str,
    mode: str,
    schedule_cron: str,
    schedule_interval_hours: int | None = None,
    timezone: str,
    is_enabled: bool,
    policy_version: str | None,
    policy_accepted_at: datetime | None,
    policy_accepted_by: uuid.UUID | None,
    max_removal_absolute: int,
    max_removal_percent: float,
    max_addition_percent: float,
    preserve_order: bool,
    reorder_enabled: bool,
    require_manual_review: bool,
    schedule_policy: str,
    auto_apply_max_removals: int,
    auto_apply_max_removal_ratio: float,
    max_plan_age_minutes: int,
    next_run_at: datetime | None,
) -> SyncBinding:
    binding = SyncBinding(
        collection_id=collection_id,
        target_id=target_id,
        media_type=media_type,
        mode=mode,
        schedule_cron=schedule_cron,
        schedule_interval_hours=schedule_interval_hours,
        timezone=timezone,
        is_enabled=is_enabled,
        policy_version=policy_version,
        policy_accepted_at=policy_accepted_at,
        policy_accepted_by=policy_accepted_by,
        max_removal_absolute=max_removal_absolute,
        max_removal_percent=max_removal_percent,
        max_addition_percent=max_addition_percent,
        preserve_order=preserve_order,
        reorder_enabled=reorder_enabled,
        require_manual_review=require_manual_review,
        schedule_policy=schedule_policy,
        auto_apply_max_removals=auto_apply_max_removals,
        auto_apply_max_removal_ratio=auto_apply_max_removal_ratio,
        max_plan_age_minutes=max_plan_age_minutes,
        next_run_at=next_run_at,
    )
    db.add(binding)
    db.flush()
    return binding


def set_next_run_at(db: Session, binding: SyncBinding, moment: datetime | None) -> None:
    binding.next_run_at = moment
    db.flush()


def set_last_run(db: Session, binding: SyncBinding, run_id: uuid.UUID) -> None:
    binding.last_run_id = run_id
    db.flush()


def list_due_bindings(
    db: Session, *, now: datetime | None = None, limit: int = 100
) -> list[SyncBinding]:
    """Enabled bindings whose ``next_run_at`` is due (or never computed)."""
    moment = now or utcnow()
    stmt = (
        select(SyncBinding)
        .where(
            SyncBinding.is_enabled.is_(True),
            or_(
                SyncBinding.schedule_cron != "",
                SyncBinding.schedule_interval_hours.is_not(None),
            ),
            SyncBinding.next_run_at.is_(None) | (SyncBinding.next_run_at <= moment),
        )
        .order_by(SyncBinding.next_run_at)
        .limit(limit)
    )
    return list(db.scalars(stmt).all())
