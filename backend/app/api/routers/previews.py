"""Preview endpoints: compute a plan without writing and read it back."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import (
    get_current_user,
    get_db_dep,
    get_settings_dep,
    require_csrf,
)
from app.api.schemas import sync as schemas_sync
from app.core.config import Settings
from app.db.models import AppUser
from app.services import previews as previews_service

router = APIRouter(tags=["previews"])


@router.post(
    "/previews",
    status_code=202,
    response_model=schemas_sync.PreviewAcceptedOut,
    dependencies=[Depends(require_csrf)],
    summary="Calcola una preview del piano (nessuna scrittura)",
)
def create_preview(
    payload: schemas_sync.PreviewRequest,
    db: Session = Depends(get_db_dep),
    settings: Settings = Depends(get_settings_dep),
    _user: AppUser = Depends(get_current_user),
) -> schemas_sync.PreviewAcceptedOut:
    preview_id = previews_service.create_preview(db, settings, payload)
    return schemas_sync.PreviewAcceptedOut(preview_id=preview_id)


@router.get(
    "/previews/{preview_id}",
    response_model=schemas_sync.PreviewOut,
    summary="Preview calcolata",
)
def get_preview(
    preview_id: uuid.UUID,
    db: Session = Depends(get_db_dep),
    _user: AppUser = Depends(get_current_user),
) -> schemas_sync.PreviewOut:
    return schemas_sync.PreviewOut.model_validate(previews_service.get_preview(db, preview_id))
