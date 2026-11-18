"""Validated command DTOs shared by the HTTP layer and use-case services.

These are transport-neutral input models. The FastAPI schemas re-export them so
the public API contract stays unchanged, while services never import
``app.api``.
"""

from __future__ import annotations

import re
import uuid
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.domain.enums import MediaType, SchedulePolicy, SyncMode

_SCHEDULE_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


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


class PreviewRequest(BaseModel):
    collection_id: uuid.UUID
    target_id: uuid.UUID | None = None
    mode: SyncMode | None = None
    thresholds: ThresholdsIn | None = None
    snapshot_id: uuid.UUID | None = None
    policy_version: str | None = Field(default=None, max_length=32)


class StartRunIn(BaseModel):
    dry_run: bool = False
    idempotency_key: str | None = Field(default=None, max_length=128)
    snapshot_id: uuid.UUID | None = None


class ApproveRunIn(BaseModel):
    plan_hash: str = Field(min_length=16, max_length=128)
    note: str | None = Field(default=None, max_length=500)


class CollectionCreateIn(BaseModel):
    # CUSTOM_FILTER derives the primary provider from the first source collection.
    provider_id: uuid.UUID | None = None
    media_type: Literal["MOVIE", "SHOW"]
    name: str = Field(min_length=3, max_length=300)
    slug: str = Field(min_length=3, max_length=200, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    source_key: Literal["tmdb", "justwatch", "combined"] = "tmdb"
    kind: Literal["CATALOG", "RECENTLY_ADDED", "CUSTOM_FILTER", "CHART", "UPCOMING"] = "CATALOG"
    # Only meaningful for source_key=combined.
    combine_mode: Literal["UNION", "INTERSECTION"] = "UNION"
    offer_types: list[Literal["FLATRATE", "RENT", "BUY", "ADS", "FREE"]] | None = None
    genre_ids: list[int] = Field(default_factory=list, max_length=20)
    exclude_genre_ids: list[int] = Field(default_factory=list, max_length=20)
    monetization_type: Literal["FLATRATE", "RENT", "BUY", "ADS", "FREE"] = "FLATRATE"
    window_days: int | None = Field(default=None, ge=1, le=90)
    source_collection_id: uuid.UUID | None = None
    source_collection_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)
    shared_snapshot_collection_id: uuid.UUID | None = None
    min_vote_average: float | None = Field(default=None, ge=0, le=10)
    min_vote_count: int | None = Field(default=None, ge=0)
    year_from: int | None = Field(default=None, ge=1900, le=2100)
    year_to: int | None = Field(default=None, ge=1900, le=2100)
    original_language: str | None = Field(default=None, min_length=2, max_length=8)
    local_sort_by: Literal[
        "vote_average.desc", "vote_count.desc", "release_date.desc", "title.asc", "popularity.desc"
    ] = "vote_average.desc"
    description: str | None = Field(default=None, max_length=1000)
    is_active: bool = True

    @field_validator("genre_ids", "exclude_genre_ids")
    @classmethod
    def _unique_genres(cls, value: list[int]) -> list[int]:
        return list(dict.fromkeys(value))

    @field_validator("source_collection_ids")
    @classmethod
    def _unique_sources(cls, value: list[uuid.UUID]) -> list[uuid.UUID]:
        return list(dict.fromkeys(value))

    @field_validator("original_language")
    @classmethod
    def _language_code(cls, value: str | None) -> str | None:
        return value.strip().lower() if value else None

    @model_validator(mode="after")
    def _year_range(self) -> CollectionCreateIn:
        if (
            self.year_from is not None
            and self.year_to is not None
            and self.year_from > self.year_to
        ):
            raise ValueError("year_from non può superare year_to.")
        return self


class CollectionUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=300)
    # The source of an existing collection is immutable; it is validated, not changed.
    source_key: Literal["tmdb", "justwatch", "combined"] | None = None
    kind: Literal["CATALOG", "RECENTLY_ADDED", "CUSTOM_FILTER", "CHART", "UPCOMING"] | None = None
    combine_mode: Literal["UNION", "INTERSECTION"] | None = None
    offer_types: list[Literal["FLATRATE", "RENT", "BUY", "ADS", "FREE"]] | None = None
    genre_ids: list[int] | None = Field(default=None, max_length=20)
    exclude_genre_ids: list[int] | None = Field(default=None, max_length=20)
    monetization_type: Literal["FLATRATE", "RENT", "BUY", "ADS", "FREE"] | None = None
    window_days: int | None = Field(default=None, ge=1, le=90)
    source_collection_id: uuid.UUID | None = None
    source_collection_ids: list[uuid.UUID] | None = Field(default=None, max_length=20)
    shared_snapshot_collection_id: uuid.UUID | None = None
    min_vote_average: float | None = Field(default=None, ge=0, le=10)
    min_vote_count: int | None = Field(default=None, ge=0)
    year_from: int | None = Field(default=None, ge=1900, le=2100)
    year_to: int | None = Field(default=None, ge=1900, le=2100)
    original_language: str | None = Field(default=None, min_length=2, max_length=8)
    local_sort_by: (
        Literal[
            "vote_average.desc",
            "vote_count.desc",
            "release_date.desc",
            "title.asc",
            "popularity.desc",
        ]
        | None
    ) = None
    description: str | None = Field(default=None, max_length=1000)
    is_active: bool | None = None

    @field_validator("genre_ids", "exclude_genre_ids")
    @classmethod
    def _unique_genres(cls, value: list[int] | None) -> list[int] | None:
        return list(dict.fromkeys(value)) if value is not None else None

    @field_validator("source_collection_ids")
    @classmethod
    def _unique_sources(cls, value: list[uuid.UUID] | None) -> list[uuid.UUID] | None:
        return list(dict.fromkeys(value)) if value is not None else None

    @field_validator("original_language")
    @classmethod
    def _language_code(cls, value: str | None) -> str | None:
        return value.strip().lower() if value else None

    @model_validator(mode="after")
    def _year_range(self) -> CollectionUpdateIn:
        if (
            self.year_from is not None
            and self.year_to is not None
            and self.year_from > self.year_to
        ):
            raise ValueError("year_from non può superare year_to.")
        return self
