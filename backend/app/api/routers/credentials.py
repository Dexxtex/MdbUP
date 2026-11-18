"""Credential endpoints: masked listing, encrypted upsert, delete, verify."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
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
from app.services import credentials as credentials_service

router = APIRouter(prefix="/credentials", tags=["credentials"])


@router.get("", response_model=schemas.CredentialListOut, summary="Credenziali mascherate")
def list_credentials(
    db: Session = Depends(get_db_dep),
    _admin: AppUser = Depends(require_admin),
) -> schemas.CredentialListOut:
    return schemas.CredentialListOut(
        items=[
            schemas.CredentialOut(
                kind=status.kind.value,
                configured=status.configured,
                masked_hint=status.masked_hint,
                key_version=status.key_version,
                status=status.status,
                updated_at=status.updated_at,
                last_verified_at=status.last_verified_at,
            )
            for status in credentials_service.list_status(db)
        ]
    )


@router.put(
    "/{kind}",
    status_code=204,
    dependencies=[Depends(require_csrf)],
    summary="Salva una credenziale cifrata",
)
def put_credential(
    kind: str,
    payload: schemas.CredentialSecretIn,
    request: Request,
    db: Session = Depends(get_db_dep),
    settings: Settings = Depends(get_settings_dep),
    admin: AppUser = Depends(require_admin),
) -> Response:
    credential_kind = credentials_service.parse_kind(kind)
    credentials_service.set_secret(
        db,
        settings,
        credential_kind,
        payload.value,
        actor_user_id=admin.id,
        ip=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_id=get_request_id(request),
    )
    return Response(status_code=204)


@router.delete(
    "/{kind}",
    status_code=204,
    dependencies=[Depends(require_csrf)],
    summary="Elimina una credenziale",
)
def delete_credential(
    kind: str,
    request: Request,
    db: Session = Depends(get_db_dep),
    admin: AppUser = Depends(require_admin),
) -> Response:
    credential_kind = credentials_service.parse_kind(kind)
    credentials_service.delete_secret(
        db,
        credential_kind,
        actor_user_id=admin.id,
        ip=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_id=get_request_id(request),
    )
    return Response(status_code=204)


@router.post(
    "/{kind}/verify",
    response_model=schemas.CredentialVerifyOut,
    dependencies=[Depends(require_csrf)],
    summary="Verifica la connessione con la credenziale salvata",
)
def verify_credential(
    kind: str,
    request: Request,
    db: Session = Depends(get_db_dep),
    settings: Settings = Depends(get_settings_dep),
    admin: AppUser = Depends(require_admin),
) -> schemas.CredentialVerifyOut:
    credential_kind = credentials_service.parse_kind(kind)
    result = credentials_service.verify(
        db,
        settings,
        credential_kind,
        actor_user_id=admin.id,
        request_id=get_request_id(request),
    )
    return schemas.CredentialVerifyOut(
        kind=result.kind.value,
        ok=result.ok,
        status_code=result.status_code,
        latency_ms=result.latency_ms,
        message=result.message,
    )
