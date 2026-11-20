"""Source endpoints: capabilities, status and a real healthcheck."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request
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
from app.services import tvdb as tvdb_service

router = APIRouter(tags=["sources"])


@router.get(
    "/sources",
    response_model=schemas_catalog.SourceListOut,
    summary="Fonti con capability e stato",
)
def list_sources(
    db: Session = Depends(get_db_dep),
    settings: Settings = Depends(get_settings_dep),
    _user: AppUser = Depends(get_current_user),
) -> schemas_catalog.SourceListOut:
    items = sources_service.list_sources(db, settings)
    return schemas_catalog.SourceListOut(
        items=[schemas_catalog.SourceOut.model_validate(item) for item in items]
    )


@router.get(
    "/sources/tvdb/companies",
    response_model=schemas_catalog.TVDbCompanyListOut,
    summary="Company TVDB (metadati, nessuna disponibilità per paese)",
)
def list_tvdb_companies(
    db: Session = Depends(get_db_dep),
    settings: Settings = Depends(get_settings_dep),
    _user: AppUser = Depends(get_current_user),
) -> schemas_catalog.TVDbCompanyListOut:
    items = tvdb_service.list_streaming_companies(db, settings)
    return schemas_catalog.TVDbCompanyListOut(
        items=[schemas_catalog.TVDbCompanyOut.model_validate(item) for item in items],
        total=len(items),
    )


@router.get(
    "/sources/tvdb/lists",
    response_model=schemas_catalog.TVDbListListOut,
    summary="Liste TVDB (ufficiali o utente; metadati)",
)
def list_tvdb_lists(
    page: int = 0,
    db: Session = Depends(get_db_dep),
    settings: Settings = Depends(get_settings_dep),
    _user: AppUser = Depends(get_current_user),
) -> schemas_catalog.TVDbListListOut:
    items = tvdb_service.list_lists(db, settings, page=max(0, page))
    return schemas_catalog.TVDbListListOut(
        items=[schemas_catalog.TVDbListOut.model_validate(item) for item in items],
        total=len(items),
        page=page,
    )


@router.get(
    "/sources/tvdb/genres",
    response_model=schemas_catalog.TVDbGenreListOut,
    summary="Generi TVDB (metadati)",
)
def list_tvdb_genres(
    db: Session = Depends(get_db_dep),
    settings: Settings = Depends(get_settings_dep),
    _user: AppUser = Depends(get_current_user),
) -> schemas_catalog.TVDbGenreListOut:
    items = tvdb_service.list_genres(db, settings)
    return schemas_catalog.TVDbGenreListOut(
        items=[schemas_catalog.TVDbGenreOut.model_validate(item) for item in items],
        total=len(items),
    )


@router.get(
    "/sources/tvdb/catalog",
    response_model=schemas_catalog.TVDbCatalogOut,
    summary="Film o serie TVDB filtrati per genere, anno e paese di origine",
)
def filter_tvdb_catalog(
    media_type: str = Query("MOVIE", pattern="^(MOVIE|SHOW)$"),
    country: str = Query("ita", min_length=3, max_length=3),
    language: str = Query("ita", min_length=3, max_length=3),
    genre_id: str | None = Query(None, max_length=32),
    year: int | None = Query(None, ge=1900, le=2100),
    sort: str = Query("score", pattern="^(score|firstAired|lastAired|name)$"),
    sort_type: str = Query("desc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db_dep),
    settings: Settings = Depends(get_settings_dep),
    _user: AppUser = Depends(get_current_user),
) -> schemas_catalog.TVDbCatalogOut:
    items = tvdb_service.filter_titles(
        db,
        settings,
        media_type,
        country=country.lower(),
        language=language.lower(),
        genre_id=genre_id,
        year=year,
        sort=sort,
        sort_type=sort_type,
    )
    return schemas_catalog.TVDbCatalogOut(
        items=[schemas_catalog.TVDbCatalogItemOut.model_validate(item) for item in items],
        total=len(items),
        media_type=media_type,
        country=country.lower(),
        language=language.lower(),
        genre_id=genre_id,
        year=year,
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
