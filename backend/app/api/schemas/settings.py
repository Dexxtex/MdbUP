"""Impostazioni applicative leggibili/aggiornabili via API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SettingItemOut(BaseModel):
    key: str
    value: Any
    description: str
    updated_at: datetime | None = None


class SettingsOut(BaseModel):
    items: list[SettingItemOut]


class SettingsPatchRequest(BaseModel):
    items: dict[str, Any] = Field(min_length=1)
