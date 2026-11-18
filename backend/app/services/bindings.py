"""Binding use cases: schedule translation, policy acceptance and CRUD."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from croniter import croniter
from sqlalchemy.orm import Session

from app.api.errors import ConflictError, NotFoundError, ValidationError
from app.api.schemas_sync import BindingCreateIn, BindingUpdateIn
from app.core.config import Settings
from app.core.time import ensure_utc, utcnow
from app.db.models import MdblistTarget, SyncBinding
from app.domain.enums import AuditActorType, SyncMode
from app.repositories import audit
from app.repositories import bindings as bindings_repo
from app.repositories import collections as collections_repo
from app.repositories import targets as targets_repo
from app.services import collections as collections_service
from app.services import targets as targets_service
from app.services.collections import CollectionSummary, is_justwatch_collection


@dataclass(frozen=True)
class BindingView:
    id: uuid.UUID
    collection_id: uuid.UUID
    target_id: uuid.UUID
    collection: CollectionSummary
    target: MdblistTarget | None
    media_type: str
    mode: str
    schedule: str
    schedule_time: str | None
    schedule_cron: str
    schedule_interval_hours: int | None
    max_removal_pct: float
    max_removal_abs: int
    max_remove_count: int
    max_remove_percent: float
    thresholds: dict[str, float]
    preserve_order: bool
    reorder_enabled: bool
    schedule_policy: str
    require_review: bool
    enabled: bool
    policy_version: str | None
    policy_accepted_at: datetime | None
    created_at: datetime
    next_run_at: datetime | None
    last_run_id: uuid.UUID | None


def schedule_to_cron(schedule: str, schedule_time: str | None) -> str:
    """Translate the UI schedule into a cron expression (``""`` = manual)."""
    if schedule == "MANUAL":
        return ""
    if not schedule_time:
        raise ValidationError("schedule_time è obbligatorio per una pianificazione.")
    try:
        hour_text, minute_text = schedule_time.split(":")
        hour, minute = int(hour_text), int(minute_text)
    except (ValueError, AttributeError) as exc:
        raise ValidationError("schedule_time deve essere nel formato HH:MM.") from exc
    if schedule == "DAILY":
        return f"{minute} {hour} * * *"
    if schedule == "WEEKLY":
        return f"{minute} {hour} * * 1"
    raise ValidationError(f"Pianificazione non supportata: {schedule}.")


def cron_to_schedule(cron: str, interval_hours: int | None = None) -> tuple[str, str | None]:
    """Best-effort reverse mapping used by the API read model."""
    if interval_hours is not None:
        return "INTERVAL", None
    if not cron:
        return "MANUAL", None
    parts = cron.split()
    if len(parts) != 5:
        return "CRON", None
    minute, hour, day_of_month, month, day_of_week = parts
    if not (minute.isdigit() and hour.isdigit()):
        return "CRON", None
    schedule_time = f"{int(hour):02d}:{int(minute):02d}"
    if day_of_month == "*" and month == "*" and day_of_week == "*":
        return "DAILY", schedule_time
    if day_of_month == "*" and month == "*" and day_of_week not in ("*", "?"):
        return "WEEKLY", schedule_time
    return "CRON", None


def compute_next_run_at(
    cron: str, timezone_name: str, *, now: datetime | None = None
) -> datetime | None:
    """Next occurrence of ``cron`` in the binding timezone, stored as UTC."""
    if not cron:
        return None
    try:
        zone = ZoneInfo(timezone_name)
    except Exception:  # pragma: no cover - invalid timezone falls back to UTC
        zone = ZoneInfo("UTC")
    base = ensure_utc(now or utcnow()).astimezone(zone)
    next_local = croniter(cron, base).get_next(datetime)
    if next_local.tzinfo is None:
        next_local = next_local.replace(tzinfo=zone)
    return next_local.astimezone(UTC)


def binding_view(db: Session, binding: SyncBinding) -> BindingView:
    schedule, schedule_time = cron_to_schedule(
        binding.schedule_cron, binding.schedule_interval_hours
    )
    collection = collections_service.get_collection(db, binding.collection_id)
    target = targets_repo.get_target(db, binding.target_id)
    return BindingView(
        id=binding.id,
        collection_id=binding.collection_id,
        target_id=binding.target_id,
        collection=collection,
        target=target,
        media_type=binding.media_type,
        mode=binding.mode,
        schedule=schedule,
        schedule_time=schedule_time,
        schedule_cron=binding.schedule_cron,
        schedule_interval_hours=(
            int(binding.schedule_interval_hours)
            if binding.schedule_interval_hours is not None
            else None
        ),
        max_removal_pct=float(binding.max_removal_percent),
        max_removal_abs=int(binding.max_removal_absolute),
        max_remove_count=int(binding.max_removal_absolute),
        max_remove_percent=float(binding.max_removal_percent),
        thresholds={
            "max_removal_pct": float(binding.max_removal_percent),
            "max_removal_abs": int(binding.max_removal_absolute),
            "max_remove_count": int(binding.max_removal_absolute),
            "max_remove_percent": float(binding.max_removal_percent),
            "max_addition_pct": float(binding.max_addition_percent),
        },
        preserve_order=bool(binding.preserve_order),
        reorder_enabled=bool(binding.reorder_enabled),
        schedule_policy=binding.schedule_policy,
        require_review=bool(binding.require_manual_review),
        enabled=bool(binding.is_enabled),
        policy_version=binding.policy_version,
        policy_accepted_at=binding.policy_accepted_at,
        created_at=binding.created_at,
        next_run_at=binding.next_run_at,
        last_run_id=binding.last_run_id,
    )


def list_bindings(
    db: Session,
    *,
    collection_id: uuid.UUID | None = None,
    target_id: uuid.UUID | None = None,
    enabled: bool | None = None,
) -> list[BindingView]:
    return [
        binding_view(db, binding)
        for binding in bindings_repo.list_bindings(
            db, collection_id=collection_id, target_id=target_id, enabled=enabled
        )
    ]


def get_binding(db: Session, binding_id: uuid.UUID) -> BindingView:
    binding = bindings_repo.get_binding(db, binding_id)
    if binding is None:
        raise NotFoundError("Binding non trovato.", details={"binding_id": str(binding_id)})
    return binding_view(db, binding)


def create_binding(
    db: Session,
    settings: Settings,
    payload: BindingCreateIn,
    *,
    actor_user_id: uuid.UUID | None = None,
) -> BindingView:
    collection = collections_repo.get_collection(db, payload.collection_id)
    if collection is None:
        raise NotFoundError(
            "Collezione non trovata.",
            details={"collection_id": str(payload.collection_id)},
        )
    target = targets_repo.get_target(db, payload.target_id)
    if target is None:
        raise NotFoundError("Target non trovato.", details={"target_id": str(payload.target_id)})
    if collection.media_type != target.mediatype:
        raise ValidationError(
            "Collezione e lista MDBList hanno tipi diversi.",
            code="MEDIA_TYPE_MISMATCH",
            details={
                "collection_media_type": collection.media_type,
                "target_mediatype": target.mediatype,
            },
        )
    if (
        payload.mode is SyncMode.MIRROR
        and payload.thresholds.max_removal_pct == 0
        and payload.thresholds.max_removal_abs == 0
    ):
        raise ValidationError(
            "MIRROR richiede almeno una soglia di rimozione positiva.",
            code="THRESHOLDS_REQUIRED",
        )
    existing = bindings_repo.get_by_collection_target(
        db, collection_id=collection.id, target_id=target.id
    )
    if existing is not None:
        raise ConflictError(
            "Esiste già un binding per questa collezione e questa lista.",
            code="BINDING_EXISTS",
            details={"binding_id": str(existing.id)},
        )
    justwatch = is_justwatch_collection(db, collection)
    if justwatch and not payload.justwatch_policy_accepted:
        raise ValidationError(
            "Per le collezioni JustWatch la policy va accettata esplicitamente "
            "(justwatch_policy_accepted=true).",
            code="JUSTWATCH_POLICY_NOT_ACCEPTED",
        )
    # A JustWatch binding always starts disabled: a SUCCEEDED dry-run must exist
    # before any real run can touch the MDBList list.
    enabled = bool(payload.enabled) and not justwatch
    if enabled:
        if not payload.policy_version:
            raise ValidationError(
                "La policy deve essere accettata prima di abilitare il binding.",
                code="POLICY_NOT_ACCEPTED",
            )
        active = bindings_repo.list_bindings(db, target_id=target.id, enabled=True)
        if active:
            raise ConflictError(
                "Un altro binding attivo scrive già su questa lista.",
                code="TARGET_LOCKED",
                details={"binding_id": str(active[0].id)},
            )

    cron = schedule_to_cron(payload.schedule, payload.schedule_time)
    next_run_at = compute_next_run_at(cron, settings.app_timezone) if enabled else None
    binding = bindings_repo.create_binding(
        db,
        collection_id=collection.id,
        target_id=target.id,
        media_type=collection.media_type,
        mode=payload.mode.value,
        schedule_cron=cron,
        timezone=settings.app_timezone,
        is_enabled=enabled,
        policy_version=payload.policy_version,
        policy_accepted_at=utcnow() if enabled else None,
        policy_accepted_by=actor_user_id if enabled else None,
        max_removal_absolute=payload.thresholds.max_removal_abs,
        max_removal_percent=payload.thresholds.max_removal_pct,
        max_addition_percent=payload.thresholds.max_addition_pct,
        preserve_order=payload.preserve_order,
        reorder_enabled=payload.reorder_enabled,
        require_manual_review=payload.require_review,
        schedule_policy=payload.schedule_policy.value,
        auto_apply_max_removals=payload.auto_apply_max_removals,
        auto_apply_max_removal_ratio=payload.auto_apply_max_removal_ratio,
        max_plan_age_minutes=payload.max_plan_age_minutes,
        next_run_at=next_run_at,
    )
    audit.record(
        db,
        action="binding_created",
        entity_type="sync_binding",
        entity_id=binding.id,
        actor_user_id=actor_user_id,
        actor_type=AuditActorType.USER if actor_user_id else AuditActorType.SYSTEM,
        after={
            "collection_id": str(collection.id),
            "target_id": str(target.id),
            "mode": binding.mode,
            "enabled": binding.is_enabled,
            "justwatch_policy_accepted": bool(justwatch and payload.justwatch_policy_accepted),
        },
    )
    db.commit()
    return binding_view(db, binding)


def _validate_cron(cron: str) -> None:
    try:
        croniter(cron, utcnow())
    except Exception as exc:
        raise ValidationError(
            "Espressione cron non valida.",
            code="INVALID_CRON",
            details={"cron": cron},
        ) from exc


def update_binding(
    db: Session,
    settings: Settings,
    binding_id: uuid.UUID,
    payload: BindingUpdateIn,
    *,
    actor_user_id: uuid.UUID | None = None,
) -> BindingView:
    """Update an existing binding without recreating it or its remote list."""
    binding = bindings_repo.get_binding(db, binding_id)
    if binding is None:
        raise NotFoundError("Binding non trovato.", details={"binding_id": str(binding_id)})
    target = targets_repo.get_target(db, binding.target_id)
    before = {
        "mode": binding.mode,
        "schedule_cron": binding.schedule_cron,
        "schedule_interval_hours": binding.schedule_interval_hours,
        "max_removal_absolute": int(binding.max_removal_absolute),
        "max_removal_percent": float(binding.max_removal_percent),
        "enabled": bool(binding.is_enabled),
        "target_private": bool(target.is_private) if target is not None else None,
    }

    mode = payload.mode.value if payload.mode is not None else binding.mode
    if payload.thresholds is not None:
        max_abs = payload.thresholds.max_removal_abs
        max_pct = payload.thresholds.max_removal_pct
        max_add = payload.thresholds.max_addition_pct
    else:
        max_abs = int(binding.max_removal_absolute)
        max_pct = float(binding.max_removal_percent)
        max_add = float(binding.max_addition_percent)
    if payload.max_remove_count is not None:
        max_abs = payload.max_remove_count
    if payload.max_remove_percent is not None:
        max_pct = payload.max_remove_percent
    if mode == SyncMode.MIRROR.value and max_abs == 0 and max_pct == 0:
        raise ValidationError(
            "MIRROR richiede almeno una soglia di rimozione positiva.",
            code="THRESHOLDS_REQUIRED",
        )

    cron = binding.schedule_cron
    interval = binding.schedule_interval_hours
    if payload.schedule is not None:
        if payload.schedule == "MANUAL":
            cron, interval = "", None
        elif payload.schedule in ("DAILY", "WEEKLY"):
            cron = schedule_to_cron(payload.schedule, payload.schedule_time)
            interval = None
        elif payload.schedule == "INTERVAL":
            cron, interval = "", payload.schedule_interval_hours
        elif payload.schedule == "CRON":
            cron = (payload.schedule_cron or "").strip()
            _validate_cron(cron)
            interval = None
    elif payload.schedule_interval_hours is not None or payload.schedule_cron is not None:
        if payload.schedule_interval_hours is not None and payload.schedule_cron:
            raise ValidationError(
                "Specificare schedule_interval_hours oppure schedule_cron, non entrambi.",
                code="SCHEDULE_AMBIGUOUS",
            )
        if payload.schedule_interval_hours is not None:
            cron, interval = "", payload.schedule_interval_hours
        else:
            cron = (payload.schedule_cron or "").strip()
            _validate_cron(cron)
            interval = None

    enabled = binding.is_enabled if payload.enabled is None else payload.enabled
    policy_version = payload.policy_version or binding.policy_version
    if enabled:
        if not policy_version:
            raise ValidationError(
                "La policy deve essere accettata prima di abilitare il binding.",
                code="POLICY_NOT_ACCEPTED",
            )
        active = bindings_repo.list_bindings(db, target_id=binding.target_id, enabled=True)
        if any(other.id != binding.id for other in active):
            raise ConflictError(
                "Un altro binding attivo scrive già su questa lista.",
                code="TARGET_LOCKED",
                details={"binding_id": str(active[0].id)},
            )

    # Remote metadata is updated only after every local validation passed.
    if payload.target_private is not None:
        targets_service.update_target_visibility(
            db,
            settings,
            binding.target_id,
            private=payload.target_private,
            actor_user_id=actor_user_id,
        )

    binding.mode = mode
    binding.schedule_cron = cron
    binding.schedule_interval_hours = interval
    binding.max_removal_absolute = max_abs
    binding.max_removal_percent = max_pct
    binding.max_addition_percent = max_add
    if payload.max_plan_age_minutes is not None:
        binding.max_plan_age_minutes = payload.max_plan_age_minutes
    if payload.auto_apply_max_removals is not None:
        binding.auto_apply_max_removals = payload.auto_apply_max_removals
    if payload.auto_apply_max_removal_ratio is not None:
        binding.auto_apply_max_removal_ratio = payload.auto_apply_max_removal_ratio
    if payload.preserve_order is not None:
        binding.preserve_order = payload.preserve_order
    if payload.reorder_enabled is not None:
        binding.reorder_enabled = payload.reorder_enabled
    if payload.schedule_policy is not None:
        binding.schedule_policy = payload.schedule_policy.value
    if payload.require_review is not None:
        binding.require_manual_review = payload.require_review
    if payload.policy_version is not None:
        binding.policy_version = payload.policy_version
        if not binding.policy_accepted_at:
            binding.policy_accepted_at = utcnow()
            binding.policy_accepted_by = actor_user_id
    if payload.enabled is not None:
        binding.is_enabled = enabled
        if enabled:
            binding.policy_version = policy_version
            binding.policy_accepted_at = binding.policy_accepted_at or utcnow()
            binding.policy_accepted_by = binding.policy_accepted_by or actor_user_id
        else:
            binding.next_run_at = None

    if binding.is_enabled:
        if interval is not None:
            binding.next_run_at = utcnow() + timedelta(hours=interval)
        elif cron:
            binding.next_run_at = compute_next_run_at(cron, binding.timezone)
        else:
            binding.next_run_at = None
    else:
        binding.next_run_at = None

    db.flush()
    audit.record(
        db,
        action="binding_updated",
        entity_type="sync_binding",
        entity_id=binding.id,
        actor_user_id=actor_user_id,
        actor_type=AuditActorType.USER if actor_user_id else AuditActorType.SYSTEM,
        before=before,
        after={
            "mode": binding.mode,
            "schedule_cron": binding.schedule_cron,
            "schedule_interval_hours": binding.schedule_interval_hours,
            "max_removal_absolute": int(binding.max_removal_absolute),
            "max_removal_percent": float(binding.max_removal_percent),
            "enabled": bool(binding.is_enabled),
            "target_private": payload.target_private,
        },
    )
    db.commit()
    return binding_view(db, binding)
