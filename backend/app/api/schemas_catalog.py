"""Pydantic response models for the catalog/dashboard endpoints (lane B)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    quality: str
    is_valid: bool
    started_at: datetime
    finished_at: datetime | None = None
    pages_expected: int | None = None
    pages_fetched: int
    items_count: int
    resolved_count: int
    unresolved_count: int
    duplicate_count: int
    error_count: int
    checksum: str | None = None
    invalid_reason: str | None = None
    last_verified_at: datetime | None = None


class CollectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    name: str
    provider_id: uuid.UUID
    provider_slug: str | None = None
    provider_name: str | None = None
    source_id: uuid.UUID
    source_key: str | None = None
    country_code: str
    media_type: str
    kind: str
    origin: str
    date_basis: str
    source_label: str | None = None
    description: str | None = None
    filters: dict[str, Any] = {}
    quality_flags: dict[str, Any] = {}
    provider_names: list[str] = []
    is_local_filter: bool = False
    is_multi_provider: bool = False
    offer_types: list[str]
    sort_mode: str
    is_active: bool
    last_valid_snapshot_id: uuid.UUID | None = None
    latest_snapshot: SnapshotOut | None = None
    last_valid_snapshot: SnapshotOut | None = None


class CollectionListOut(BaseModel):
    items: list[CollectionOut]
    total: int


class GenreOut(BaseModel):
    id: int
    name: str


class GenreListOut(BaseModel):
    media_type: str
    items: list[GenreOut]


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


class SnapshotListOut(BaseModel):
    items: list[SnapshotOut]
    total: int
    page: int
    page_size: int


class SnapshotItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    position: int
    media_id: uuid.UUID | None = None
    media_type: str | None = None
    tmdb_id: int | None = None
    imdb_id: str | None = None
    title: str | None = None
    release_year: int | None = None
    resolution_status: str
    resolution_error: str | None = None
    source_item_id: str | None = None
    date_basis: str
    source_date_created: date | None = None
    availability_status: str | None = None
    source_offer_types: list[str] = []


class SnapshotItemListOut(BaseModel):
    items: list[SnapshotItemOut]
    total: int
    page: int
    page_size: int


class ProviderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    name: str
    kind: str
    logo_url: str | None = None
    website_url: str | None = None
    country_code: str
    tmdb_provider_id: str | None = None
    tmdb_provider_id_movie: str | None = None
    tmdb_provider_id_tv: str | None = None
    mapping_verified: bool
    mapping_verified_movie: bool = False
    mapping_verified_tv: bool = False
    justwatch_provider_id: str | None = None
    justwatch_verified: bool = False
    justwatch_movie_verified: bool = False
    justwatch_tv_verified: bool = False
    justwatch_monetization_types: list[str] = []
    collections_count: int
    movie_collections: int
    show_collections: int


class ProviderListOut(BaseModel):
    items: list[ProviderOut]
    total: int


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    key: str
    name: str
    type: str
    base_url: str | None = None
    status: str
    status_message: str | None = None
    is_official: bool
    origin_default: str
    requires_contract: bool
    capabilities: dict[str, Any]
    credential_configured: bool
    connector_available: bool
    justwatch: dict[str, Any] | None = None
    last_healthcheck_at: datetime | None = None
    last_success_at: datetime | None = None


class SourceListOut(BaseModel):
    items: list[SourceOut]


class EpisodeEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    media_id: uuid.UUID
    title: str | None = None
    event_type: str
    season_number: int
    episode_number: int | None = None
    occurred_at: datetime | None = None
    source_key: str | None = None


class EpisodeEventListOut(BaseModel):
    items: list[EpisodeEventOut]
    total: int


class SourceHealthcheckOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source_id: uuid.UUID
    source_key: str
    ok: bool
    status: str
    latency_ms: int | None = None
    message: str
    checked_at: datetime


class AcquireOut(BaseModel):
    job_id: uuid.UUID
    collection_id: uuid.UUID
    status: str
    snapshot_id: uuid.UUID | None = None


class DashboardAlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    severity: str
    message: str
    details: dict[str, Any]


class DashboardOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    counters: dict[str, int]
    alerts: list[DashboardAlertOut]
    recent_snapshots: list[dict[str, Any]]
    recent_jobs: list[dict[str, Any]]
    recent_sync_runs: list[dict[str, Any]]
    sources: list[dict[str, Any]]
    api_usage: dict[str, Any] = {}
