"""Sync executor: preflight, planning, application, verification and reorder.

Invariants enforced here:

* nothing is written before the plan is persisted;
* every remote write is a ``SyncOperation`` row created *before* the request;
* a timeout or 5xx marks the batch ``UNCERTAIN`` and the remote list is read
  back before any retry (no blind retry);
* a failed reorder is a warning (``ORDER_NOT_ENFORCED``), not a ``PARTIAL``;
* one writer per target: PostgreSQL advisory lock, in-process lock on SQLite.
"""

from __future__ import annotations

import hashlib
import random
import threading
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api.errors import NotFoundError
from app.core.config import Settings
from app.core.logging import get_logger
from app.core.time import ensure_utc, utcnow
from app.db.models import (
    Collection,
    CollectionSnapshot,
    MdblistTarget,
    Media,
    SnapshotItem,
    SyncBinding,
    SyncOperation,
    SyncRun,
)
from app.domain.enums import (
    TERMINAL_RUN_STATUSES,
    MediaType,
    SyncMode,
    SyncOperationAction,
    SyncOperationStatus,
    SyncRunStatus,
)
from app.integrations.mdblist.client import (
    MdbListAuthError,
    MdbListClient,
    MdbListError,
    MdbListNotFoundError,
    MdbListPermissionError,
    MdbListRateLimitError,
    MdbListRequestError,
    MdbListServerError,
    MdbListTimeout,
)
from app.integrations.mdblist.models import MdbListId, MdbListList, MdbListListItem
from app.repositories import bindings as bindings_repo
from app.repositories import collections as collections_repo
from app.repositories import media as media_repo
from app.repositories import runs as runs_repo
from app.repositories import snapshots as snapshots_repo
from app.repositories import targets as targets_repo
from app.services import credentials as credentials_service
from app.services import planning, reconciliation
from app.services.credentials import CredentialKind
from app.services.planning import MediaKey, SourceItem, SyncPlan
from app.services.thresholds import (
    ThresholdPolicy,
    ThresholdResult,
    auto_apply_allowed,
)

logger = get_logger(__name__)

DEFAULT_BATCH_SIZE = 100
MAX_ATTEMPTS = 5
NOT_FOUND_SUPPRESSION_THRESHOLD = 3
NOT_FOUND_SUPPRESSION_DAYS = 30
MAX_RATE_LIMIT_SLEEP_SECONDS = 60.0
TERMINAL_STATUS_VALUES = {status.value for status in TERMINAL_RUN_STATUSES}

_INPROCESS_LOCKS: dict[str, threading.Lock] = {}
_INPROCESS_GUARD = threading.Lock()


def next_delay(
    attempt: int,
    retry_after: float | None,
    *,
    rng: random.Random | None = None,
) -> float:
    """Backoff for one retry: ``Retry-After`` wins, otherwise exponential + jitter."""
    if retry_after is not None:
        return max(0.0, retry_after)
    base = 0.5 * (2 ** max(0, attempt - 1))
    cap = 30.0
    jitter = (rng or random).uniform(0.8, 1.2)
    return min(base, cap) * jitter


class WriteThrottle:
    """Fixed-window write budget (240 writes per 5 minutes by default).

    MDBList allows 300 writes per 5-minute window per account. The throttle
    keeps a margin and is process-wide; a multi-worker deployment should move
    the counter to Redis.
    """

    def __init__(
        self,
        *,
        capacity: int = 240,
        window_seconds: float = 300.0,
    ) -> None:
        self.capacity = capacity
        self.window_seconds = window_seconds
        self._window_start = time.monotonic()
        self._used = 0
        self._lock = threading.Lock()

    def acquire(self, count: int, *, sleep: Callable[[float], None] = time.sleep) -> None:
        if count <= 0:
            return
        with self._lock:
            now = time.monotonic()
            if now - self._window_start >= self.window_seconds:
                self._window_start = now
                self._used = 0
            if self._used + count > self.capacity:
                wait = self.window_seconds - (now - self._window_start)
                if wait > 0:
                    sleep(wait)
                self._window_start = time.monotonic()
                self._used = 0
            self._used += count


WRITE_THROTTLE = WriteThrottle()


@dataclass(frozen=True)
class SyncOutcome:
    run_id: uuid.UUID
    status: str
    added: int
    removed: int
    failed: int
    uncertain: int
    order_enforced: bool
    warnings: list[str] = field(default_factory=list)
    abort_reason: str | None = None
    plan_hash: str | None = None


