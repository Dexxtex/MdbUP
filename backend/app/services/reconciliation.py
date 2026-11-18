"""Remote read-back and operation reconciliation.

The remote list is the source of truth: aggregated add/remove counters are never
trusted for ``not_found``/``existing``, and an incomplete cursor read concludes
nothing. After a timeout or a 5xx the executor marks the batch ``UNCERTAIN`` and
calls this module before retrying.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.db.models import SyncOperation, SyncRun
from app.domain.enums import SyncOperationAction, SyncOperationStatus
from app.integrations.mdblist.client import MdbListClient, MdbListError
from app.integrations.mdblist.models import MdbListListItem
from app.repositories import runs as runs_repo
from app.services.planning import MediaKey, reorder_chunks

DEFAULT_PAGE_SIZE = 100
DEFAULT_MAX_PAGES = 1000


class ReconciliationIncomplete(RuntimeError):
    """The remote list could not be read completely; no conclusion is possible."""


@dataclass(frozen=True)
class RemoteRead:
    items: tuple[MdbListListItem, ...]
    pages: int
    complete: bool = True
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReconcileResult:
    succeeded: int = 0
    pending: int = 0
    failed: int = 0

    @property
    def touched(self) -> int:
        return self.succeeded + self.pending + self.failed


@dataclass(frozen=True)
class ReorderOutcome:
    attempted: bool
    succeeded: bool
    chunks: int = 0
    not_found: int = 0
    warnings: tuple[str, ...] = field(default_factory=tuple)


def read_all_remote_items(
    client: MdbListClient,
    remote_list_id: int,
    *,
    page_size: int = DEFAULT_PAGE_SIZE,
    max_pages: int = DEFAULT_MAX_PAGES,
) -> RemoteRead:
    """Read every page with ``cursor`` until ``X-Has-More`` is false."""
    items: list[MdbListListItem] = []
    cursor: str | None = None
    seen: set[str] = set()
    pages = 0
    while pages < max_pages:
        try:
            page = client.get_items(remote_list_id, cursor=cursor, limit=page_size)
        except MdbListError as exc:
            raise ReconciliationIncomplete(str(exc)) from exc
        pages += 1
        items.extend(page.items)
        if not page.has_more or page.next_cursor is None:
            return RemoteRead(items=tuple(items), pages=pages)
        if page.next_cursor in seen:
            raise ReconciliationIncomplete("Cursore MDBList ripetuto: lettura incompleta.")
        seen.add(page.next_cursor)
        cursor = page.next_cursor
    raise ReconciliationIncomplete(f"Limite di {max_pages} pagine MDBList raggiunto.")


def remote_keys(items: Sequence[MdbListListItem]) -> set[MediaKey]:
    from app.services.planning import remote_key

    keys: set[MediaKey] = set()
    for item in items:
        key = remote_key(item)
        if key is not None:
            keys.add(key)
    return keys


def media_key_from_label(label: str | None) -> MediaKey | None:
    """Parse the ``MOVIE:tmdb:603`` label stored in ``sync_operation.remote_id``."""
    if not label:
        return None
    parts = label.split(":", 2)
    if len(parts) != 3 or not all(parts):
        return None
    return MediaKey(media_type=parts[0], id_type=parts[1], value=parts[2])


def reconcile_operations(
    db: Session,
    run: SyncRun,
    operations: Sequence[SyncOperation],
    remote: set[MediaKey],
    *,
    max_attempts: int | None = None,
) -> ReconcileResult:
    """Mark operations against the current remote state.

    ``ADD`` succeeds when the item is present, ``REMOVE`` when it is absent.
    An operation that is still not applied goes back to ``PENDING`` while it has
    attempts left; otherwise it is ``FAILED`` with ``MDBLIST_UNCERTAIN``.
    """
    succeeded = pending = failed = 0
    for operation in operations:
        if operation.status in {
            SyncOperationStatus.SUCCEEDED.value,
            SyncOperationStatus.SKIPPED.value,
            SyncOperationStatus.FAILED.value,
        }:
            continue
        key = media_key_from_label(operation.remote_id)
        if key is None:
            runs_repo.set_operation_status(
                db,
                operation,
                SyncOperationStatus.FAILED,
                error_code="MDBLIST_SCHEMA_CHANGED",
                error_message="Operazione senza chiave media valida.",
                reconciled=True,
            )
            failed += 1
            continue
        present = key in remote
        applied = present if operation.action == SyncOperationAction.ADD.value else not present
        if applied:
            runs_repo.set_operation_status(
                db,
                operation,
                SyncOperationStatus.SUCCEEDED,
                error_code=None,
                error_message=None,
                reconciled=True,
            )
            succeeded += 1
            continue
        limit = max_attempts or operation.max_attempts
        if operation.attempt < limit:
            runs_repo.set_operation_status(
                db,
                operation,
                SyncOperationStatus.PENDING,
                error_code="MDBLIST_UNCERTAIN",
                error_message="Esito remoto non applicato: nuovo tentativo.",
                reconciled=True,
            )
            pending += 1
        else:
            runs_repo.set_operation_status(
                db,
                operation,
                SyncOperationStatus.FAILED,
                error_code="MDBLIST_UNCERTAIN",
                error_message="Tentativi esauriti: stato remoto non allineato.",
                reconciled=True,
            )
            failed += 1
    return ReconcileResult(succeeded=succeeded, pending=pending, failed=failed)


def reorder_to_order(
    client: MdbListClient,
    remote_list_id: int,
    keys: Sequence[MediaKey],
    *,
    chunk_size: int = 1000,
) -> ReorderOutcome:
    """Apply the desired order in chunks; a failure is a warning, not a PARTIAL.

    Content correctness is already reconciled at this point. MDBList reorder is
    not atomic, so an interruption leaves a partial order: the run stays
    ``SUCCEEDED`` with ``ORDER_NOT_ENFORCED``.
    """
    if not keys:
        return ReorderOutcome(attempted=False, succeeded=True)
    chunks = reorder_chunks(keys, chunk_size=chunk_size)
    not_found = 0
    for index, chunk in enumerate(chunks):
        items = [(key.media_type, key.as_mdblist_id()) for key in chunk]
        try:
            if index == 0:
                result = client.reorder(remote_list_id, items, position="top")
            else:
                previous = chunks[index - 1][-1]
                result = client.reorder(
                    remote_list_id,
                    items,
                    after=(previous.media_type, previous.as_mdblist_id()),
                )
        except MdbListError:
            return ReorderOutcome(
                attempted=True,
                succeeded=False,
                chunks=index,
                not_found=not_found,
                warnings=("ORDER_NOT_ENFORCED",),
            )
        not_found += result.not_found
    warnings: list[str] = []
    if not_found:
        warnings.extend(["ORDER_NOT_ENFORCED", "ORDER_PARTIAL"])
    return ReorderOutcome(
        attempted=True,
        succeeded=not_found == 0,
        chunks=len(chunks),
        not_found=not_found,
        warnings=tuple(warnings),
    )
