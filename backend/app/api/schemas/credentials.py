"""Credenziali delle fonti: elenco mascherato, scrittura e verifica."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class CredentialOut(BaseModel):
    kind: str
    configured: bool
    masked_hint: str | None = None
    key_version: int | None = None
    status: Literal["CONFIGURED", "MISSING", "UNAVAILABLE"]
    updated_at: datetime | None = None
    last_verified_at: datetime | None = None


class CredentialListOut(BaseModel):
    items: list[CredentialOut]


class CredentialSecretIn(BaseModel):
    value: str = Field(min_length=1, max_length=4096)


class CredentialVerifyOut(BaseModel):
    kind: str
    ok: bool
    status_code: int | None = None
    latency_ms: int | None = None
    message: str
