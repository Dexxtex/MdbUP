"""Pydantic request/response models for the sync endpoints (lane C)."""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.api.schemas_catalog import CollectionOut
from app.domain.enums import MediaType, SchedulePolicy, SyncMode

_SCHEDULE_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


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


class TargetCreateIn(BaseModel):
    """``mode=new`` creates a list; ``mode=existing`` links a numeric list id."""

    mode: Literal["new", "existing"] = "new"
    name: str | None = Field(default=None, min_length=3, max_length=80)
    private: bool = False
    media_type: MediaType
    remote_list_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _validate_mode(self) -> TargetCreateIn:
        if self.mode == "new" and not self.name:
            raise ValueError("Il nome della lista è obbligatorio per mode=new.")
        if self.mode == "existing" and self.remote_list_id is None:
            raise ValueError("remote_list_id è obbligatorio per mode=existing.")
        return self


class ThresholdsIn(BaseModel):
    max_removal_pct: float = Field(default=10.0, ge=0, le=100)
    max_removal_abs: int = Field(default=50, ge=0, le=100_000)
    max_addition_pct: float = Field(default=50.0, ge=0, le=100)


class BindingCreateIn(BaseModel):
    collection_id: uuid.UUID
    target_id: uuid.UUID
    # JustWatch is an aggregator without provider-declared dates: the operator
    # must accept that explicitly. Such bindings are always created disabled.
    justwatch_policy_accepted: bool = False
    mode: SyncMode = SyncMode.MIRROR
    schedule: Literal["MANUAL", "DAILY", "WEEKLY"] = "MANUAL"
    schedule_time: str | None = None
    thresholds: ThresholdsIn = Field(default_factory=ThresholdsIn)
    preserve_order: bool = False
    reorder_enabled: bool = True
    schedule_policy: SchedulePolicy = SchedulePolicy.AUTO_APPLY_IF_SAFE
    require_review: bool = True
    enabled: bool = False
    policy_version: str | None = Field(default=None, max_length=32)
    max_plan_age_minutes: int = Field(default=60, ge=1, le=1440)
    auto_apply_max_removals: int = Field(default=5, ge=0, le=1000)
    auto_apply_max_removal_ratio: float = Field(default=2.0, ge=0, le=100)

    @model_validator(mode="after")
    def _validate_schedule(self) -> BindingCreateIn:
        if self.schedule != "MANUAL" and (
            not self.schedule_time or not _SCHEDULE_TIME.match(self.schedule_time)
        ):
            raise ValueError("schedule_time deve essere nel formato HH:MM.")
        if self.mode is SyncMode.MIRROR and (
            self.thresholds.max_removal_pct == 0 and self.thresholds.max_removal_abs == 0
        ):
            raise ValueError("MIRROR richiede almeno una soglia di rimozione positiva.")
        return self


class BindingUpdateIn(BaseModel):
    """Partial update; omitted fields keep their current value."""

    mode: SyncMode | None = None
    schedule: Literal["MANUAL", "DAILY", "WEEKLY", "INTERVAL", "CRON"] | None = None
    schedule_time: str | None = None
    schedule_interval_hours: int | None = Field(default=None, ge=1, le=24 * 30)
    schedule_cron: str | None = Field(default=None, max_length=64)
    thresholds: ThresholdsIn | None = None
    max_remove_count: int | None = Field(default=None, ge=0, le=100_000)
    max_remove_percent: float | None = Field(default=None, ge=0, le=100)
    enabled: bool | None = None
    policy_version: str | None = Field(default=None, max_length=32)
    max_plan_age_minutes: int | None = Field(default=None, ge=1, le=1440)
    auto_apply_max_removals: int | None = Field(default=None, ge=0, le=1000)
    auto_apply_max_removal_ratio: float | None = Field(default=None, ge=0, le=100)
    preserve_order: bool | None = None
    reorder_enabled: bool | None = None
    schedule_policy: SchedulePolicy | None = None
    require_review: bool | None = None
    target_private: bool | None = None

    @model_validator(mode="after")
    def _validate_schedule_shape(self) -> BindingUpdateIn:
        if self.schedule in ("DAILY", "WEEKLY") and (
            not self.schedule_time or not _SCHEDULE_TIME.match(self.schedule_time)
        ):
            raise ValueError("schedule_time deve essere nel formato HH:MM.")
        if self.schedule == "INTERVAL" and self.schedule_interval_hours is None:
            raise ValueError("schedule_interval_hours è obbligatorio per schedule=INTERVAL.")
        if self.schedule == "CRON" and not self.schedule_cron:
            raise ValueError("schedule_cron è obbligatorio per schedule=CRON.")
        return self


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


class PreviewRequest(BaseModel):
    collection_id: uuid.UUID
    target_id: uuid.UUID | None = None
    mode: SyncMode | None = None
    thresholds: ThresholdsIn | None = None
    snapshot_id: uuid.UUID | None = None
    policy_version: str | None = Field(default=None, max_length=32)


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


class StartRunIn(BaseModel):
    dry_run: bool = False
    idempotency_key: str | None = Field(default=None, max_length=128)
    snapshot_id: uuid.UUID | None = None


class ApproveRunIn(BaseModel):
    plan_hash: str = Field(min_length=16, max_length=128)
    note: str | None = Field(default=None, max_length=500)


class JobAcceptedOut(BaseModel):
    job_id: uuid.UUID


class RunAcceptedOut(BaseModel):
    run_id: uuid.UUID
    job_id: uuid.UUID | None = None
    status: str | None = None
