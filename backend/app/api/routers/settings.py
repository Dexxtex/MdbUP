"""Runtime settings endpoints (values are never secrets)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api import schemas
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
from app.services import settings as settings_service

router = APIRouter(prefix="/settings", tags=["settings"])


def _render(items: list[settings_service.SettingView]) -> schemas.SettingsOut:
    return schemas.SettingsOut(
        items=[
            schemas.SettingItemOut(
                key=item.key,
                value=item.value,
                description=item.description,
                updated_at=item.updated_at,
            )
            for item in items
        ]
    )


@router.get("", response_model=schemas.SettingsOut, summary="Impostazioni applicative")
def read_settings(
    db: Session = Depends(get_db_dep),
    settings: Settings = Depends(get_settings_dep),
    _admin: AppUser = Depends(require_admin),
) -> schemas.SettingsOut:
    return _render(settings_service.list_settings(db, settings))


@router.patch(
    "",
    response_model=schemas.SettingsOut,
    dependencies=[Depends(require_csrf)],
    summary="Aggiorna impostazioni applicative",
)
def patch_settings(
    payload: schemas.SettingsPatchRequest,
    request: Request,
    db: Session = Depends(get_db_dep),
    settings: Settings = Depends(get_settings_dep),
    admin: AppUser = Depends(require_admin),
) -> schemas.SettingsOut:
    return _render(
        settings_service.update_settings(
            db,
            settings,
            payload.items,
            actor_user_id=admin.id,
            ip=get_client_ip(request),
            user_agent=request.headers.get("user-agent"),
            request_id=get_request_id(request),
        )
    )
