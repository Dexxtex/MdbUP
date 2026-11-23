"""MDBList target endpoints: list local targets and create/link a remote list."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
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
from app.domain.enums import MediaType
from app.services import targets as targets_service

router = APIRouter(tags=["targets"])


@router.get(
    "/targets",
    response_model=schemas_sync.TargetListOut,
    summary="Liste MDBList collegate",
)
def list_targets(
    media_type: MediaType | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db_dep),
    _user: AppUser = Depends(get_current_user),
) -> schemas_sync.TargetListOut:
    items = targets_service.list_targets(db, media_type=media_type.value if media_type else None)
    start = (page - 1) * page_size
    page_items = items[start : start + page_size]
    return schemas_sync.TargetListOut(
        items=[schemas_sync.TargetOut.model_validate(item) for item in page_items],
        total=len(items),
        page=page,
        page_size=page_size,
        has_more=start + page_size < len(items),
    )


@router.post(
    "/targets",
    status_code=201,
    response_model=schemas_sync.TargetOut,
    dependencies=[Depends(require_csrf)],
    summary="Crea o collega una lista MDBList",
)
def create_target(
    payload: schemas_sync.TargetCreateIn,
    db: Session = Depends(get_db_dep),
    settings: Settings = Depends(get_settings_dep),
    user: AppUser = Depends(get_current_user),
) -> schemas_sync.TargetOut:
    view = targets_service.create_target(db, settings, payload, actor_user_id=user.id)
    return schemas_sync.TargetOut.model_validate(view)
