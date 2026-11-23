"""Pydantic models for the catalog change feed (Phase 9)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class CatalogChangeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    media_id: uuid.UUID
    title: str
    year: int | None = None
    media_type: str
    provider_id: uuid.UUID
    provider_slug: str
    provider_name: str
    source_key: str
    source_label: str
    direction: Literal["ADDED", "REMOVED"]
    detected_at: datetime
    detected_at_rome: datetime
    collection_id: uuid.UUID
    collection_name: str
    collection_slug: str
    previous_snapshot_id: uuid.UUID
    current_snapshot_id: uuid.UUID
    season_number: int | None = None
    episode_number: int | None = None
    episode_event_type: str | None = None


class CatalogChangeCountersOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    added_today: int
    removed_today: int
    added_window: int
    removed_window: int


class CatalogChangesOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[CatalogChangeOut]
    total: int
    page: int
    page_size: int
    window: str
    generated_at: datetime
    counters: CatalogChangeCountersOut
