"""Sistema: liveness, readiness, metriche e stato dei servizi/risorse."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


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
