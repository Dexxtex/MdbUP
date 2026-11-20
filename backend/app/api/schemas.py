"""Pydantic request/response models for the foundation endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


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


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    is_admin: bool
    created_at: datetime
    last_login_at: datetime | None = None


class BootstrapRequest(BaseModel):
    token: str = Field(min_length=1, max_length=512)
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class BootstrapOut(BaseModel):
    user: UserOut


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class SessionOut(BaseModel):
    user: UserOut
    csrf_token: str


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=1, max_length=128)


class HealthOut(BaseModel):
    status: Literal["ok"] = "ok"
    version: str


class ReadinessOut(BaseModel):
    status: Literal["ok", "degraded"]
    checks: dict[str, bool]


ServiceState = Literal["OK", "MISSING_CREDENTIAL", "DEGRADED", "ERROR", "DISABLED"]


class SystemHealthOut(BaseModel):
    api: bool
    database: bool
    redis: bool
    worker: bool
    tmdb: ServiceState
    mdblist: ServiceState
    tvdb: ServiceState


class BackupStatusOut(BaseModel):
    last_valid_at: datetime | None = None
    file: str | None = None
    status: str = "MISSING"
    age_hours: float | None = None


class UpcomingRunOut(BaseModel):
    binding_id: uuid.UUID
    collection_name: str
    target_name: str
    next_run_at: datetime


class CatalogAcquisitionOut(BaseModel):
    collection_id: uuid.UUID
    collection_name: str
    provider_name: str
    next_acquire_at: datetime


class StorageStatusOut(BaseModel):
    snapshot_bytes: int = 0
    run_bytes: int = 0
    total_bytes: int = 0
    database_bytes: int = 0
    snapshot_rows: int = 0
    snapshot_item_rows: int = 0
    run_rows: int = 0
    size_supported: bool = False


class SystemStatusOut(BaseModel):
    health: SystemHealthOut
    queues: dict[str, int]
    runs: dict[str, int]
    api_usage: dict[str, dict[str, int]]
    backup: BackupStatusOut
    pending_approvals: int
    upcoming: list[UpcomingRunOut]
    catalog_acquisitions: list[CatalogAcquisitionOut]
    storage: StorageStatusOut


class SettingItemOut(BaseModel):
    key: str
    value: Any
    description: str
    updated_at: datetime | None = None


class SettingsOut(BaseModel):
    items: list[SettingItemOut]


class SettingsPatchRequest(BaseModel):
    items: dict[str, Any] = Field(min_length=1)


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
