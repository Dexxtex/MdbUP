"""Snapshot endpoints: paginated items of one snapshot."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api import schemas_catalog
from app.api.deps import get_current_user, get_db_dep
from app.db.models import AppUser
from app.services import snapshots as snapshots_service

router = APIRouter(tags=["snapshots"])


@router.get(
    "/snapshots/{snapshot_id}/items",
    response_model=schemas_catalog.SnapshotItemListOut,
    summary="Item dello snapshot con paginazione",
)
def list_snapshot_items(
    snapshot_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db_dep),
    _user: AppUser = Depends(get_current_user),
) -> schemas_catalog.SnapshotItemListOut:
    items, total = snapshots_service.list_snapshot_items(
        db, snapshot_id, page=page, page_size=page_size
    )
    return schemas_catalog.SnapshotItemListOut(
        items=[schemas_catalog.SnapshotItemOut.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )
