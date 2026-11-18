"""Configuration portability endpoints (admin only, secrets excluded)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import (
    get_client_ip,
    get_db_dep,
    get_request_id,
    get_settings_dep,
    require_admin,
    require_csrf,
)
from app.core.config import Settings
from app.db.models import AppUser
from app.domain.enums import AuditActorType
from app.repositories import audit
from app.services import config_portability

router = APIRouter(prefix="/config", tags=["config"])


@router.get("/export", summary="Esporta la configurazione senza segreti")
def export_config(
    db: Session = Depends(get_db_dep),
    settings: Settings = Depends(get_settings_dep),
    admin: AppUser = Depends(require_admin),
) -> dict[str, Any]:
    payload = config_portability.export_config(db, settings)
    audit.record(
        db,
        action="config_exported",
        entity_type="app_config",
        entity_id="json",
        actor_user_id=admin.id,
        actor_type=AuditActorType.USER,
        after={"version": payload["version"]},
    )
    db.commit()
    return payload


@router.post(
    "/import",
    dependencies=[Depends(require_csrf)],
    summary="Importa una configurazione JSON (upsert, nessun segreto)",
)
def import_config(
    request: Request,
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db_dep),
    settings: Settings = Depends(get_settings_dep),
    admin: AppUser = Depends(require_admin),
) -> dict[str, int]:
    result = config_portability.import_config(db, settings, payload, actor_user_id=admin.id)
    audit.record(
        db,
        action="config_imported",
        entity_type="app_config",
        entity_id="json",
        actor_user_id=admin.id,
        actor_type=AuditActorType.USER,
        after={**result, "ip": get_client_ip(request), "request_id": get_request_id(request)},
    )
    db.commit()
    return result
