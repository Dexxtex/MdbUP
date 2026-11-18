"""Runtime settings persistence and the registry of editable keys."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import AppSetting


@dataclass(frozen=True)
class SettingSpec:
    """A runtime-editable setting.

    ``default_attr`` names the ``Settings`` field that provides the default, so
    environment configuration stays the single source of truth.
    """

    key: str
    type: type
    default_attr: str
    description: str
    minimum: float | None = None
    maximum: float | None = None
    choices: tuple[str, ...] | None = None

    def default_value(self, settings: Settings) -> Any:
        return getattr(settings, self.default_attr)


SETTING_SPECS: dict[str, SettingSpec] = {
    spec.key: spec
    for spec in (
        SettingSpec(
            key="sync_batch_size",
            type=int,
            default_attr="sync_batch_size",
            description="Elementi per batch nelle scritture MDBList.",
            minimum=1,
            maximum=1000,
        ),
        SettingSpec(
            key="sync_max_removal_absolute",
            type=int,
            default_attr="sync_max_removal_absolute",
            description="Numero massimo di rimozioni per run senza approvazione.",
            minimum=0,
        ),
        SettingSpec(
            key="sync_max_removal_percent",
            type=float,
            default_attr="sync_max_removal_percent",
            description="Percentuale massima di rimozioni per run senza approvazione.",
            minimum=0,
            maximum=100,
        ),
        SettingSpec(
            key="sync_max_addition_percent",
            type=float,
            default_attr="sync_max_addition_percent",
            description="Percentuale massima di aggiunte per run senza approvazione.",
            minimum=0,
            maximum=100,
        ),
        SettingSpec(
            key="snapshot_retention_days",
            type=int,
            default_attr="snapshot_retention_days",
            description="Giorni di conservazione degli snapshot non più validi.",
            minimum=1,
        ),
        SettingSpec(
            key="http_timeout_seconds",
            type=int,
            default_attr="http_timeout_seconds",
            description="Timeout HTTP verso le fonti esterne.",
            minimum=1,
            maximum=300,
        ),
        SettingSpec(
            key="default_country_code",
            type=str,
            default_attr="default_country_code",
            description="Paese predefinito per collezioni e mapping provider.",
        ),
        SettingSpec(
            key="default_source",
            type=str,
            default_attr="default_source",
            description="Fonte predefinita per le nuove collezioni (JustWatch o TMDb).",
            choices=("justwatch", "tmdb"),
        ),
        SettingSpec(
            key="catalog_schedule_enabled",
            type=bool,
            default_attr="catalog_schedule_enabled",
            description=(
                "Abilita le acquisizioni scaglionate del catalogo JustWatch "
                "(una collezione alla volta, slot giornalieri)."
            ),
        ),
        SettingSpec(
            key="app_timezone",
            type=str,
            default_attr="app_timezone",
            description="Fuso orario usato per pianificazioni e visualizzazione.",
        ),
        SettingSpec(
            key="notifications_summary_enabled",
            type=bool,
            default_attr="notifications_summary_enabled",
            description="Abilita il riepilogo periodico delle sincronizzazioni.",
        ),
        SettingSpec(
            key="notifications_summary_hour",
            type=int,
            default_attr="notifications_summary_hour",
            description="Ora (0-23) del riepilogo periodico.",
            minimum=0,
            maximum=23,
        ),
    )
}


class InvalidSettingValueError(ValueError):
    """Raised when a value does not match the type/bounds of its spec."""


def coerce_value(spec: SettingSpec, value: Any) -> Any:
    """Validate and coerce ``value`` for ``spec``."""
    if spec.type is bool:
        if not isinstance(value, bool):
            raise InvalidSettingValueError(f"'{spec.key}' richiede un booleano.")
        return value
    if spec.type is int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise InvalidSettingValueError(f"'{spec.key}' richiede un intero.")
        coerced: Any = value
    elif spec.type is float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise InvalidSettingValueError(f"'{spec.key}' richiede un numero.")
        coerced = float(value)
    elif spec.type is str:
        if not isinstance(value, str) or not value.strip():
            raise InvalidSettingValueError(f"'{spec.key}' richiede una stringa non vuota.")
        coerced = value.strip()
    else:  # pragma: no cover - registry only uses the types above
        raise InvalidSettingValueError(f"Tipo non supportato per '{spec.key}'.")
    if spec.minimum is not None and coerced < spec.minimum:
        raise InvalidSettingValueError(f"'{spec.key}' deve essere >= {spec.minimum}.")
    if spec.maximum is not None and coerced > spec.maximum:
        raise InvalidSettingValueError(f"'{spec.key}' deve essere <= {spec.maximum}.")
    if spec.choices is not None and coerced not in spec.choices:
        raise InvalidSettingValueError(
            f"'{spec.key}' accetta solo i valori: {', '.join(spec.choices)}."
        )
    return coerced


def get_all(db: Session) -> dict[str, AppSetting]:
    return {row.key: row for row in db.scalars(select(AppSetting)).all()}


def set_value(
    db: Session,
    key: str,
    value: Any,
    *,
    updated_by: uuid.UUID | None = None,
) -> AppSetting:
    """Upsert a setting row (value is validated by the caller)."""
    row = db.get(AppSetting, key)
    if row is None:
        row = AppSetting(key=key, value=value, updated_by=updated_by)
        db.add(row)
    else:
        row.value = value
        row.updated_by = updated_by
    db.flush()
    return row


def effective_values(db: Session, settings: Settings) -> dict[str, Any]:
    """Return every known setting's effective value (DB override or default)."""
    return {spec.key: value for spec, value, _updated_at in resolved_items(db, settings)}


def resolved_items(
    db: Session, settings: Settings
) -> list[tuple[SettingSpec, Any, datetime | None]]:
    """Return every known setting with its effective value and last update time."""
    rows = get_all(db)
    items: list[tuple[SettingSpec, Any, datetime | None]] = []
    for spec in SETTING_SPECS.values():
        row = rows.get(spec.key)
        if row is None:
            items.append((spec, spec.default_value(settings), None))
        else:
            items.append((spec, row.value, row.updated_at))
    return items