class TargetLock:
    """One writer per target.

    PostgreSQL uses a session-level advisory lock held on a dedicated
    connection for the whole run (the run spans several transactions). SQLite
    uses a process-local lock, which is enough for the single-process test setup.
    """

    def __init__(self, db: Session, target_id: uuid.UUID) -> None:
        self.key = f"mdblist_target:{target_id}"
        self._db = db
        self._connection: Any | None = None
        self._inprocess: threading.Lock | None = None
        self.acquired = False

    def acquire(self) -> bool:
        bind = self._db.get_bind()
        if bind.dialect.name == "postgresql":
            connection = bind.connect()
            try:
                acquired = bool(
                    connection.execute(
                        text("SELECT pg_try_advisory_lock(hashtextextended(:key, 0))"),
                        {"key": self.key},
                    ).scalar()
                )
            except Exception:
                connection.close()
                raise
            if not acquired:
                connection.close()
                return False
            self._connection = connection
            self.acquired = True
            return True
        with _INPROCESS_GUARD:
            lock = _INPROCESS_LOCKS.setdefault(self.key, threading.Lock())
        if not lock.acquire(blocking=False):
            return False
        self._inprocess = lock
        self.acquired = True
        return True

    def release(self) -> None:
        if not self.acquired:
            return
        if self._connection is not None:
            try:
                self._connection.execute(
                    text("SELECT pg_advisory_unlock(hashtextextended(:key, 0))"),
                    {"key": self.key},
                )
            finally:
                self._connection.close()
                self._connection = None
        elif self._inprocess is not None:
            self._inprocess.release()
            with _INPROCESS_GUARD:
                if not self._inprocess.locked():
                    _INPROCESS_LOCKS.pop(self.key, None)
            self._inprocess = None
        self.acquired = False


def build_client(db: Session, settings: Settings) -> MdbListClient:
    """Build a client from the encrypted MDBLIST credential."""
    api_key = credentials_service.get_secret(db, settings, CredentialKind.MDBLIST)
    return MdbListClient(
        api_key,
        timeout=float(settings.http_timeout_seconds),
        max_retries=settings.http_max_retries,
        backoff_base_seconds=settings.http_backoff_base_ms / 1000,
        backoff_max_seconds=settings.http_backoff_max_ms / 1000,
        jitter_ratio=settings.http_jitter_ratio,
    )


