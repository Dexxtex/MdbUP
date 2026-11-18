"""Sync run and operation ledger persistence.

Every remote write is recorded as a ``SyncOperation`` *before* it is sent, so a
crash or a timeout can always be reconciled by reading the remote list. State
transitions are validated here and mirrored into ``sync_run_event`` for the UI
timeline.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.db.models import Collection, SyncBinding, SyncOperation, SyncRun, SyncRunEvent
from app.domain.enums import (
    ACTIVE_RUN_STATUSES,
    TERMINAL_RUN_STATUSES,
    SyncOperationStatus,
    SyncRunStatus,
)

ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    SyncRunStatus.PENDING.value: frozenset(
        {
            SyncRunStatus.PREFLIGHT.value,
            SyncRunStatus.BLOCKED.value,
            SyncRunStatus.FAILED.value,
            SyncRunStatus.CANCELLED.value,
        }
    ),
    SyncRunStatus.PREFLIGHT.value: frozenset(
        {
            SyncRunStatus.PLANNING.value,
            SyncRunStatus.BLOCKED.value,
            SyncRunStatus.FAILED.value,
            SyncRunStatus.CANCELLED.value,
        }
    ),
    SyncRunStatus.PLANNING.value: frozenset(
        {
            SyncRunStatus.AWAITING_APPROVAL.value,
            SyncRunStatus.APPLYING.value,
            SyncRunStatus.VERIFYING.value,
            SyncRunStatus.SUCCEEDED.value,
            SyncRunStatus.BLOCKED.value,
            SyncRunStatus.FAILED.value,
            SyncRunStatus.CANCELLED.value,
        }
    ),
    SyncRunStatus.AWAITING_APPROVAL.value: frozenset(
        {
            SyncRunStatus.PLANNING.value,
            SyncRunStatus.APPLYING.value,
            SyncRunStatus.BLOCKED.value,
            SyncRunStatus.FAILED.value,
            SyncRunStatus.CANCELLED.value,
        }
    ),
    SyncRunStatus.APPLYING.value: frozenset(
        {
            SyncRunStatus.VERIFYING.value,
            SyncRunStatus.PARTIAL.value,
            SyncRunStatus.FAILED.value,
            SyncRunStatus.CANCELLED.value,
        }
    ),
    SyncRunStatus.VERIFYING.value: frozenset(
        {
            SyncRunStatus.SUCCEEDED.value,
            SyncRunStatus.PARTIAL.value,
            SyncRunStatus.FAILED.value,
            SyncRunStatus.CANCELLED.value,
        }
    ),
    SyncRunStatus.PARTIAL.value: frozenset(
        {
            SyncRunStatus.VERIFYING.value,
            SyncRunStatus.SUCCEEDED.value,
            SyncRunStatus.FAILED.value,
        }
    ),
    SyncRunStatus.FAILED.value: frozenset({SyncRunStatus.VERIFYING.value}),
    SyncRunStatus.SUCCEEDED.value: frozenset(),
    SyncRunStatus.BLOCKED.value: frozenset(),
    SyncRunStatus.CANCELLED.value: frozenset(),
}


class InvalidTransitionError(RuntimeError):
    """The requested run status transition is not part of the state machine."""


def create_run(
    db: Session,
    *,
    binding_id: uuid.UUID,
    target_id: uuid.UUID,
    media_type: str,
    snapshot_id: uuid.UUID,
    mode: str,
    trigger_type: str,
    is_dry_run: bool,
    requested_by: uuid.UUID | None = None,
    parent_run_id: uuid.UUID | None = None,
    summary: dict[str, Any] | None = None,
) -> SyncRun:
    run = SyncRun(
        binding_id=binding_id,
        target_id=target_id,
        media_type=media_type,
        snapshot_id=snapshot_id,
        mode=mode,
        status=SyncRunStatus.PENDING.value,
        is_dry_run=is_dry_run,
        trigger_type=trigger_type,
        requested_by=requested_by,
        parent_run_id=parent_run_id,
        summary=summary or {},
    )
    db.add(run)
    db.flush()
    add_event(db, run, from_status=None, to_status=run.status, message="run creato")
    return run


def get_run(db: Session, run_id: uuid.UUID) -> SyncRun | None:
    return db.get(SyncRun, run_id)


def list_runs(
    db: Session,
    *,
    binding_id: uuid.UUID | None = None,
    target_id: uuid.UUID | None = None,
    status: str | None = None,
    provider_id: uuid.UUID | None = None,
    media_type: str | None = None,
    limit: int = 25,
    offset: int = 0,
) -> list[SyncRun]:
    stmt = select(SyncRun)
    if provider_id is not None or media_type is not None:
        stmt = stmt.join(SyncBinding, SyncBinding.id == SyncRun.binding_id).join(
            Collection, Collection.id == SyncBinding.collection_id
        )
    if binding_id is not None:
        stmt = stmt.where(SyncRun.binding_id == binding_id)
    if target_id is not None:
        stmt = stmt.where(SyncRun.target_id == target_id)
    if status is not None:
        stmt = stmt.where(SyncRun.status == status)
    if provider_id is not None:
        stmt = stmt.where(Collection.provider_id == provider_id)
    if media_type is not None:
        stmt = stmt.where(SyncRun.media_type == media_type)
    stmt = stmt.order_by(SyncRun.created_at.desc()).limit(limit).offset(offset)
    return list(db.scalars(stmt).all())


def count_runs(
    db: Session,
    *,
    binding_id: uuid.UUID | None = None,
    target_id: uuid.UUID | None = None,
    status: str | None = None,
    provider_id: uuid.UUID | None = None,
    media_type: str | None = None,
) -> int:
    stmt = select(func.count()).select_from(SyncRun)
    if provider_id is not None or media_type is not None:
        stmt = stmt.join(SyncBinding, SyncBinding.id == SyncRun.binding_id).join(
            Collection, Collection.id == SyncBinding.collection_id
        )
    if binding_id is not None:
        stmt = stmt.where(SyncRun.binding_id == binding_id)
    if target_id is not None:
        stmt = stmt.where(SyncRun.target_id == target_id)
    if status is not None:
        stmt = stmt.where(SyncRun.status == status)
    if provider_id is not None:
        stmt = stmt.where(Collection.provider_id == provider_id)
    if media_type is not None:
        stmt = stmt.where(SyncRun.media_type == media_type)
    return int(db.scalar(stmt) or 0)


def get_active_run_for_binding(db: Session, binding_id: uuid.UUID) -> SyncRun | None:
    statuses = [status.value for status in ACTIVE_RUN_STATUSES]
    return db.scalar(
        select(SyncRun)
        .where(SyncRun.binding_id == binding_id, SyncRun.status.in_(statuses))
        .order_by(SyncRun.created_at.desc())
    )


def get_active_run_for_target(db: Session, target_id: uuid.UUID) -> SyncRun | None:
    statuses = [status.value for status in ACTIVE_RUN_STATUSES]
    return db.scalar(
        select(SyncRun)
        .where(SyncRun.target_id == target_id, SyncRun.status.in_(statuses))
        .order_by(SyncRun.created_at.desc())
    )


def add_event(
    db: Session,
    run: SyncRun,
    *,
    from_status: str | None,
    to_status: str,
    message: str | None = None,
) -> SyncRunEvent:
    event = SyncRunEvent(
        run_id=run.id,
        from_status=from_status,
        to_status=to_status,
        message=message,
    )
    db.add(event)
    db.flush()
    return event


def transition_run(
    db: Session,
    run: SyncRun,
    to_status: SyncRunStatus | str,
    *,
    message: str | None = None,
    force: bool = False,
) -> SyncRun:
    """Move the run to ``to_status`` and record the transition."""
    target = str(to_status)
    current = run.status
    if current == target:
        return run
    if not force and target not in ALLOWED_TRANSITIONS.get(current, frozenset()):
        raise InvalidTransitionError(f"Transizione non valida: {current} -> {target}")
    if current == SyncRunStatus.PENDING.value and run.started_at is None:
        run.started_at = utcnow()
    run.status = target
    if target in {status.value for status in TERMINAL_RUN_STATUSES}:
        run.finished_at = utcnow()
    db.flush()
    add_event(db, run, from_status=current, to_status=target, message=message)
    return run


def set_plan(
    db: Session,
    run: SyncRun,
    *,
    plan_hash: str,
    snapshot_hash: str,
    source_item_count: int,
    remote_item_count: int,
    to_add_count: int,
    to_remove_count: int,
    threshold_breached: bool,
    requires_approval: bool,
    warnings: Sequence[str],
    summary: dict[str, Any],
) -> None:
    run.plan_hash = plan_hash
    run.snapshot_hash = snapshot_hash
    run.source_item_count = source_item_count
    run.remote_item_count = remote_item_count
    run.to_add_count = to_add_count
    run.to_remove_count = to_remove_count
    run.threshold_breached = threshold_breached
    run.requires_approval = requires_approval
    run.warnings = list(warnings)
    run.summary = summary
    db.flush()


def set_counters(
    db: Session,
    run: SyncRun,
    *,
    added: int,
    removed: int,
    failed: int,
    uncertain: int,
) -> None:
    run.added_count = added
    run.removed_count = removed
    run.failed_count = failed
    run.uncertain_count = uncertain
    db.flush()


def finish_run(
    db: Session,
    run: SyncRun,
    status: SyncRunStatus,
    *,
    abort_reason: str | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
    order_enforced: bool = False,
    warnings: Sequence[str] | None = None,
) -> SyncRun:
    run.abort_reason = abort_reason
    run.error_code = error_code
    run.error_message = error_message[:1000] if error_message else None
    run.order_enforced = order_enforced
    if warnings is not None:
        run.warnings = list(warnings)
    transition_run(db, run, status, message=abort_reason or error_code)
    return run


def create_operation(
    db: Session,
    *,
    run_id: uuid.UUID,
    action: str,
    media_id: uuid.UUID | None,
    remote_id: str | None,
    idempotency_key: str,
    max_attempts: int = 5,
) -> SyncOperation:
    """Insert the ledger row once; the unique key makes retries idempotent."""
    existing = db.scalar(
        select(SyncOperation).where(SyncOperation.idempotency_key == idempotency_key)
    )
    if existing is not None:
        return existing
    operation = SyncOperation(
        run_id=run_id,
        action=action,
        media_id=media_id,
        remote_id=remote_id,
        idempotency_key=idempotency_key,
        status=SyncOperationStatus.PENDING.value,
        max_attempts=max_attempts,
    )
    db.add(operation)
    db.flush()
    return operation


def get_operation(db: Session, operation_id: uuid.UUID) -> SyncOperation | None:
    return db.get(SyncOperation, operation_id)


def list_operations(
    db: Session,
    run_id: uuid.UUID,
    *,
    status: str | None = None,
    action: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[SyncOperation]:
    stmt = select(SyncOperation).where(SyncOperation.run_id == run_id)
    if status is not None:
        stmt = stmt.where(SyncOperation.status == status)
    if action is not None:
        stmt = stmt.where(SyncOperation.action == action)
    stmt = stmt.order_by(SyncOperation.created_at, SyncOperation.id).limit(limit).offset(offset)
    return list(db.scalars(stmt).all())


def count_operations(
    db: Session,
    run_id: uuid.UUID,
    *,
    status: str | None = None,
    action: str | None = None,
) -> int:
    stmt = select(func.count()).select_from(SyncOperation).where(SyncOperation.run_id == run_id)
    if status is not None:
        stmt = stmt.where(SyncOperation.status == status)
    if action is not None:
        stmt = stmt.where(SyncOperation.action == action)
    return int(db.scalar(stmt) or 0)


def operation_counts(db: Session, run_id: uuid.UUID) -> dict[str, int]:
    stmt = (
        select(SyncOperation.status, func.count())
        .where(SyncOperation.run_id == run_id)
        .group_by(SyncOperation.status)
    )
    return {status: int(total) for status, total in db.execute(stmt).all()}


def set_operation_status(
    db: Session,
    operation: SyncOperation,
    status: SyncOperationStatus | str,
    *,
    error_code: str | None = None,
    error_message: str | None = None,
    http_status: int | None = None,
    duration_ms: int | None = None,
    response: dict[str, Any] | None = None,
    next_retry_at: datetime | None = None,
    reconciled: bool = False,
) -> SyncOperation:
    operation.status = str(status)
    operation.error_code = error_code
    operation.error_message = error_message[:1000] if error_message else None
    if http_status is not None:
        operation.http_status = http_status
    if duration_ms is not None:
        operation.duration_ms = duration_ms
    if response is not None:
        operation.response = response
    if next_retry_at is not None:
        operation.next_retry_at = next_retry_at
    if reconciled:
        operation.reconciled_at = utcnow()
    if str(status) in {
        SyncOperationStatus.SUCCEEDED.value,
        SyncOperationStatus.FAILED.value,
        SyncOperationStatus.SKIPPED.value,
    }:
        operation.finished_at = utcnow()
    db.flush()
    return operation


def recent(db: Session, *, limit: int = 5) -> list[SyncRun]:
    return list(db.scalars(select(SyncRun).order_by(SyncRun.created_at.desc()).limit(limit)).all())


def count_operations_with_error(db: Session, run_id: uuid.UUID, error_code: str) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(SyncOperation)
            .where(
                SyncOperation.run_id == run_id,
                SyncOperation.error_code == error_code,
            )
        )
        or 0
    )
