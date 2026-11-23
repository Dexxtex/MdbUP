"""Errori HTTP: envelope uniforme dei problemi applicativi e tecnici."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ErrorBody(BaseModel):
    code: str
    category: str
    message: str
    retryable: bool
    request_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    retry_after_s: int | None = None


class ErrorEnvelope(BaseModel):
    error: ErrorBody
