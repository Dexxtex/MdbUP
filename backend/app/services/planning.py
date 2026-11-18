"""Pure sync planning: media keys, MIRROR/APPEND_ONLY diff and ``plan_hash``.

The planner never touches the database or the network. It receives the snapshot
metadata, the resolved source items and the remote list items, and returns a
``SyncPlan`` that the executor persists and applies. Unresolved source items and
unmapped remote items never enter the diff; remote duplicates are reported but
never removed, because ``remove`` could delete every occurrence.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from app.db.models import CollectionSnapshot, SyncBinding
from app.domain.enums import MediaType, ResolutionStatus, SyncMode
from app.integrations.mdblist.models import MdbListId, MdbListListItem
from app.services.thresholds import (
    ThresholdPolicy,
    ThresholdResult,
    evaluate_thresholds,
    threshold_summary,
)

PLANNER_VERSION = "planning-v1"
DEFAULT_REORDER_CHUNK = 1000
SAMPLE_SIZE = 50


@dataclass(frozen=True, order=True)
class MediaKey:
    """Identity of one media item: media type first, then the external id."""

    media_type: str
    id_type: str
    value: str

    def label(self) -> str:
        return f"{self.media_type}:{self.id_type}:{self.value}"

    def as_mdblist_id(self) -> MdbListId:
        if self.id_type == "tmdb":
            return MdbListId(tmdb=int(self.value))
        return MdbListId(imdb=self.value)


@dataclass(frozen=True)
class SourceItem:
    """A resolved snapshot item as needed by the planner."""

    media_type: str
    tmdb_id: int | None
    imdb_id: str | None
    media_id: uuid.UUID | None
    resolution_status: str = ResolutionStatus.RESOLVED.value
    title: str | None = None
    year: int | None = None
    suppressed: bool = False


@dataclass(frozen=True)
class SyncPlan:
    mode: str
    to_add: tuple[MediaKey, ...]
    to_remove: tuple[MediaKey, ...]
    unchanged: tuple[MediaKey, ...]
    unresolved: tuple[dict[str, Any], ...]
    unmapped_remote: tuple[dict[str, Any], ...]
    remote_duplicates: tuple[MediaKey, ...]
    suppressed: tuple[MediaKey, ...]
    desired_order: tuple[MediaKey, ...]
    reorder_needed: bool
    plan_hash: str
    snapshot_hash: str
    order_enforced: bool
    source_item_count: int
    remote_item_count: int
    blocked: bool
    block_reason: str | None
    warnings: tuple[str, ...]
    threshold: ThresholdResult
    policy_version: str

    @property
    def has_changes(self) -> bool:
        return bool(self.to_add or self.to_remove)


def build_media_key(media_type: str, tmdb_id: int | None, imdb_id: str | None) -> MediaKey | None:
    """``(media_type, tmdb_id)`` first, ``(media_type, imdb_id)`` as fallback."""
    if media_type not in (MediaType.MOVIE.value, MediaType.SHOW.value):
        return None
    if tmdb_id is not None:
        return MediaKey(media_type=media_type, id_type="tmdb", value=str(tmdb_id))
    if imdb_id:
        return MediaKey(media_type=media_type, id_type="imdb", value=imdb_id)
    return None


def source_key(item: SourceItem) -> MediaKey | None:
    if item.resolution_status != ResolutionStatus.RESOLVED.value or item.media_id is None:
        return None
    return build_media_key(item.media_type, item.tmdb_id, item.imdb_id)


def remote_key(item: MdbListListItem) -> MediaKey | None:
    return build_media_key(item.mediatype, item.tmdb_id, item.imdb_id)


def snapshot_hash_for(keys: Sequence[MediaKey]) -> str:
    """SHA-256 of the normalized, sorted snapshot keys."""
    payload = "\n".join(sorted(key.label() for key in keys))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compute_plan_hash(
    *,
    mode: str,
    snapshot_hash: str,
    to_add: Sequence[MediaKey],
    to_remove: Sequence[MediaKey],
    policy_version: str,
) -> str:
    payload = {
        "mode": mode,
        "snapshot_hash": snapshot_hash,
        "to_add": sorted(key.label() for key in to_add),
        "to_remove": sorted(key.label() for key in to_remove),
        "policy_version": policy_version,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def plan_sync(
    *,
    mode: SyncMode | str,
    snapshot: CollectionSnapshot,
    source_items: Sequence[SourceItem],
    remote_items: Sequence[MdbListListItem],
    binding: SyncBinding,
    policy_version: str,
    order_enforced: bool = True,
) -> SyncPlan:
    """Build the diff and the safety evaluation for one run."""
    sync_mode = SyncMode(str(mode))
    policy = ThresholdPolicy.from_binding(binding)

    source_order: list[MediaKey] = []
    source_set: set[MediaKey] = set()
    unresolved: list[dict[str, Any]] = []
    suppressed: list[MediaKey] = []
    seen_unresolved: set[tuple[str, str]] = set()
    for item in source_items:
        key = source_key(item)
        if key is None:
            marker = (item.media_type, item.imdb_id or str(item.tmdb_id) or (item.title or ""))
            if marker not in seen_unresolved:
                seen_unresolved.add(marker)
                unresolved.append(
                    {
                        "media_type": item.media_type,
                        "tmdb_id": item.tmdb_id,
                        "imdb_id": item.imdb_id,
                        "title": item.title,
                        "year": item.year,
                        "reason": "UNRESOLVED",
                    }
                )
            continue
        if item.suppressed:
            if key not in suppressed:
                suppressed.append(key)
            continue
        if key in source_set:
            continue
        source_set.add(key)
        source_order.append(key)

    remote_order: list[MediaKey] = []
    remote_set: set[MediaKey] = set()
    remote_duplicates: list[MediaKey] = []
    unmapped_remote: list[dict[str, Any]] = []
    for item in remote_items:
        key = remote_key(item)
        if key is None:
            unmapped_remote.append(
                {
                    "mediatype": item.mediatype,
                    "title": item.title,
                    "tmdb_id": item.tmdb_id,
                    "imdb_id": item.imdb_id,
                    "rank": item.rank,
                }
            )
            continue
        if key in remote_set:
            if key not in remote_duplicates:
                remote_duplicates.append(key)
            continue
        remote_set.add(key)
        remote_order.append(key)

    to_add = tuple(key for key in source_order if key not in remote_set)
    if sync_mode is SyncMode.MIRROR:
        to_remove = tuple(key for key in remote_order if key not in source_set)
    else:
        to_remove = ()
    unchanged = tuple(key for key in source_order if key in remote_set)

    threshold = evaluate_thresholds(
        to_add_count=len(to_add),
        to_remove_count=len(to_remove),
        remote_count=len(remote_set),
        policy=policy,
    )

    block_reason = _block_reason(sync_mode, snapshot, unresolved)
    warnings: list[str] = []
    if snapshot.quality == "WARNINGS":
        warnings.append("SNAPSHOT_WARNINGS")
    if unresolved:
        warnings.append("UNRESOLVED_ITEMS_SKIPPED")
    if unmapped_remote:
        warnings.append("UNMAPPED_REMOTE_ITEMS")
    if remote_duplicates:
        warnings.append("REMOTE_DUPLICATES")
    if suppressed:
        warnings.append("SUPPRESSED_MEDIA_SKIPPED")

    reorder_needed = False
    desired_order: tuple[MediaKey, ...] = ()
    if binding.preserve_order and source_order:
        desired_order = tuple(source_order)
        current_existing = tuple(key for key in remote_order if key in source_set)
        reorder_needed = desired_order != current_existing or bool(to_add)
        if reorder_needed and not binding.reorder_enabled:
            warnings.append("ORDER_NOT_ENFORCED")
    effective_order_enforced = bool(
        order_enforced
        and (not reorder_needed or (binding.preserve_order and binding.reorder_enabled))
    )

    snapshot_hash = snapshot_hash_for(source_order)
    plan_hash = compute_plan_hash(
        mode=sync_mode.value,
        snapshot_hash=snapshot_hash,
        to_add=to_add,
        to_remove=to_remove,
        policy_version=policy_version,
    )
    return SyncPlan(
        mode=sync_mode.value,
        to_add=to_add,
        to_remove=to_remove,
        unchanged=unchanged,
        unresolved=tuple(unresolved),
        unmapped_remote=tuple(unmapped_remote),
        remote_duplicates=tuple(remote_duplicates),
        suppressed=tuple(suppressed),
        desired_order=desired_order,
        reorder_needed=reorder_needed,
        plan_hash=plan_hash,
        snapshot_hash=snapshot_hash,
        order_enforced=effective_order_enforced,
        source_item_count=len(source_order),
        remote_item_count=len(remote_set),
        blocked=block_reason is not None,
        block_reason=block_reason,
        warnings=tuple(warnings),
        threshold=threshold,
        policy_version=policy_version,
    )


def _block_reason(
    mode: SyncMode,
    snapshot: CollectionSnapshot,
    unresolved: Sequence[dict[str, Any]],
) -> str | None:
    """Policy gate: an invalid or empty snapshot never authorizes a run."""
    if snapshot.status != "COMPLETE":
        return "SNAPSHOT_INCOMPLETE"
    if snapshot.items_count == 0:
        return "SNAPSHOT_EMPTY"
    if mode is SyncMode.MIRROR:
        if not snapshot.is_valid:
            return "SNAPSHOT_NOT_VALID_FOR_MIRROR"
        if snapshot.unresolved_count > 0 or unresolved:
            return "SNAPSHOT_UNRESOLVED_ITEMS"
    return None


def reorder_chunks(
    keys: Sequence[MediaKey], *, chunk_size: int = DEFAULT_REORDER_CHUNK
) -> list[list[MediaKey]]:
    """Split the desired order into MDBList-sized reorder calls."""
    if chunk_size < 1:
        raise ValueError("chunk_size deve essere positivo.")
    return [list(keys[index : index + chunk_size]) for index in range(0, len(keys), chunk_size)]


def plan_summary(plan: SyncPlan) -> dict[str, Any]:
    """JSON-safe plan view persisted in ``sync_run.summary``."""
    return {
        "planner_version": PLANNER_VERSION,
        "mode": plan.mode,
        "blocked": plan.blocked,
        "block_reason": plan.block_reason,
        "to_add_count": len(plan.to_add),
        "to_remove_count": len(plan.to_remove),
        "unchanged_count": len(plan.unchanged),
        "unresolved_count": len(plan.unresolved),
        "unmapped_remote_count": len(plan.unmapped_remote),
        "remote_duplicates_count": len(plan.remote_duplicates),
        "suppressed_count": len(plan.suppressed),
        "source_item_count": plan.source_item_count,
        "remote_item_count": plan.remote_item_count,
        "reorder_needed": plan.reorder_needed,
        "desired_order": [key.label() for key in plan.desired_order],
        "order_enforced": plan.order_enforced,
        "plan_hash": plan.plan_hash,
        "snapshot_hash": plan.snapshot_hash,
        "policy_version": plan.policy_version,
        "warnings": list(plan.warnings),
        "thresholds": threshold_summary(plan.threshold),
        "to_add_sample": [key.label() for key in plan.to_add[:SAMPLE_SIZE]],
        "to_remove_sample": [key.label() for key in plan.to_remove[:SAMPLE_SIZE]],
        "unresolved_sample": list(plan.unresolved[:SAMPLE_SIZE]),
        "unmapped_remote_sample": list(plan.unmapped_remote[:SAMPLE_SIZE]),
        "remote_duplicates_sample": [key.label() for key in plan.remote_duplicates[:SAMPLE_SIZE]],
        "suppressed_sample": [key.label() for key in plan.suppressed[:SAMPLE_SIZE]],
    }


@dataclass
class PlanSamples:
    """Small, JSON-safe preview view of a plan (used by ``POST /previews``)."""

    to_add: list[str] = field(default_factory=list)
    to_remove: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    unresolved: list[dict[str, Any]] = field(default_factory=list)
    unmapped_remote: list[dict[str, Any]] = field(default_factory=list)
    remote_duplicates: list[str] = field(default_factory=list)


def plan_samples(plan: SyncPlan) -> PlanSamples:
    return PlanSamples(
        to_add=[key.label() for key in plan.to_add[:SAMPLE_SIZE]],
        to_remove=[key.label() for key in plan.to_remove[:SAMPLE_SIZE]],
        unchanged=[key.label() for key in plan.unchanged[:SAMPLE_SIZE]],
        unresolved=list(plan.unresolved[:SAMPLE_SIZE]),
        unmapped_remote=list(plan.unmapped_remote[:SAMPLE_SIZE]),
        remote_duplicates=[key.label() for key in plan.remote_duplicates[:SAMPLE_SIZE]],
    )
