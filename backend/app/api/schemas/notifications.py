"""Notification channel request/response models."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

NotificationKind = Literal["WEBHOOK", "TELEGRAM", "DISCORD"]


class NotificationChannelOut(BaseModel):
    id: uuid.UUID
    name: str
    kind: NotificationKind
    enabled: bool
    events: list[str]
    config: dict[str, Any] = Field(default_factory=dict)
    secret_configured: bool = False
    masked_hint: str | None = None
    last_sent_at: datetime | None = None
    last_status: str | None = None
    last_error: str | None = None
    retry_count: int = 0
    next_retry_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class NotificationChannelListOut(BaseModel):
    items: list[NotificationChannelOut]


class NotificationChannelCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: NotificationKind
    secret: str = Field(min_length=1, max_length=4096)
    events: list[str] = Field(default_factory=list, max_length=20)
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class NotificationChannelUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    secret: str | None = Field(default=None, max_length=4096)
    events: list[str] | None = Field(default=None, max_length=20)
    config: dict[str, Any] | None = None
    enabled: bool | None = None


class NotificationTestOut(BaseModel):
    ok: bool
    status_code: int | None = None
    message: str
    latency_ms: int | None = None
