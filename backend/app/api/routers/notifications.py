"""Notification channel management and test delivery."""

from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api import schemas_notifications
from app.api.deps import get_db_dep, require_admin, require_csrf
from app.db.models import AppUser, NotificationChannel
from app.services import notifications as notifications_service

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _out(channel: NotificationChannel) -> schemas_notifications.NotificationChannelOut:
    return schemas_notifications.NotificationChannelOut(
        id=channel.id,
        name=channel.name,
        kind=channel.kind,  # type: ignore[arg-type]
        enabled=channel.is_enabled,
        events=list(channel.events or []),
        config=dict(channel.config or {}),
        secret_configured=channel.secret_ciphertext is not None,
        masked_hint=channel.secret_masked_hint,
        last_sent_at=channel.last_sent_at,
        last_status=channel.last_status,
        last_error=channel.last_error,
        retry_count=channel.retry_count or 0,
        next_retry_at=channel.next_retry_at,
        created_at=channel.created_at,
        updated_at=channel.updated_at,
    )


@router.get(
    "/channels",
    response_model=schemas_notifications.NotificationChannelListOut,
    summary="Canali di notifica configurati",
)
def list_channels(
    db: Session = Depends(get_db_dep),
    _admin: AppUser = Depends(require_admin),
) -> schemas_notifications.NotificationChannelListOut:
    return schemas_notifications.NotificationChannelListOut(
        items=[_out(channel) for channel in notifications_service.list_channels(db)]
    )


@router.post(
    "/channels",
    status_code=201,
    response_model=schemas_notifications.NotificationChannelOut,
    dependencies=[Depends(require_csrf)],
    summary="Crea un canale di notifica",
)
def create_channel(
    payload: schemas_notifications.NotificationChannelCreateIn,
    db: Session = Depends(get_db_dep),
    admin: AppUser = Depends(require_admin),
) -> schemas_notifications.NotificationChannelOut:
    channel = notifications_service.create_channel(
        db,
        _settings(db),
        name=payload.name,
        kind=payload.kind,
        secret=payload.secret,
        events=payload.events,
        config=payload.config,
        is_enabled=payload.enabled,
        actor_user_id=admin.id,
    )
    return _out(channel)


@router.patch(
    "/channels/{channel_id}",
    response_model=schemas_notifications.NotificationChannelOut,
    dependencies=[Depends(require_csrf)],
    summary="Modifica un canale di notifica",
)
def update_channel(
    channel_id: uuid.UUID,
    payload: schemas_notifications.NotificationChannelUpdateIn,
    db: Session = Depends(get_db_dep),
    admin: AppUser = Depends(require_admin),
) -> schemas_notifications.NotificationChannelOut:
    channel = notifications_service.update_channel(
        db,
        _settings(db),
        channel_id,
        name=payload.name,
        secret=payload.secret,
        events=payload.events,
        config=payload.config,
        is_enabled=payload.enabled,
        actor_user_id=admin.id,
    )
    return _out(channel)


@router.delete(
    "/channels/{channel_id}",
    status_code=204,
    dependencies=[Depends(require_csrf)],
    summary="Elimina un canale di notifica",
)
def delete_channel(
    channel_id: uuid.UUID,
    db: Session = Depends(get_db_dep),
    admin: AppUser = Depends(require_admin),
) -> Response:
    notifications_service.delete_channel(db, channel_id, actor_user_id=admin.id)
    return Response(status_code=204)


@router.post(
    "/channels/{channel_id}/test",
    response_model=schemas_notifications.NotificationTestOut,
    dependencies=[Depends(require_csrf)],
    summary="Invia un messaggio di prova",
)
def test_channel(
    channel_id: uuid.UUID,
    db: Session = Depends(get_db_dep),
    _admin: AppUser = Depends(require_admin),
) -> schemas_notifications.NotificationTestOut:
    started = time.monotonic()
    result = notifications_service.send_test(db, _settings(db), channel_id)
    return schemas_notifications.NotificationTestOut(
        ok=result.ok,
        status_code=result.status_code,
        message=(
            "Messaggio di prova inviato."
            if result.ok
            else f"Invio non riuscito: {result.error or 'errore sconosciuto'}"
        ),
        latency_ms=int((time.monotonic() - started) * 1000),
    )


def _settings(db: Session):  # noqa: ANN001 - local helper keeps imports small
    from app.core.config import get_settings

    return get_settings()