def execute_run(
    db: Session,
    settings: Settings,
    run_id: uuid.UUID,
    *,
    client: MdbListClient,
    sleep: Callable[[float], None] = time.sleep,
    throttle: WriteThrottle | None = None,
) -> SyncOutcome:
    """Drive one run from ``PENDING`` to a terminal state."""
    run = runs_repo.get_run(db, run_id)
    if run is None:
        raise NotFoundError("Run non trovato.", details={"run_id": str(run_id)})
    if run.status in TERMINAL_STATUS_VALUES:
        return _outcome(run)

    binding = bindings_repo.get_binding(db, run.binding_id)
    target = targets_repo.get_target(db, run.target_id)
    snapshot = snapshots_repo.get_snapshot(db, run.snapshot_id)
    collection = collections_repo.get_collection(db, binding.collection_id) if binding else None
    if binding is None or target is None or snapshot is None or collection is None:
        return _block(db, run, "BINDING_INCOMPLETE", "Binding, target o snapshot mancante.")

    if run.status in {SyncRunStatus.APPLYING.value, SyncRunStatus.VERIFYING.value}:
        # Crash recovery: the ledger already exists, so reconcile instead of replanning.
        if run.status == SyncRunStatus.APPLYING.value:
            runs_repo.transition_run(db, run, SyncRunStatus.VERIFYING, message="resume after crash")
            db.commit()
        return _verify_and_finish(db, run, target, binding, client, _plan_from_summary(run))

    lock: TargetLock | None = None
    try:
        if not run.is_dry_run:
            lock = TargetLock(db, target.id)
            if not lock.acquire():
                return _block(db, run, "LOCK_HELD", "Un altro run sta scrivendo sul target.")

        resuming_approval = run.status == SyncRunStatus.AWAITING_APPROVAL.value
        if resuming_approval:
            runs_repo.transition_run(
                db, run, SyncRunStatus.PLANNING, message="resume after approval"
            )
        else:
            runs_repo.transition_run(db, run, SyncRunStatus.PREFLIGHT, message="preflight")
        db.commit()

        preflight_reason = _preflight_reason(run, binding, target, snapshot, collection)
        if preflight_reason is not None:
            return _block(db, run, preflight_reason)

        try:
            remote_list = client.get_list(target.remote_list_id)
        except MdbListError as exc:
            return _block(db, run, _error_reason(exc), str(exc))
        ownership_reason = _ownership_reason(client, remote_list)
        if ownership_reason is not None:
            return _block(db, run, ownership_reason)
        targets_repo.update_remote_metadata(
            db,
            target,
            name=remote_list.name,
            remote_slug=remote_list.slug,
            is_private=remote_list.private,
            item_count=remote_list.item_count,
            verified=True,
        )
        db.commit()

        try:
            remote_read = reconciliation.read_all_remote_items(client, target.remote_list_id)
        except reconciliation.ReconciliationIncomplete as exc:
            return _block(db, run, _reconciliation_reason(exc), str(exc))
        targets_repo.mark_remote_read(db, target, item_count=len(remote_read.items))
        db.commit()

        if run.status != SyncRunStatus.PLANNING.value:
            runs_repo.transition_run(db, run, SyncRunStatus.PLANNING, message="planning")
            db.commit()

        source_items = load_source_items(db, snapshot, collection)
        policy_version = binding.policy_version or planning.PLANNER_VERSION
        previous_plan_hash = run.plan_hash
        plan = planning.plan_sync(
            mode=run.mode,
            snapshot=snapshot,
            source_items=source_items,
            remote_items=remote_read.items,
            binding=binding,
            policy_version=policy_version,
        )
        requires_approval = _requires_approval(binding, plan)
        summary = planning.plan_summary(plan)
        summary["idempotency_key"] = (run.summary or {}).get("idempotency_key")
        summary["trigger"] = run.trigger_type
        summary["planned_at"] = utcnow().isoformat()
        runs_repo.set_plan(
            db,
            run,
            plan_hash=plan.plan_hash,
            snapshot_hash=plan.snapshot_hash,
            source_item_count=plan.source_item_count,
            remote_item_count=plan.remote_item_count,
            to_add_count=len(plan.to_add),
            to_remove_count=len(plan.to_remove),
            threshold_breached=plan.threshold.breached,
            requires_approval=requires_approval and run.approved_at is None,
            warnings=plan.warnings,
            summary=summary,
        )
        db.commit()

        if plan.blocked:
            return _block(db, run, plan.block_reason or "PLAN_BLOCKED")

        if not plan.has_changes and not plan.reorder_needed:
            runs_repo.finish_run(
                db,
                run,
                SyncRunStatus.SUCCEEDED,
                order_enforced=plan.order_enforced,
                warnings=plan.warnings,
            )
            db.commit()
            return _outcome(run)

        if run.is_dry_run:
            _create_operations(db, run, target, plan, snapshot, remote_read.items)
            runs_repo.finish_run(
                db,
                run,
                SyncRunStatus.SUCCEEDED,
                order_enforced=plan.order_enforced,
                warnings=plan.warnings,
            )
            db.commit()
            return _outcome(run)

        if (
            run.approved_at is not None
            and previous_plan_hash
            and previous_plan_hash != plan.plan_hash
        ):
            return _fail(
                db,
                run,
                "STALE_PLAN",
                "Il piano è cambiato dopo l'approvazione: ricalcolare la preview.",
            )

        if requires_approval and run.approved_at is None:
            reason = plan.threshold.primary_reason or "MANUAL_REVIEW_REQUIRED"
            runs_repo.transition_run(db, run, SyncRunStatus.AWAITING_APPROVAL, message=reason)
            db.commit()
            return _outcome(run)

        runs_repo.transition_run(db, run, SyncRunStatus.APPLYING, message="apply")
        db.commit()
        operations = _create_operations(db, run, target, plan, snapshot, remote_read.items)
        db.commit()

        add_ops = [
            operation
            for operation in operations
            if operation.action == SyncOperationAction.ADD.value
        ]
        remove_ops = [
            operation
            for operation in operations
            if operation.action == SyncOperationAction.REMOVE.value
        ]
        fatal_code = _apply_action(
            db,
            run,
            target,
            client,
            add_ops,
            "add",
            batch_size=settings.sync_batch_size or DEFAULT_BATCH_SIZE,
            sleep=sleep,
            throttle=throttle,
        )
        if fatal_code is not None:
            _fail_pending_operations(db, run, fatal_code)
            return _fail(db, run, fatal_code)
        if _is_cancelled(db, run):
            return _finish_cancelled(db, run)
        fatal_code = _apply_action(
            db,
            run,
            target,
            client,
            remove_ops,
            "remove",
            batch_size=settings.sync_batch_size or DEFAULT_BATCH_SIZE,
            sleep=sleep,
            throttle=throttle,
        )
        if fatal_code is not None:
            _fail_pending_operations(db, run, fatal_code)
            return _fail(db, run, fatal_code)
        if _is_cancelled(db, run):
            return _finish_cancelled(db, run)

        runs_repo.transition_run(db, run, SyncRunStatus.VERIFYING, message="verify")
        db.commit()
        return _verify_and_finish(db, run, target, binding, client, plan)
    finally:
        if lock is not None:
            lock.release()


def reconcile_run(
    db: Session,
    settings: Settings,
    run_id: uuid.UUID,
    *,
    client: MdbListClient,
) -> SyncOutcome:
    """Re-read the remote list and reconcile a PARTIAL/FAILED run."""
    run = runs_repo.get_run(db, run_id)
    if run is None:
        raise NotFoundError("Run non trovato.", details={"run_id": str(run_id)})
    if run.status not in {
        SyncRunStatus.PARTIAL.value,
        SyncRunStatus.FAILED.value,
        SyncRunStatus.VERIFYING.value,
    }:
        return _outcome(run)
    target = targets_repo.get_target(db, run.target_id)
    binding = bindings_repo.get_binding(db, run.binding_id)
    if target is None or binding is None:
        return _block(db, run, "BINDING_INCOMPLETE", "Target o binding mancante.")
    if run.status != SyncRunStatus.VERIFYING.value:
        runs_repo.transition_run(db, run, SyncRunStatus.VERIFYING, message="reconcile")
        db.commit()
    plan = _plan_from_summary(run)
    lock = TargetLock(db, target.id)
    if not lock.acquire():
        return _block(
            db,
            run,
            "LOCK_HELD",
            "Un altro run sta scrivendo sul target: riconciliazione non eseguita.",
        )
    try:
        return _verify_and_finish(db, run, target, binding, client, plan)
    finally:
        lock.release()


