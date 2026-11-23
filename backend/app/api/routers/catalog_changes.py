"""Catalog change feed endpoint (Phase 9)."""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db_dep
from app.api.schemas import catalog_changes as schemas_catalog_changes
from app.db.models import AppUser
from app.services import catalog_changes as catalog_changes_service

router = APIRouter(tags=["catalog-changes"])


@router.get(
    "/catalog-changes",
    response_model=schemas_catalog_changes.CatalogChangesOut,
    summary="Cambi catalogo (aggiunti/rimossi) tra snapshot validi consecutivi",
)
def list_catalog_changes(
    window: Literal["24h", "7d", "14d", "30d"] = Query("24h"),
    provider_id: uuid.UUID | None = None,
    media_type: Literal["MOVIE", "SHOW"] | None = None,
    source_key: Literal["justwatch", "tmdb"] | None = None,
    direction: Literal["ADDED", "REMOVED"] | None = None,
    search: str | None = Query(None, max_length=200),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db_dep),
    _user: AppUser = Depends(get_current_user),
) -> schemas_catalog_changes.CatalogChangesOut:
    page_result = catalog_changes_service.list_catalog_changes(
        db,
        window=window,
        provider_id=provider_id,
        media_type=media_type,
        source_key=source_key,
        direction=direction,
        search=search,
        page=page,
        page_size=page_size,
    )
    return schemas_catalog_changes.CatalogChangesOut.model_validate(page_result)
