"""MDBList target use cases: list local targets and create/link remote lists."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import MdblistTarget
from app.domain.commands import TargetCreateIn
from app.domain.enums import AuditActorType, MediaType
from app.domain.errors import ConflictError, NotFoundError, ValidationError
from app.integrations.mdblist.client import MdbListError
from app.integrations.mdblist.models import MdbListList
from app.repositories import audit
from app.repositories import targets as targets_repo
from app.services import sync as sync_service

MDBLIST_WEB_BASE = "https://mdblist.com/lists"


@dataclass(frozen=True)
class TargetView:
    id: uuid.UUID
    remote_list_id: str
    remote_slug: str | None
    remote_url: str | None
    name: str
    mediatype: str
    private: bool
    item_count: int | None
    last_verified_at: datetime | None
    last_remote_read_at: datetime | None
    capabilities: dict[str, Any]


def target_view(target: MdblistTarget) -> TargetView:
    return TargetView(
        id=target.id,
        remote_list_id=str(target.remote_list_id),
        remote_slug=target.remote_slug,
        remote_url=target.remote_url,
        name=target.name,
        mediatype=target.mediatype,
        private=bool(target.is_private),
        item_count=target.item_count,
        last_verified_at=target.last_verified_at,
        last_remote_read_at=target.last_remote_read_at,
        capabilities=target.capabilities or {},
    )


def list_targets(db: Session, *, media_type: str | None = None) -> list[TargetView]:
    return [target_view(target) for target in targets_repo.list_targets(db, mediatype=media_type)]


def get_target(db: Session, target_id: uuid.UUID) -> TargetView:
    target = targets_repo.get_target(db, target_id)
    if target is None:
        raise NotFoundError("Target non trovato.", details={"target_id": str(target_id)})
    return target_view(target)


def create_target(
    db: Session,
    settings: Settings,
    payload: TargetCreateIn,
    *,
    actor_user_id: uuid.UUID | None = None,
) -> TargetView:
    """Create a new MDBList list or link an existing one.

    The remote list is never deleted or recreated: ``remote_list_id`` is the
    stable key and the slug/URL are display metadata only.
    """
    client = sync_service.build_client(db, settings)
    try:
        if payload.mode == "new":
            remote = client.create_list(payload.name or "", private=payload.private)
        else:
            if payload.remote_list_id is None:  # pragma: no cover - schema validator
                raise ValidationError("remote_list_id è obbligatorio per mode=existing.")
            remote = client.get_list(payload.remote_list_id)
    except MdbListError as exc:
        raise ConflictError(
            f"MDBList non ha accettato la richiesta: {exc}",
            code="MDBLIST_REQUEST_FAILED",
        ) from exc
    finally:
        client.close()

    existing = targets_repo.get_by_remote_list_id(db, remote.id)
    if existing is not None:
        raise ConflictError(
            "Questa lista MDBList è già collegata a un target.",
            code="TARGET_ALREADY_LINKED",
            details={"target_id": str(existing.id), "remote_list_id": remote.id},
        )

    mediatype = _resolve_mediatype(remote, payload.media_type)
    name = payload.name or remote.name
    target = targets_repo.create_target(
        db,
        remote_list_id=remote.id,
        name=name,
        mediatype=mediatype,
        remote_slug=remote.slug,
        remote_url=_remote_url(remote),
        is_private=remote.private if payload.mode == "existing" else payload.private,
        item_count=remote.item_count,
        capabilities={
            "supports_reorder": True,
            "max_reorder_batch": 1000,
            "mediatype": mediatype,
        },
    )
    targets_repo.set_verified_at(db, target)
    audit.record(
        db,
        action="target_created",
        entity_type="mdblist_target",
        entity_id=target.id,
        actor_user_id=actor_user_id,
        actor_type=AuditActorType.USER if actor_user_id else AuditActorType.SYSTEM,
        after={
            "remote_list_id": remote.id,
            "mediatype": mediatype,
            "mode": payload.mode,
        },
    )
    db.commit()
    return target_view(target)


def update_target_visibility(
    db: Session,
    settings: Settings,
    target_id: uuid.UUID,
    *,
    private: bool,
    actor_user_id: uuid.UUID | None = None,
) -> TargetView:
    """Update only the remote list visibility (``PUT /lists/{id}``)."""
    target = targets_repo.get_target(db, target_id)
    if target is None:
        raise NotFoundError("Target non trovato.", details={"target_id": str(target_id)})
    client = sync_service.build_client(db, settings)
    try:
        remote = client.update_list(target.remote_list_id, private=private)
    except MdbListError as exc:
        raise ConflictError(
            f"MDBList non ha accettato l'aggiornamento della lista: {exc}",
            code="MDBLIST_REQUEST_FAILED",
        ) from exc
    finally:
        client.close()
    targets_repo.update_remote_metadata(db, target, is_private=remote.private, verified=True)
    audit.record(
        db,
        action="target_visibility_updated",
        entity_type="mdblist_target",
        entity_id=target.id,
        actor_user_id=actor_user_id,
        actor_type=AuditActorType.USER if actor_user_id else AuditActorType.SYSTEM,
        after={"remote_list_id": target.remote_list_id, "private": remote.private},
    )
    db.commit()
    return target_view(target)


def _resolve_mediatype(remote: MdbListList, requested: MediaType) -> str:
    if remote.mediatype and remote.mediatype != requested.value:
        raise ValidationError(
            "La lista MDBList non è dello stesso tipo della collezione.",
            code="MEDIA_TYPE_MISMATCH",
            details={"remote_mediatype": remote.mediatype, "requested": requested.value},
        )
    return requested.value


def _remote_url(remote: MdbListList) -> str | None:
    if not remote.slug:
        return None
    return f"{MDBLIST_WEB_BASE}/{remote.slug}"
