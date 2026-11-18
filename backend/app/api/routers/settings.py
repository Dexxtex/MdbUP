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
from app.api.errors import ValidationError
from app.core.config import Settings
from app.db.models import AppUser
from app.domain.enums import AuditActorType
from app.repositories import audit
from app.repositories import settings as settings_repo

router = APIRouter(prefix="/settings", tags=["settings"])


def _render(db: Session, settings: Settings) -> schemas.SettingsOut:
    return schemas.SettingsOut(
        items=[
            schemas.SettingItemOut(
                key=spec.key,
                value=value,
                description=spec.description,
                updated_at=updated_at,
            )
            for spec, value, updated_at in settings_repo.resolved_items(db, settings)
        ]
    )


@router.get("", response_model=schemas.SettingsOut, summary="Impostazioni applicative")
def read_settings(
    db: Session = Depends(get_db_dep),
    settings: Settings = Depends(get_settings_dep),
    _admin: AppUser = Depends(require_admin),
) -> schemas.SettingsOut:
    return _render(db, settings)


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
    validated: dict[str, object] = {}
    for key, value in payload.items.items():
        spec = settings_repo.SETTING_SPECS.get(key)
        if spec is None:
            raise ValidationError(
                f"Impostazione sconosciuta: '{key}'.",
                code="VALIDATION_UNKNOWN_SETTING",
                details={"key": key},
            )
        try:
            validated[key] = settings_repo.coerce_value(spec, value)
        except settings_repo.InvalidSettingValueError as exc:
            raise ValidationError(
                str(exc), code="VALIDATION_INVALID_SETTING", details={"key": key}
            ) from exc
    current = settings_repo.get_all(db)
    before = {key: current[key].value for key in validated if key in current}
    for key, value in validated.items():
        settings_repo.set_value(db, key, value, updated_by=admin.id)
    audit.record(
        db,
        action="settings_updated",
        entity_type="app_setting",
        entity_id=",".join(sorted(validated)),
        actor_user_id=admin.id,
        actor_type=AuditActorType.USER,
        before=before,
        after=validated,
        ip=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_id=get_request_id(request),
    )
    db.commit()
    return _render(db, settings)
