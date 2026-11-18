"""Pydantic response models for the catalog/dashboard endpoints (lane B)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.domain.commands import CollectionCreateIn, CollectionUpdateIn

__all__ = ["CollectionCreateIn", "CollectionUpdateIn"]


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
