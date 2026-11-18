"""Sync run use cases: start, approve, cancel, reconcile and resume."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.locks import build_dispatch_lock
from app.core.time import ensure_utc, utcnow
from app.db.models import (
    Collection,
    CollectionSnapshot,
    JobExecution,
    MdblistTarget,
    SyncBinding,
    SyncOperation,
    SyncRun,
)
from app.domain.commands import ApproveRunIn, StartRunIn
from app.domain.enums import (
    TERMINAL_RUN_STATUSES,
    SyncMode,
    SyncOperationStatus,
    SyncRunStatus,
)
from app.domain.errors import ConflictError, NotFoundError, ServiceUnavailableError
from app.jobs import tasks
from app.repositories import bindings as bindings_repo
from app.repositories import collections as collections_repo
from app.repositories import media as media_repo
from app.repositories import providers as providers_repo
from app.repositories import runs as runs_repo
from app.repositories import snapshots as snapshots_repo
from app.repositories import targets as targets_repo
from app.services import credentials as credentials_service
from app.services.collections import is_justwatch_collection
from app.services.credentials import CredentialKind

TERMINAL_STATUS_VALUES = {status.value for status in TERMINAL_RUN_STATUSES}


@dataclass(frozen=True)
class RunCounters:
    planned: int
    applied: int
    skipped: int
    not_found: int
    failed: int
    uncertain: int


@dataclass(frozen=True)
class RunView:
    id: uuid.UUID
    binding_id: uuid.UUID
    target_id: uuid.UUID
    status: str
    mode: str
    is_dry_run: bool
    trigger: str
    snapshot_id: uuid.UUID
    plan_hash: str | None
    snapshot_hash: str | None
    order_enforced: bool
    warnings: list[str]
    counters: RunCounters
    source_item_count: int
    remote_item_count: int
    to_add_count: int
    to_remove_count: int
    added_count: int
    removed_count: int
    failed_count: int
    uncertain_count: int
    threshold_breached: bool
    requires_approval: bool
    approved_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    abort_reason: str | None
    error_code: str | None
    error_message: str | None
    summary: dict[str, Any]
    collection_name: str | None
    provider_name: str | None
    target_name: str | None
    idempotency_key: str | None
    reconcile_required: bool
    parent_run_id: uuid.UUID | None
    created_at: datetime


@dataclass(frozen=True)
class OperationView:
    id: uuid.UUID
    run_id: uuid.UUID
    action: str
    media_id: uuid.UUID | None
    media: dict[str, Any] | None
    status: str
    attempt: int
    error: str | None
    error_code: str | None
    remote_id: str | None
    batch_id: uuid.UUID | None
    http_status: int | None
    updated_at: datetime | None


def run_view(
    db: Session,
    run: SyncRun,
    *,
    collection: Collection | None = None,
    target: MdblistTarget | None = None,
    provider_name: str | None = None,
) -> RunView:
    counts = runs_repo.operation_counts(db, run.id)
    skipped = counts.get(SyncOperationStatus.SKIPPED.value, 0)
    not_found = runs_repo.count_operations_with_error(db, run.id, "MDBLIST_NOT_FOUND")
    summary = run.summary or {}
    return RunView(
        id=run.id,
        binding_id=run.binding_id,
        target_id=run.target_id,
        status=run.status,
        mode=run.mode,
        is_dry_run=bool(run.is_dry_run),
        trigger=run.trigger_type,
        snapshot_id=run.snapshot_id,
        plan_hash=run.plan_hash,
        snapshot_hash=run.snapshot_hash,
        order_enforced=bool(run.order_enforced),
        warnings=list(run.warnings or []),
        counters=RunCounters(
            planned=run.to_add_count + run.to_remove_count,
            applied=run.added_count + run.removed_count,
            skipped=skipped,
            not_found=not_found,
            failed=run.failed_count,
            uncertain=run.uncertain_count,
        ),
        source_item_count=run.source_item_count,
        remote_item_count=run.remote_item_count,
        to_add_count=run.to_add_count,
        to_remove_count=run.to_remove_count,
        added_count=run.added_count,
        removed_count=run.removed_count,
        failed_count=run.failed_count,
        uncertain_count=run.uncertain_count,
        threshold_breached=bool(run.threshold_breached),
        requires_approval=bool(run.requires_approval),
        approved_at=run.approved_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        abort_reason=run.abort_reason,
        error_code=run.error_code,
        error_message=run.error_message,
        summary=summary,
        collection_name=collection.name if collection is not None else None,
        provider_name=provider_name,
        target_name=target.name if target is not None else None,
        idempotency_key=summary.get("idempotency_key"),
        reconcile_required=run.status
        in {
            SyncRunStatus.PARTIAL.value,
            SyncRunStatus.FAILED.value,
        }
        and run.uncertain_count > 0,
        parent_run_id=run.parent_run_id,
        created_at=run.created_at,
    )


def list_runs(
    db: Session,
    *,
    binding_id: uuid.UUID | None = None,
    target_id: uuid.UUID | None = None,
    status: str | None = None,
    provider_id: uuid.UUID | None = None,
    media_type: str | None = None,
    page: int = 1,
    page_size: int = 25,
) -> tuple[list[RunView], int]:
    rows = runs_repo.list_runs(
        db,
        binding_id=binding_id,
        target_id=target_id,
        status=status,
        provider_id=provider_id,
        media_type=media_type,
        limit=page_size,
        offset=(page - 1) * page_size,
    )
    total = runs_repo.count_runs(
        db,
        binding_id=binding_id,
        target_id=target_id,
        status=status,
        provider_id=provider_id,
        media_type=media_type,
    )
    collections = {row.id: row for row in collections_repo.list_collections(db)}
    targets = {row.id: row for row in targets_repo.list_targets(db)}
    bindings = {row.id: row for row in bindings_repo.list_bindings(db)}
    providers = {row.id: row for row in providers_repo.list_providers(db)}
    views = []
    for row in rows:
        binding = bindings.get(row.binding_id)
        collection = collections.get(binding.collection_id) if binding else None
        provider = providers.get(collection.provider_id) if collection else None
        views.append(
            run_view(
                db,
                row,
                collection=collection,
                target=targets.get(row.target_id),
                provider_name=provider.name if provider is not None else None,
            )
        )
    return views, total


def get_run(db: Session, run_id: uuid.UUID) -> RunView:
    run = runs_repo.get_run(db, run_id)
    if run is None:
        raise NotFoundError("Run non trovato.", details={"run_id": str(run_id)})
    binding = bindings_repo.get_binding(db, run.binding_id)
    collection = collections_repo.get_collection(db, binding.collection_id) if binding else None
    provider = providers_repo.get_provider(db, collection.provider_id) if collection else None
    return run_view(
        db,
        run,
        collection=collection,
        target=targets_repo.get_target(db, run.target_id),
        provider_name=provider.name if provider is not None else None,
    )


def list_operations(
    db: Session,
    run_id: uuid.UUID,
    *,
    status: str | None = None,
    action: str | None = None,
    page: int = 1,
    page_size: int = 100,
) -> tuple[list[OperationView], int]:
    if runs_repo.get_run(db, run_id) is None:
        raise NotFoundError("Run non trovato.", details={"run_id": str(run_id)})
    rows = runs_repo.list_operations(
        db,
        run_id,
        status=status,
        action=action,
        limit=page_size,
        offset=(page - 1) * page_size,
    )
    total = runs_repo.count_operations(db, run_id, status=status, action=action)
    return [_operation_view(db, row) for row in rows], total


def _operation_view(db: Session, operation: SyncOperation) -> OperationView:
    media = media_repo.find_by_id(db, operation.media_id) if operation.media_id else None
    return OperationView(
        id=operation.id,
        run_id=operation.run_id,
        action=operation.action,
        media_id=operation.media_id,
        media=(
            {
                "title": media.title,
                "year": media.release_year,
                "media_type": media.media_type,
                "tmdb_id": media.tmdb_id,
                "imdb_id": media.imdb_id,
            }
            if media is not None
            else None
        ),
        status=operation.status,
        attempt=operation.attempt,
        error=operation.error_message,
        error_code=operation.error_code,
        remote_id=operation.remote_id,
        batch_id=operation.batch_id,
        http_status=operation.http_status,
        updated_at=operation.updated_at,
    )


def start_run(
    db: Session,
    settings: Settings,
    binding_id: uuid.UUID,
    payload: StartRunIn,
    *,
    actor_user_id: uuid.UUID | None = None,
) -> tuple[SyncRun, JobExecution]:
    binding = bindings_repo.get_binding(db, binding_id)
    if binding is None:
        raise NotFoundError("Binding non trovato.", details={"binding_id": str(binding_id)})
    # Serialise the active-run check + row creation with the scheduler. The
    # executor's TargetLock still protects the actual remote writes.
    dispatch_lock = build_dispatch_lock(settings.redis_url)
    token = dispatch_lock.acquire(f"target:{binding.target_id}")
    if token is None:
        raise ConflictError(
            "Un run è già in preparazione per questa lista MDBList.",
            code="RUN_IN_PROGRESS",
            details={"target_id": str(binding.target_id)},
        )
    try:
        return _start_run_locked(db, settings, binding, payload, actor_user_id)
    finally:
        dispatch_lock.release(f"target:{binding.target_id}", token)


def _start_run_locked(
    db: Session,
    settings: Settings,
    binding: SyncBinding,
    payload: StartRunIn,
    actor_user_id: uuid.UUID | None,
) -> tuple[SyncRun, JobExecution]:
    # Dry-run also reads the remote list, so the credential is always required.
    credentials_service.get_secret(db, settings, CredentialKind.MDBLIST)
    if not payload.dry_run:
        if not binding.is_enabled:
            raise ConflictError(
                "Il binding è disabilitato: abilitarlo per eseguire una sync reale.",
                code="BINDING_DISABLED",
            )
        if binding.policy_accepted_at is None:
            raise ConflictError(
                "Policy non accettata: abilitare il binding prima di sincronizzare.",
                code="POLICY_NOT_ACCEPTED",
            )
    active = runs_repo.get_active_run_for_binding(db, binding.id)
    if active is not None:
        if (
            payload.idempotency_key
            and (active.summary or {}).get("idempotency_key") == payload.idempotency_key
        ):
            job = tasks.record_control_job(
                db,
                task_name="sync_run_idempotent",
                payload={"run_id": str(active.id)},
                result={"run_id": str(active.id), "status": active.status},
            )
            return active, job
        raise ConflictError(
            "Un run è già attivo per questo binding.",
            code="RUN_IN_PROGRESS",
            details={"run_id": str(active.id)},
        )
    active_target = runs_repo.get_active_run_for_target(db, binding.target_id)
    if active_target is not None:
        raise ConflictError(
            "Un run è già attivo su questa lista MDBList.",
            code="RUN_IN_PROGRESS",
            details={"run_id": str(active_target.id)},
        )
    collection = collections_repo.get_collection(db, binding.collection_id)
    if collection is None:
        raise NotFoundError("Collezione del binding non trovata.")
    # Guardrail: an aggregator binding cannot write before a dry-run proved the
    # plan is viable. A dry-run itself stays always possible.
    if (
        not payload.dry_run
        and is_justwatch_collection(db, collection)
        and not runs_repo.has_succeeded_dry_run(db, binding.id)
    ):
        raise ConflictError(
            "Eseguire prima un dry-run completato con successo per questo binding.",
            code="DRY_RUN_REQUIRED",
            details={"binding_id": str(binding.id)},
        )
    snapshot = _resolve_snapshot(
        db,
        collection,
        snapshot_id=payload.snapshot_id,
        mode=SyncMode(binding.mode),
    )
    run = runs_repo.create_run(
        db,
        binding_id=binding.id,
        target_id=binding.target_id,
        media_type=binding.media_type,
        snapshot_id=snapshot.id,
        mode=binding.mode,
        trigger_type="MANUAL",
        is_dry_run=payload.dry_run,
        requested_by=actor_user_id,
        summary={"idempotency_key": payload.idempotency_key},
    )
    bindings_repo.set_last_run(db, binding, run.id)
    db.commit()
    try:
        job = tasks.enqueue_sync_run(db, settings, run.id)
    except ServiceUnavailableError:
        runs_repo.finish_run(
            db,
            run,
            SyncRunStatus.FAILED,
            error_code="CELERY_UNAVAILABLE",
            error_message="Coda Celery non raggiungibile.",
        )
        db.commit()
        raise
    db.refresh(run)
    return run, job


def approve_run(
    db: Session,
    settings: Settings,
    run_id: uuid.UUID,
    payload: ApproveRunIn,
    *,
    actor_user_id: uuid.UUID | None = None,
) -> JobExecution:
    run = runs_repo.get_run(db, run_id)
    if run is None:
        raise NotFoundError("Run non trovato.", details={"run_id": str(run_id)})
    if run.status != SyncRunStatus.AWAITING_APPROVAL.value:
        raise ConflictError(
            "Il run non è in attesa di approvazione.",
            code="RUN_NOT_AWAITING_APPROVAL",
            details={"status": run.status},
        )
    if not run.plan_hash or payload.plan_hash != run.plan_hash:
        raise ConflictError(
            "Il piano è cambiato: ricaricare la preview e approvare il nuovo plan_hash.",
            code="STALE_PLAN",
        )
    binding = bindings_repo.get_binding(db, run.binding_id)
    if binding is not None:
        planned_at = ensure_utc(run.updated_at)
        expires_at = planned_at + timedelta(minutes=binding.max_plan_age_minutes)
        if utcnow() > expires_at:
            raise ConflictError(
                "Il piano è scaduto: ricalcolare la preview.",
                code="STALE_PLAN",
            )
    run.approved_at = utcnow()
    run.approved_by = actor_user_id
    run.requires_approval = False
    runs_repo.add_event(
        db,
        run,
        from_status=run.status,
        to_status=run.status,
        message=payload.note or "piano approvato",
    )
    db.commit()
    return tasks.enqueue_sync_run(db, settings, run.id)


def cancel_run(db: Session, settings: Settings, run_id: uuid.UUID) -> JobExecution:
    run = runs_repo.get_run(db, run_id)
    if run is None:
        raise NotFoundError("Run non trovato.", details={"run_id": str(run_id)})
    if run.status in TERMINAL_STATUS_VALUES:
        raise ConflictError(
            "Il run è già concluso.", code="RUN_TERMINAL", details={"status": run.status}
        )
    if run.status in {SyncRunStatus.APPLYING.value, SyncRunStatus.VERIFYING.value}:
        raise ConflictError(
            "Il run sta applicando o verificando: usare la riconciliazione, non l'annullamento.",
            code="RUN_IN_PROGRESS",
            details={"status": run.status},
        )
    runs_repo.finish_run(db, run, SyncRunStatus.CANCELLED, abort_reason="CANCELLED_BY_USER")
    db.commit()
    return tasks.record_control_job(
        db,
        task_name="cancel_sync_run",
        payload={"run_id": str(run.id)},
        result={"run_id": str(run.id), "status": run.status},
    )


def reconcile_run(db: Session, settings: Settings, run_id: uuid.UUID) -> JobExecution:
    run = runs_repo.get_run(db, run_id)
    if run is None:
        raise NotFoundError("Run non trovato.", details={"run_id": str(run_id)})
    if run.status not in {SyncRunStatus.PARTIAL.value, SyncRunStatus.FAILED.value}:
        raise ConflictError(
            "Il run non è riconciliabile.", code="RUN_NOT_UNCERTAIN", details={"status": run.status}
        )
    if run.uncertain_count == 0 and run.failed_count == 0:
        raise ConflictError("Nessuna operazione incerta da riconciliare.", code="RUN_NOT_UNCERTAIN")
    return tasks.enqueue_sync_run(db, settings, run.id, reconcile=True)


def resume_run(db: Session, settings: Settings, run_id: uuid.UUID) -> tuple[SyncRun, JobExecution]:
    run = runs_repo.get_run(db, run_id)
    if run is None:
        raise NotFoundError("Run non trovato.", details={"run_id": str(run_id)})
    if run.status not in {SyncRunStatus.PARTIAL.value, SyncRunStatus.FAILED.value}:
        raise ConflictError(
            "Il run non è riprendibile.", code="RUN_NOT_RESUMABLE", details={"status": run.status}
        )
    binding = bindings_repo.get_binding(db, run.binding_id)
    if binding is None:
        raise NotFoundError("Binding del run non trovato.")
    collection = collections_repo.get_collection(db, binding.collection_id)
    if collection is None:
        raise NotFoundError("Collezione del binding non trovata.")
    snapshot = _resolve_snapshot(db, collection, snapshot_id=None, mode=SyncMode(binding.mode))
    new_run = runs_repo.create_run(
        db,
        binding_id=binding.id,
        target_id=binding.target_id,
        media_type=binding.media_type,
        snapshot_id=snapshot.id,
        mode=binding.mode,
        trigger_type="RETRY",
        is_dry_run=run.is_dry_run,
        parent_run_id=run.id,
        summary={"idempotency_key": f"resume:{run.id}"},
    )
    bindings_repo.set_last_run(db, binding, new_run.id)
    db.commit()
    job = tasks.enqueue_sync_run(db, settings, new_run.id)
    db.refresh(new_run)
    return new_run, job


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
        if not _snapshot_usable(snapshot, mode):
            raise ConflictError("Snapshot non utilizzabile.", code="SNAPSHOT_INVALID")
        return snapshot
    if collection.last_valid_snapshot_id is not None:
        snapshot = snapshots_repo.get_snapshot(db, collection.last_valid_snapshot_id)
        if snapshot is not None and _snapshot_usable(snapshot, mode):
            return snapshot
    if mode is SyncMode.APPEND_ONLY:
        for candidate in snapshots_repo.list_snapshots(db, collection.id, limit=50):
            if _snapshot_usable(candidate, mode):
                return candidate
    raise ConflictError(
        "Nessuno snapshot valido disponibile: acquisire la collezione prima di sincronizzare.",
        code="SNAPSHOT_INVALID",
        details={"collection_id": str(collection.id)},
    )


def _snapshot_usable(snapshot: CollectionSnapshot, mode: SyncMode) -> bool:
    if snapshot.status != "COMPLETE" or snapshot.items_count == 0:
        return False
    if mode is SyncMode.MIRROR:
        return bool(snapshot.is_valid) and snapshot.unresolved_count == 0
    return True