def _verify_and_finish(
    db: Session,
    run: SyncRun,
    target: MdblistTarget,
    binding: SyncBinding,
    client: MdbListClient,
    plan: SyncPlan | None,
) -> SyncOutcome:
    try:
        remote = reconciliation.read_all_remote_items(client, target.remote_list_id)
    except reconciliation.ReconciliationIncomplete as exc:
        runs_repo.set_counters(
            db,
            run,
            added=run.added_count,
            removed=run.removed_count,
            failed=run.failed_count,
            uncertain=max(run.uncertain_count, 1),
        )
        counts = runs_repo.operation_counts(db, run.id)
        succeeded = counts.get(SyncOperationStatus.SUCCEEDED.value, 0) + counts.get(
            SyncOperationStatus.SKIPPED.value, 0
        )
        runs_repo.finish_run(
            db,
            run,
            SyncRunStatus.PARTIAL if succeeded else SyncRunStatus.FAILED,
            error_code="REMOTE_READ_INCOMPLETE",
            error_message=str(exc),
            order_enforced=False,
        )
        db.commit()
        return _outcome(run)

    operations = runs_repo.list_operations(db, run.id, limit=100_000)
    reconciliation.reconcile_operations(
        db, run, operations, reconciliation.remote_keys(remote.items)
    )
    # Verification is the last chance to retry: anything still not applied is
    # uncertain and must be visible as such, never silently counted as success.
    for operation in operations:
        if operation.status in {
            SyncOperationStatus.PENDING.value,
            SyncOperationStatus.IN_FLIGHT.value,
        }:
            runs_repo.set_operation_status(
                db,
                operation,
                SyncOperationStatus.UNCERTAIN,
                error_code="MDBLIST_UNCERTAIN",
                error_message="Verifica conclusa: stato remoto non allineato.",
            )
    db.commit()

    add_ops = [
        operation for operation in operations if operation.action == SyncOperationAction.ADD.value
    ]
    remove_ops = [
        operation
        for operation in operations
        if operation.action == SyncOperationAction.REMOVE.value
    ]
    added = sum(
        1
        for operation in add_ops
        if operation.status
        in {SyncOperationStatus.SUCCEEDED.value, SyncOperationStatus.SKIPPED.value}
    )
    removed = sum(
        1
        for operation in remove_ops
        if operation.status
        in {SyncOperationStatus.SUCCEEDED.value, SyncOperationStatus.SKIPPED.value}
    )
    failed = sum(
        1 for operation in operations if operation.status == SyncOperationStatus.FAILED.value
    )
    uncertain = sum(
        1
        for operation in operations
        if operation.status
        in {SyncOperationStatus.UNCERTAIN.value, SyncOperationStatus.IN_FLIGHT.value}
    )
    runs_repo.set_counters(
        db, run, added=added, removed=removed, failed=failed, uncertain=uncertain
    )

    warnings = list(run.warnings or [])
    order_enforced = run.order_enforced
    if plan is not None and not plan.reorder_needed:
        order_enforced = True
    if plan is not None and plan.reorder_needed:
        if binding.preserve_order and binding.reorder_enabled:
            reorder = reconciliation.reorder_to_order(
                client, target.remote_list_id, plan.desired_order
            )
            order_enforced = reorder.succeeded
            if reorder.succeeded:
                warnings = [warning for warning in warnings if warning != "ORDER_NOT_ENFORCED"]
            else:
                for warning in reorder.warnings:
                    if warning not in warnings:
                        warnings.append(warning)
        else:
            order_enforced = False
            if "ORDER_NOT_ENFORCED" not in warnings:
                warnings.append("ORDER_NOT_ENFORCED")

    if failed == 0 and uncertain == 0:
        status = SyncRunStatus.SUCCEEDED
    elif added + removed > 0:
        status = SyncRunStatus.PARTIAL
    else:
        status = SyncRunStatus.FAILED
    runs_repo.finish_run(
        db,
        run,
        status,
        order_enforced=order_enforced,
        warnings=warnings,
    )
    db.commit()
    return _outcome(run)


@dataclass
class _BatchOutcome:
    retry: list[SyncOperation] = field(default_factory=list)
    fatal_code: str | None = None

    @property
    def fatal(self) -> bool:
        return self.fatal_code is not None


