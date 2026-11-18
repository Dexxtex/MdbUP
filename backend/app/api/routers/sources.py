"""Source endpoints: capabilities, status and a real healthcheck."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api import schemas_catalog
from app.api.deps import (
    get_current_user,
    get_db_dep,
    get_request_id,
    get_settings_dep,
    require_csrf,
)
from app.core.config import Settings
from app.db.models import AppUser
from app.services import sources as sources_service

router = APIRouter(tags=["sources"])


@router.get(
    "/sources",
    response_model=schemas_catalog.SourceListOut,
    summary="Fonti con capability e stato",
)
def list_sources(
    db: Session = Depends(get_db_dep),
    _user: AppUser = Depends(get_current_user),
) -> schemas_catalog.SourceListOut:
    items = sources_service.list_sources(db)
    return schemas_catalog.SourceListOut(
        items=[schemas_catalog.SourceOut.model_validate(item) for item in items]
    )


@router.post(
    "/sources/{source_id}/healthcheck",
    response_model=schemas_catalog.SourceHealthcheckOut,
    dependencies=[Depends(require_csrf)],
    summary="Healthcheck di una fonte configurata",
)
def healthcheck_source(
    source_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db_dep),
    settings: Settings = Depends(get_settings_dep),
    user: AppUser = Depends(get_current_user),
) -> schemas_catalog.SourceHealthcheckOut:
    result = sources_service.healthcheck_source(
        db,
        settings,
        source_id,
        actor_user_id=user.id,
        request_id=get_request_id(request),
    )
    return schemas_catalog.SourceHealthcheckOut.model_validate(result)
