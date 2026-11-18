"""Use cases for runtime settings (render, validation and audit)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domain.enums import AuditActorType
from app.domain.errors import ValidationError
from app.repositories import audit
from app.repositories import settings as settings_repo


@dataclass(frozen=True)
class SettingView:
    key: str
    value: Any
    description: str
    updated_at: datetime | None


def list_settings(db: Session, settings: Settings) -> list[SettingView]:
    return [
        SettingView(
            key=spec.key,
            value=value,
            description=spec.description,
            updated_at=updated_at,
        )
        for spec, value, updated_at in settings_repo.resolved_items(db, settings)
    ]


def update_settings(
    db: Session,
    settings: Settings,
    values: dict[str, Any],
    *,
    actor_user_id: uuid.UUID,
    ip: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
) -> list[SettingView]:
    """Validate, persist and audit a settings patch."""
    validated: dict[str, object] = {}
    for key, value in values.items():
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
        settings_repo.set_value(db, key, value, updated_by=actor_user_id)
    audit.record(
        db,
        action="settings_updated",
        entity_type="app_setting",
        entity_id=",".join(sorted(validated)),
        actor_user_id=actor_user_id,
        actor_type=AuditActorType.USER,
        before=before,
        after=validated,
        ip=ip,
        user_agent=user_agent,
        request_id=request_id,
    )
    db.commit()
    return list_settings(db, settings)