def _apply_action(
    db: Session,
    run: SyncRun,
    target: MdblistTarget,
    client: MdbListClient,
    operations: Sequence[SyncOperation],
    action: str,
    *,
    batch_size: int,
    sleep: Callable[[float], None],
    throttle: WriteThrottle | None = None,
) -> str | None:
    pending = list(operations)
    rounds = 0
    while pending and rounds < MAX_ATTEMPTS:
        rounds += 1
        retry: list[SyncOperation] = []
        for batch in _chunks(pending, batch_size):
            if _is_cancelled(db, run):
                return None
            if throttle is not None:
                throttle.acquire(len(batch), sleep=sleep)
            outcome = _send_batch(db, run, target, client, batch, action, sleep)
            retry.extend(outcome.retry)
            db.commit()
            if outcome.fatal:
                return outcome.fatal_code
        if not retry:
            return None
        if not all(operation.error_code == "MDBLIST_RATE_LIMITED" for operation in retry):
            sleep(next_delay(rounds, None))
        uncertain = [
            operation
            for operation in retry
            if operation.status == SyncOperationStatus.UNCERTAIN.value
        ]
        if uncertain:
            try:
                remote = reconciliation.read_all_remote_items(client, target.remote_list_id)
            except reconciliation.ReconciliationIncomplete:
                break
            reconciliation.reconcile_operations(
                db, run, uncertain, reconciliation.remote_keys(remote.items)
            )
            db.commit()
        pending = [
            operation
            for operation in retry
            if operation.status == SyncOperationStatus.PENDING.value
        ]
    for operation in pending:
        if operation.status in {
            SyncOperationStatus.PENDING.value,
            SyncOperationStatus.UNCERTAIN.value,
        }:
            runs_repo.set_operation_status(
                db,
                operation,
                SyncOperationStatus.FAILED,
                error_code=operation.error_code or "MDBLIST_UNCERTAIN",
                error_message="Tentativi esauriti: stato remoto non allineato.",
            )
    db.commit()
    return None


def _send_batch(
    db: Session,
    run: SyncRun,
    target: MdblistTarget,
    client: MdbListClient,
    batch: Sequence[SyncOperation],
    action: str,
    sleep: Callable[[float], None],
) -> _BatchOutcome:
    batch_id = uuid.uuid4()
    for operation in batch:
        operation.batch_id = batch_id
        operation.status = SyncOperationStatus.IN_FLIGHT.value
        operation.attempt += 1
        operation.started_at = operation.started_at or utcnow()
        operation.error_code = None
        operation.error_message = None
    db.flush()

    movies, shows = _payload_for(batch)
    started = time.monotonic()
    try:
        if action == "add":
            result = client.add_items(target.remote_list_id, movies=movies, shows=shows)
        else:
            result = client.remove_items(target.remote_list_id, movies=movies, shows=shows)
    except MdbListRateLimitError as exc:
        wait = exc.retry_after_seconds
        if wait is not None and wait > 0:
            sleep(min(wait, MAX_RATE_LIMIT_SLEEP_SECONDS))
        retry: list[SyncOperation] = []
        for operation in batch:
            if operation.attempt >= operation.max_attempts:
                runs_repo.set_operation_status(
                    db,
                    operation,
                    SyncOperationStatus.FAILED,
                    error_code="MDBLIST_RATE_LIMITED",
                    error_message="Rate limit MDBList: tentativi esauriti.",
                )
                continue
            runs_repo.set_operation_status(
                db,
                operation,
                SyncOperationStatus.PENDING,
                error_code="MDBLIST_RATE_LIMITED",
                error_message="Rate limit MDBList: attesa e nuovo tentativo.",
                next_retry_at=utcnow() + timedelta(seconds=wait or 30),
            )
            retry.append(operation)
        db.flush()
        return _BatchOutcome(retry=retry)
    except (MdbListTimeout, MdbListServerError) as exc:
        for operation in batch:
            runs_repo.set_operation_status(
                db,
                operation,
                SyncOperationStatus.UNCERTAIN,
                error_code="MDBLIST_UNCERTAIN",
                error_message=str(exc)[:1000],
            )
        db.flush()
        return _BatchOutcome(retry=list(batch))
    except (MdbListAuthError, MdbListPermissionError, MdbListNotFoundError) as exc:
        code = _error_reason(exc)
        for operation in batch:
            runs_repo.set_operation_status(
                db,
                operation,
                SyncOperationStatus.FAILED,
                error_code=code,
                error_message=str(exc)[:1000],
            )
        db.flush()
        return _BatchOutcome(fatal_code=code)
    except MdbListRequestError as exc:
        for operation in batch:
            runs_repo.set_operation_status(
                db,
                operation,
                SyncOperationStatus.FAILED,
                error_code="MDBLIST_REQUEST_FAILED",
                error_message=str(exc)[:1000],
            )
        db.flush()
        return _BatchOutcome()

    duration_ms = int((time.monotonic() - started) * 1000)
    if result.not_found_total or result.existing_total:
        try:
            remote = reconciliation.read_all_remote_items(client, target.remote_list_id)
        except reconciliation.ReconciliationIncomplete:
            remote = None
        if remote is not None:
            _settle_batch_from_remote(
                db, run, batch, action, reconciliation.remote_keys(remote.items)
            )
            db.flush()
            return _BatchOutcome(
                retry=[
                    operation
                    for operation in batch
                    if operation.status == SyncOperationStatus.PENDING.value
                ]
            )
        # The aggregate counters say something was not applied but the read-back
        # failed: do not claim success, let verification reconcile the batch.
        for operation in batch:
            runs_repo.set_operation_status(
                db,
                operation,
                SyncOperationStatus.UNCERTAIN,
                error_code="MDBLIST_UNCERTAIN",
                error_message="Rilettura remota non riuscita dopo il batch.",
            )
        db.flush()
        return _BatchOutcome(retry=list(batch))

    for operation in batch:
        runs_repo.set_operation_status(
            db,
            operation,
            SyncOperationStatus.SUCCEEDED,
            http_status=200,
            duration_ms=duration_ms,
            response=result.raw,
        )
        _reset_not_found(db, operation)
    db.flush()
    return _BatchOutcome()


