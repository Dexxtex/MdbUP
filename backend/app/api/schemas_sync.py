"""Pydantic request/response models for the sync endpoints (lane C)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.api.schemas_catalog import CollectionOut
from app.domain.commands import (
    ApproveRunIn,
    BindingCreateIn,
    BindingUpdateIn,
    PreviewRequest,
    StartRunIn,
    TargetCreateIn,
    ThresholdsIn,
)

__all__ = [
    "ApproveRunIn",
    "BindingCreateIn",
    "BindingUpdateIn",
    "PreviewRequest",
    "StartRunIn",
    "TargetCreateIn",
    "ThresholdsIn",
]


class TargetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    remote_list_id: str
    remote_slug: str | None = None
    remote_url: str | None = None
    name: str
    mediatype: str
    private: bool
    item_count: int | None = None
    last_verified_at: datetime | None = None
    last_remote_read_at: datetime | None = None
    capabilities: dict[str, Any] = Field(default_factory=dict)


class TargetListOut(BaseModel):
    items: list[TargetOut]
    total: int
    page: int = 1
    page_size: int = 25
    has_more: bool = False


class BindingOut(BaseModel):
    id: uuid.UUID
    collection_id: uuid.UUID
    target_id: uuid.UUID
    collection: CollectionOut | None = None
    target: TargetOut | None = None
    media_type: str
    mode: str
    schedule: str
    schedule_time: str | None = None
    schedule_cron: str
    schedule_interval_hours: int | None = None
    max_removal_pct: float
    max_removal_abs: int
    max_remove_count: int
    max_remove_percent: float
    thresholds: dict[str, float]
    preserve_order: bool
    reorder_enabled: bool
    schedule_policy: str
    require_review: bool
    enabled: bool
    policy_version: str | None = None
    policy_accepted_at: datetime | None = None
    created_at: datetime
    next_run_at: datetime | None = None
    last_run_id: uuid.UUID | None = None


class BindingListOut(BaseModel):
    items: list[BindingOut]
    total: int
    page: int = 1
    page_size: int = 25
    has_more: bool = False


class PreviewCountsOut(BaseModel):
    to_add: int = 0
    to_remove: int = 0
    unchanged: int = 0
    unresolved: int = 0
    unmapped_remote: int = 0
    remote_duplicates: int = 0


class PreviewBlockedOut(BaseModel):
    reason: str
    threshold: float | None = None
    observed: float | None = None


class PreviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    state: Literal["RUNNING", "READY", "BLOCKED", "FAILED"]
    counts: PreviewCountsOut
    blocked: PreviewBlockedOut | None = None
    sample: dict[str, Any] = Field(default_factory=dict)
    snapshot_id: uuid.UUID | None = None
    snapshot_hash: str | None = None
    plan_hash: str | None = None
    order_enforced: bool | None = None
    generated_at: datetime | None = None
    warnings: list[str] = Field(default_factory=list)


class PreviewAcceptedOut(BaseModel):
    preview_id: uuid.UUID


class RunCountersOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    planned: int = 0
    applied: int = 0
    skipped: int = 0
    not_found: int = 0
    failed: int = 0
    uncertain: int = 0


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    binding_id: uuid.UUID
    target_id: uuid.UUID
    status: str
    mode: str
    is_dry_run: bool
    trigger: str
    snapshot_id: uuid.UUID
    plan_hash: str | None = None
    snapshot_hash: str | None = None
    order_enforced: bool = False
    warnings: list[str] = Field(default_factory=list)
    counters: RunCountersOut
    source_item_count: int = 0
    remote_item_count: int = 0
    to_add_count: int = 0
    to_remove_count: int = 0
    added_count: int = 0
    removed_count: int = 0
    failed_count: int = 0
    uncertain_count: int = 0
    threshold_breached: bool = False
    requires_approval: bool = False
    approved_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    abort_reason: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    summary: dict[str, Any] = Field(default_factory=dict)
    collection_name: str | None = None
    provider_name: str | None = None
    target_name: str | None = None
    idempotency_key: str | None = None
    reconcile_required: bool = False
    parent_run_id: uuid.UUID | None = None
    created_at: datetime


class RunListOut(BaseModel):
    items: list[RunOut]
    total: int
    page: int = 1
    page_size: int = 25
    has_more: bool = False


class OperationMediaOut(BaseModel):
    title: str | None = None
    year: int | None = None
    media_type: str | None = None
    tmdb_id: int | None = None
    imdb_id: str | None = None


class OperationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_id: uuid.UUID
    action: str
    media_id: uuid.UUID | None = None
    media: OperationMediaOut | None = None
    status: str
    attempt: int
    error: str | None = None
    error_code: str | None = None
    remote_id: str | None = None
    batch_id: uuid.UUID | None = None
    http_status: int | None = None
    updated_at: datetime | None = None


class OperationListOut(BaseModel):
    items: list[OperationOut]
    total: int
    page: int = 1
    page_size: int = 100
    has_more: bool = False


class JobAcceptedOut(BaseModel):
    job_id: uuid.UUID


class RunAcceptedOut(BaseModel):
    run_id: uuid.UUID
    job_id: uuid.UUID | None = None
    status: str | None = None
