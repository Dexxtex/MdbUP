"""Preview/dry-run planning without remote writes.

A preview is persisted as a ``job_execution`` row (there is no preview table in
the data model): the request payload and the computed plan are stored there, so
``GET /previews/{id}`` survives the API process. The preview only issues GET
requests; it never adds, removes or reorders anything.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.time import utcnow
from app.db.models import Collection, CollectionSnapshot, JobExecution, SyncBinding
from app.domain.commands import PreviewRequest
from app.domain.enums import (
    JobStatus,
    SchedulePolicy,
    SyncMode,
)
from app.domain.errors import ConflictError, NotFoundError
from app.integrations.mdblist.client import MdbListError
from app.repositories import bindings as bindings_repo
from app.repositories import collections as collections_repo
from app.repositories import snapshots as snapshots_repo
from app.repositories import targets as targets_repo
from app.services import planning, reconciliation
from app.services import sync as sync_service

PREVIEW_TASK_NAME = "sync_preview"
PREVIEW_QUEUE = "previews"


def _resolve_snapshot(
    db: Session,
    collection: Collection,
    *,
    snapshot_id: uuid.UUID | None,
    mode: SyncMode,
) -> CollectionSnapshot:
    if snapshot_id is not None:
        snapshot = snapshots_repo.get_snapshot(db, snapshot_id)
        if snapshot is None or snapshot.collection_id != collection.id:
            raise ConflictError(
                "Snapshot non valido per questa collezione.",
                code="SNAPSHOT_INVALID",
                details={"snapshot_id": str(snapshot_id)},
            )
        return snapshot
    if collection.last_valid_snapshot_id is not None:
        snapshot = snapshots_repo.get_snapshot(db, collection.last_valid_snapshot_id)
        if snapshot is not None:
            return snapshot
    valid = snapshots_repo.latest_snapshots_for(db, [collection.id], valid_only=True)
    if collection.id in valid:
        return valid[collection.id]
    if mode is SyncMode.APPEND_ONLY:
        for candidate in snapshots_repo.list_snapshots(db, collection.id, limit=50):
            if candidate.status == "COMPLETE" and candidate.items_count > 0:
                return candidate
    raise ConflictError(
        "Nessuno snapshot valido disponibile: acquisire la collezione prima della preview.",
        code="SNAPSHOT_INVALID",
        details={"collection_id": str(collection.id)},
    )


def _transient_binding(
    db: Session,
    settings: Settings,
    collection: Collection,
    target_id: uuid.UUID | None,
    mode: SyncMode,
    thresholds: Any,
) -> SyncBinding:
    """A non-persisted binding carrying the preview policy."""
    existing = (
        bindings_repo.get_by_collection_target(db, collection_id=collection.id, target_id=target_id)
        if target_id is not None
        else None
    )
    return SyncBinding(
        collection_id=collection.id,
        target_id=target_id or uuid.uuid4(),
        media_type=collection.media_type,
        mode=mode.value,
        schedule_cron=existing.schedule_cron if existing else "",
        timezone=settings.app_timezone,
        is_enabled=False,
        policy_version=existing.policy_version if existing else planning.PLANNER_VERSION,
        max_removal_absolute=(
            thresholds.max_removal_abs
            if thresholds is not None
            else (existing.max_removal_absolute if existing else 50)
        ),
        max_removal_percent=(
            thresholds.max_removal_pct
            if thresholds is not None
            else (existing.max_removal_percent if existing else 10.0)
        ),
        max_addition_percent=(
            thresholds.max_addition_pct
            if thresholds is not None
            else (existing.max_addition_percent if existing else 50.0)
        ),
        preserve_order=existing.preserve_order if existing else False,
        reorder_enabled=existing.reorder_enabled if existing else True,
        require_manual_review=existing.require_manual_review if existing else True,
        schedule_policy=SchedulePolicy.AUTO_APPLY_IF_SAFE.value,
        auto_apply_max_removals=existing.auto_apply_max_removals if existing else 5,
        auto_apply_max_removal_ratio=(existing.auto_apply_max_removal_ratio if existing else 2.0),
        max_plan_age_minutes=existing.max_plan_age_minutes if existing else 60,
    )


def create_preview(
    db: Session,
    settings: Settings,
    payload: PreviewRequest,
) -> uuid.UUID:
    """Compute the plan and persist it as a preview job; returns the preview id."""
    collection = collections_repo.get_collection(db, payload.collection_id)
    if collection is None:
        raise NotFoundError(
            "Collezione non trovata.",
            details={"collection_id": str(payload.collection_id)},
        )
    mode = payload.mode or SyncMode.MIRROR
    snapshot = _resolve_snapshot(db, collection, snapshot_id=payload.snapshot_id, mode=mode)
    target = (
        targets_repo.get_target(db, payload.target_id) if payload.target_id is not None else None
    )
    if payload.target_id is not None and target is None:
        raise NotFoundError("Target non trovato.", details={"target_id": str(payload.target_id)})
    if target is not None and target.mediatype != collection.media_type:
        raise ConflictError(
            "La lista MDBList non è dello stesso tipo della collezione.",
            code="MEDIA_TYPE_MISMATCH",
        )

    client = sync_service.build_client(db, settings) if target is not None else None
    job = JobExecution(
        task_name=PREVIEW_TASK_NAME,
        queue=PREVIEW_QUEUE,
        status=JobStatus.RUNNING.value,
        payload={
            "collection_id": str(collection.id),
            "target_id": str(target.id) if target is not None else None,
            "snapshot_id": str(snapshot.id),
            "mode": mode.value,
        },
        started_at=utcnow(),
    )
    db.add(job)
    db.flush()
    try:
        binding = _transient_binding(
            db,
            settings,
            collection,
            target.id if target else None,
            mode,
            payload.thresholds,
        )
        source_items = sync_service.load_source_items(db, snapshot, collection)
        remote_items = []
        if client is not None and target is not None:
            try:
                remote = reconciliation.read_all_remote_items(client, target.remote_list_id)
                remote_items = list(remote.items)
            except (MdbListError, reconciliation.ReconciliationIncomplete) as exc:
                _fail_preview(db, job, snapshot, str(exc))
                return job.id

        plan = planning.plan_sync(
            mode=mode,
            snapshot=snapshot,
            source_items=source_items,
            remote_items=remote_items,
            binding=binding,
            policy_version=binding.policy_version or planning.PLANNER_VERSION,
        )
        state, blocked = _preview_state(plan, has_target=target is not None)
        job.result = {
            "state": state,
            "counts": {
                "to_add": len(plan.to_add),
                "to_remove": len(plan.to_remove),
                "unchanged": len(plan.unchanged),
                "unresolved": len(plan.unresolved),
                "unmapped_remote": len(plan.unmapped_remote),
                "remote_duplicates": len(plan.remote_duplicates),
            },
            "blocked": blocked,
            "sample": {
                "to_add": [key.label() for key in plan.to_add[: planning.SAMPLE_SIZE]],
                "to_remove": [key.label() for key in plan.to_remove[: planning.SAMPLE_SIZE]],
                "unresolved": list(plan.unresolved[: planning.SAMPLE_SIZE]),
                "unmapped_remote": list(plan.unmapped_remote[: planning.SAMPLE_SIZE]),
                "remote_duplicates": [
                    key.label() for key in plan.remote_duplicates[: planning.SAMPLE_SIZE]
                ],
            },
            "snapshot_id": str(snapshot.id),
            "snapshot_hash": plan.snapshot_hash,
            "plan_hash": plan.plan_hash if target is not None else None,
            "order_enforced": plan.order_enforced if target is not None else None,
            "generated_at": utcnow().isoformat(),
            "warnings": list(plan.warnings),
        }
        job.status = JobStatus.SUCCEEDED.value
        job.finished_at = utcnow()
        db.commit()
        return job.id
    finally:
        if client is not None:
            client.close()


def _fail_preview(
    db: Session,
    job: JobExecution,
    snapshot: CollectionSnapshot,
    error_message: str,
) -> None:
    job.status = JobStatus.FAILED.value
    job.finished_at = utcnow()
    job.error_code = "MDBLIST_REQUEST_FAILED"
    job.error_message = error_message[:1000]
    job.result = {
        "state": "FAILED",
        "counts": _empty_counts(),
        "blocked": None,
        "sample": {},
        "snapshot_id": str(snapshot.id),
        "snapshot_hash": snapshot.checksum,
        "plan_hash": None,
        "order_enforced": None,
        "generated_at": utcnow().isoformat(),
        "warnings": [],
        "error": error_message[:1000],
    }
    db.commit()


def _preview_state(
    plan: planning.SyncPlan, *, has_target: bool
) -> tuple[str, dict[str, Any] | None]:
    """A source-only preview cannot evaluate thresholds against a remote list."""
    if not has_target:
        if plan.blocked:
            return "BLOCKED", {
                "reason": plan.block_reason,
                "threshold": None,
                "observed": None,
            }
        return "READY", None
    if plan.blocked or plan.threshold.breached:
        return "BLOCKED", _blocked_payload(plan)
    return "READY", None


def get_preview(db: Session, preview_id: uuid.UUID) -> dict[str, Any]:
    job = db.get(JobExecution, preview_id)
    if job is None or job.task_name != PREVIEW_TASK_NAME:
        raise NotFoundError("Preview non trovata.", details={"preview_id": str(preview_id)})
    result = job.result or {}
    if job.status in {JobStatus.QUEUED.value, JobStatus.RUNNING.value}:
        state = "RUNNING"
    elif job.status == JobStatus.FAILED.value and result.get("state") != "FAILED":
        state = "FAILED"
    else:
        state = result.get("state", "FAILED")
    return {
        "id": job.id,
        "state": state,
        "counts": result.get("counts") or _empty_counts(),
        "blocked": result.get("blocked"),
        "sample": result.get("sample") or {},
        "snapshot_id": result.get("snapshot_id"),
        "snapshot_hash": result.get("snapshot_hash"),
        "plan_hash": result.get("plan_hash"),
        "order_enforced": result.get("order_enforced"),
        "generated_at": result.get("generated_at") or job.finished_at,
        "warnings": result.get("warnings") or [],
        "error": result.get("error") or job.error_message,
    }


def _empty_counts() -> dict[str, int]:
    return {
        "to_add": 0,
        "to_remove": 0,
        "unchanged": 0,
        "unresolved": 0,
        "unmapped_remote": 0,
        "remote_duplicates": 0,
    }


def _blocked_payload(plan: planning.SyncPlan) -> dict[str, Any] | None:
    if plan.blocked:
        return {"reason": plan.block_reason, "threshold": None, "observed": None}
    if not plan.threshold.breached:
        return None
    reason = plan.threshold.primary_reason or "THRESHOLD_EXCEEDED"
    if reason == "REMOVAL_ABSOLUTE_EXCEEDED":
        threshold = float(plan.threshold.max_removal_absolute)
        observed = float(plan.threshold.observed_removals)
    elif reason == "REMOVAL_PERCENT_EXCEEDED":
        threshold = plan.threshold.max_removal_percent
        observed = plan.threshold.removal_ratio * 100
    else:
        threshold = plan.threshold.max_addition_percent
        observed = plan.threshold.addition_ratio * 100
    return {
        "reason": reason,
        "threshold": round(threshold, 2),
        "observed": round(observed, 2),
    }