def _settle_batch_from_remote(
    db: Session,
    run: SyncRun,
    batch: Sequence[SyncOperation],
    action: str,
    remote: set[MediaKey],
) -> None:
    for operation in batch:
        key = reconciliation.media_key_from_label(operation.remote_id)
        present = key in remote if key is not None else False
        if action == "add":
            if present:
                runs_repo.set_operation_status(
                    db,
                    operation,
                    SyncOperationStatus.SUCCEEDED,
                    error_code=None,
                    reconciled=True,
                )
                _reset_not_found(db, operation)
            else:
                runs_repo.set_operation_status(
                    db,
                    operation,
                    SyncOperationStatus.FAILED,
                    error_code="MDBLIST_NOT_FOUND",
                    error_message="MDBList non riconosce questo media.",
                    reconciled=True,
                )
                _register_not_found(db, operation)
        else:
            if not present:
                runs_repo.set_operation_status(
                    db,
                    operation,
                    SyncOperationStatus.SUCCEEDED,
                    error_code=None,
                    reconciled=True,
                )
            else:
                runs_repo.set_operation_status(
                    db,
                    operation,
                    SyncOperationStatus.FAILED,
                    error_code="MDBLIST_REMOVE_NOT_APPLIED",
                    error_message="L'elemento è ancora presente dopo la rimozione.",
                    reconciled=True,
                )


def _fail_pending_operations(db: Session, run: SyncRun, error_code: str) -> None:
    for operation in runs_repo.list_operations(db, run.id, limit=100_000):
        if operation.status in {
            SyncOperationStatus.PENDING.value,
            SyncOperationStatus.IN_FLIGHT.value,
            SyncOperationStatus.UNCERTAIN.value,
        }:
            runs_repo.set_operation_status(
                db,
                operation,
                SyncOperationStatus.FAILED,
                error_code=error_code,
                error_message="Run interrotto da un errore definitivo.",
            )
    db.commit()


def _register_not_found(db: Session, operation: SyncOperation) -> None:
    if operation.media_id is None:
        return
    media = db.get(Media, operation.media_id)
    if media is None:
        return
    media.not_found_count = int(media.not_found_count or 0) + 1
    if media.not_found_count >= NOT_FOUND_SUPPRESSION_THRESHOLD:
        media.sync_suppressed_until = utcnow() + timedelta(days=NOT_FOUND_SUPPRESSION_DAYS)
    db.flush()


def _reset_not_found(db: Session, operation: SyncOperation) -> None:
    if operation.media_id is None:
        return
    media = db.get(Media, operation.media_id)
    if media is None:
        return
    media.not_found_count = 0
    media.sync_suppressed_until = None
    db.flush()


def _payload_for(
    batch: Sequence[SyncOperation],
) -> tuple[list[MdbListId], list[MdbListId]]:
    movies: list[MdbListId] = []
    shows: list[MdbListId] = []
    for operation in batch:
        key = reconciliation.media_key_from_label(operation.remote_id)
        if key is None:
            continue
        if key.media_type == MediaType.MOVIE.value:
            movies.append(key.as_mdblist_id())
        elif key.media_type == MediaType.SHOW.value:
            shows.append(key.as_mdblist_id())
    return movies, shows


def _create_operations(
    db: Session,
    run: SyncRun,
    target: MdblistTarget,
    plan: SyncPlan,
    snapshot: CollectionSnapshot,
    remote_items: Sequence[MdbListListItem],
) -> list[SyncOperation]:
    source_media = _source_media_ids(db, snapshot)
    remote_by_key: dict[MediaKey, MdbListListItem] = {}
    for item in remote_items:
        key = planning.remote_key(item)
        if key is not None and key not in remote_by_key:
            remote_by_key[key] = item

    operations: list[SyncOperation] = []
    for action, keys in (
        (SyncOperationAction.ADD.value, plan.to_add),
        (SyncOperationAction.REMOVE.value, plan.to_remove),
    ):
        for key in keys:
            media_id = source_media.get(key)
            if media_id is None:
                media_id = _media_id_for_key(db, key, remote_by_key.get(key))
            if media_id is None:
                continue
            idempotency_key = hashlib.sha256(
                f"{run.id}|{action}|{key.label()}|{target.id}".encode()
            ).hexdigest()
            operations.append(
                runs_repo.create_operation(
                    db,
                    run_id=run.id,
                    action=action,
                    media_id=media_id,
                    remote_id=key.label(),
                    idempotency_key=idempotency_key,
                    max_attempts=MAX_ATTEMPTS,
                )
            )
    db.flush()
    return operations


def _media_id_for_key(
    db: Session, key: MediaKey, remote_item: MdbListListItem | None
) -> uuid.UUID | None:
    tmdb_id = int(key.value) if key.id_type == "tmdb" else None
    imdb_id = key.value if key.id_type == "imdb" else None
    media = media_repo.find_by_tmdb(db, key.media_type, tmdb_id) if tmdb_id is not None else None
    if media is None and imdb_id:
        media = media_repo.find_by_imdb(db, key.media_type, imdb_id)
    if media is not None:
        return media.id
    resolved = media_repo.resolve_media(
        db,
        media_type=key.media_type,
        tmdb_id=tmdb_id,
        imdb_id=imdb_id,
        title=(remote_item.title if remote_item and remote_item.title else "Senza titolo"),
        year=remote_item.release_year if remote_item else None,
        metadata={"source": "mdblist"},
    )
    return resolved.id if resolved is not None else None


def _source_media_ids(db: Session, snapshot: CollectionSnapshot) -> dict[MediaKey, uuid.UUID]:
    result: dict[MediaKey, uuid.UUID] = {}
    stmt = (
        select(SnapshotItem, Media)
        .outerjoin(Media, SnapshotItem.media_id == Media.id)
        .where(SnapshotItem.snapshot_id == snapshot.id)
        .order_by(SnapshotItem.position)
    )
    for item, media in db.execute(stmt).all():
        if media is None or item.media_id is None:
            continue
        key = planning.build_media_key(media.media_type, media.tmdb_id, media.imdb_id)
        if key is not None:
            result.setdefault(key, item.media_id)
    return result


def load_source_items(
    db: Session, snapshot: CollectionSnapshot, collection: Collection
) -> list[SourceItem]:
    items: list[SourceItem] = []
    now = utcnow()
    stmt = (
        select(SnapshotItem, Media)
        .outerjoin(Media, SnapshotItem.media_id == Media.id)
        .where(SnapshotItem.snapshot_id == snapshot.id)
        .order_by(SnapshotItem.position)
    )
    for item, media in db.execute(stmt).all():
        if media is None:
            items.append(
                SourceItem(
                    media_type=collection.media_type,
                    tmdb_id=None,
                    imdb_id=None,
                    media_id=None,
                    resolution_status=item.resolution_status,
                )
            )
            continue
        suppressed = (
            media.sync_suppressed_until is not None
            and ensure_utc(media.sync_suppressed_until) > now
        )
        items.append(
            SourceItem(
                media_type=media.media_type,
                tmdb_id=media.tmdb_id,
                imdb_id=media.imdb_id,
                media_id=media.id,
                resolution_status=item.resolution_status,
                title=media.title,
                year=media.release_year,
                suppressed=suppressed,
            )
        )
    return items


def _preflight_reason(
    run: SyncRun,
    binding: SyncBinding,
    target: MdblistTarget,
    snapshot: CollectionSnapshot,
    collection: Collection,
) -> str | None:
    if snapshot.collection_id != binding.collection_id:
        return "SNAPSHOT_COLLECTION_MISMATCH"
    if snapshot.status == "RUNNING":
        return "SNAPSHOT_RUNNING"
    if snapshot.status != "COMPLETE":
        return "SNAPSHOT_INCOMPLETE"
    if snapshot.items_count == 0:
        return "SNAPSHOT_EMPTY"
    if run.mode == SyncMode.MIRROR.value and not snapshot.is_valid:
        return "SNAPSHOT_NOT_VALID_FOR_MIRROR"
    if run.mode == SyncMode.MIRROR.value and snapshot.unresolved_count > 0:
        return "SNAPSHOT_UNRESOLVED_ITEMS"
    if binding.media_type != target.mediatype:
        return "MEDIA_TYPE_MISMATCH"
    if run.media_type != binding.media_type or collection.media_type != binding.media_type:
        return "MEDIA_TYPE_MISMATCH"
    if binding.is_enabled and binding.policy_accepted_at is None:
        return "POLICY_NOT_ACCEPTED"
    return None


def _ownership_reason(client: MdbListClient, remote_list: MdbListList) -> str | None:
    """Verify the list belongs to the authenticated account when possible."""
    try:
        user = client.get_user()
    except MdbListAuthError:
        return "MDBLIST_AUTH_FAILED"
    except MdbListPermissionError:
        return "MDBLIST_PERMISSION_DENIED"
    except MdbListError:
        # Ownership cannot be proven now; a 403 on write remains a definitive block.
        return None
    if user.id is not None and remote_list.user_id is not None and user.id != remote_list.user_id:
        return "MDBLIST_PERMISSION_DENIED"
    return None


def _requires_approval(binding: SyncBinding, plan: SyncPlan) -> bool:
    if binding.schedule_policy == "ALWAYS_APPROVE":
        return True
    if plan.threshold.breached and binding.require_manual_review:
        return True
    if binding.schedule_policy == "AUTO_APPLY_IF_SAFE":
        return not auto_apply_allowed(
            to_remove_count=len(plan.to_remove),
            removal_ratio=plan.threshold.removal_ratio,
            policy=ThresholdPolicy.from_binding(binding),
        )
    return False


def _plan_from_summary(run: SyncRun) -> SyncPlan | None:
    """Rebuild the reorder order from the persisted summary (no re-planning)."""
    summary = run.summary or {}
    desired = summary.get("desired_order")
    if not isinstance(desired, list):
        return None
    keys: list[MediaKey] = []
    for label in desired:
        key = reconciliation.media_key_from_label(label if isinstance(label, str) else None)
        if key is not None:
            keys.append(key)
    return SyncPlan(
        mode=run.mode,
        to_add=(),
        to_remove=(),
        unchanged=(),
        unresolved=(),
        unmapped_remote=(),
        remote_duplicates=(),
        suppressed=(),
        desired_order=tuple(keys),
        reorder_needed=bool(summary.get("reorder_needed")),
        plan_hash=run.plan_hash or "",
        snapshot_hash=run.snapshot_hash or "",
        order_enforced=run.order_enforced,
        source_item_count=run.source_item_count,
        remote_item_count=run.remote_item_count,
        blocked=False,
        block_reason=None,
        warnings=tuple(run.warnings or []),
        threshold=_empty_threshold(),
        policy_version=str(summary.get("policy_version") or planning.PLANNER_VERSION),
    )


def _empty_threshold() -> ThresholdResult:
    return ThresholdResult(
        breached=False,
        reasons=(),
        removal_ratio=0.0,
        addition_ratio=0.0,
        observed_removals=0,
        observed_additions=0,
        remote_count=0,
        max_removal_absolute=0,
        max_removal_percent=0.0,
        max_addition_percent=0.0,
        require_manual_review=False,
    )


def _chunks(operations: Sequence[SyncOperation], size: int) -> list[list[SyncOperation]]:
    if size < 1:
        size = DEFAULT_BATCH_SIZE
    return [list(operations[index : index + size]) for index in range(0, len(operations), size)]


def _is_cancelled(db: Session, run: SyncRun) -> bool:
    db.refresh(run)
    return run.status == SyncRunStatus.CANCELLED.value


def _finish_cancelled(db: Session, run: SyncRun) -> SyncOutcome:
    if run.status != SyncRunStatus.CANCELLED.value:
        runs_repo.finish_run(db, run, SyncRunStatus.CANCELLED, abort_reason="CANCELLED_BY_USER")
        db.commit()
    return _outcome(run)


def _block(db: Session, run: SyncRun, reason: str, message: str | None = None) -> SyncOutcome:
    runs_repo.finish_run(
        db,
        run,
        SyncRunStatus.BLOCKED,
        abort_reason=reason,
        error_message=message,
    )
    db.commit()
    return _outcome(run)


def _fail(db: Session, run: SyncRun, code: str, message: str | None = None) -> SyncOutcome:
    runs_repo.finish_run(
        db,
        run,
        SyncRunStatus.FAILED,
        error_code=code,
        error_message=message,
    )
    db.commit()
    return _outcome(run)


def _error_reason(exc: MdbListError) -> str:
    if isinstance(exc, MdbListAuthError):
        return "MDBLIST_AUTH_FAILED"
    if isinstance(exc, MdbListPermissionError):
        return "MDBLIST_PERMISSION_DENIED"
    if isinstance(exc, MdbListNotFoundError):
        return "MDBLIST_LIST_NOT_FOUND"
    if isinstance(exc, MdbListRateLimitError):
        return "MDBLIST_RATE_LIMITED"
    if isinstance(exc, (MdbListServerError, MdbListTimeout)):
        return "MDBLIST_UNCERTAIN"
    return "MDBLIST_INTERNAL"


def _reconciliation_reason(exc: reconciliation.ReconciliationIncomplete) -> str:
    cause = exc.__cause__
    if isinstance(cause, MdbListError):
        return _error_reason(cause)
    return "REMOTE_READ_INCOMPLETE"


def _outcome(run: SyncRun) -> SyncOutcome:
    return SyncOutcome(
        run_id=run.id,
        status=run.status,
        added=run.added_count,
        removed=run.removed_count,
        failed=run.failed_count,
        uncertain=run.uncertain_count,
        order_enforced=run.order_enforced,
        warnings=list(run.warnings or []),
        abort_reason=run.abort_reason or run.error_code,
        plan_hash=run.plan_hash,
    )
