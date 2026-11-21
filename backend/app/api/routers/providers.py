"""Provider endpoints: canonical providers with their TMDb mapping."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api import schemas_catalog
from app.api.deps import get_current_user, get_db_dep, get_settings_dep, require_admin, require_csrf
from app.core.config import Settings
from app.db.models import AppUser
from app.services import provider_catalog
from app.services import providers as providers_service

router = APIRouter(tags=["providers"])


@router.get(
    "/providers",
    response_model=schemas_catalog.ProviderListOut,
    summary="Provider canonici con mapping e numero collezioni",
)
def list_providers(
    country: str = Query("IT", min_length=2, max_length=2),
    db: Session = Depends(get_db_dep),
    _user: AppUser = Depends(get_current_user),
) -> schemas_catalog.ProviderListOut:
    items = providers_service.list_providers(db, country_code=country.upper())
    return schemas_catalog.ProviderListOut(
        items=[schemas_catalog.ProviderOut.model_validate(item) for item in items],
        total=len(items),
    )


@router.post(
    "/providers",
    status_code=201,
    response_model=schemas_catalog.ProviderOut,
    dependencies=[Depends(require_csrf)],
    summary="Crea un provider scelto dall'operatore",
)
def create_provider(
    payload: schemas_catalog.ProviderCreateIn,
    db: Session = Depends(get_db_dep),
    admin: AppUser = Depends(require_admin),
) -> schemas_catalog.ProviderOut:
    summary = providers_service.create_provider(db, payload, actor_user_id=admin.id)
    return schemas_catalog.ProviderOut.model_validate(summary)


@router.delete(
    "/providers/{provider_id}",
    status_code=204,
    dependencies=[Depends(require_csrf)],
    summary="Elimina un provider non usato da collezioni",
)
def delete_provider(
    provider_id: uuid.UUID,
    db: Session = Depends(get_db_dep),
    admin: AppUser = Depends(require_admin),
) -> None:
    providers_service.delete_provider(db, provider_id, actor_user_id=admin.id)


@router.get(
    "/providers/catalog",
    response_model=schemas_catalog.ProviderCatalogOut,
    summary="Provider disponibili da TMDb, JustWatch e TheTVDB",
)
def provider_catalog_endpoint(
    country: str = Query("IT", min_length=2, max_length=2),
    db: Session = Depends(get_db_dep),
    settings: Settings = Depends(get_settings_dep),
    _user: AppUser = Depends(get_current_user),
) -> schemas_catalog.ProviderCatalogOut:
    catalog = provider_catalog.discover_providers(db, settings, country=country.upper())
    items = [schemas_catalog.ProviderCandidateOut.model_validate(item) for item in catalog.items]
    sources = [
        schemas_catalog.ProviderCatalogSourceOut.model_validate(item.as_dict())
        for item in catalog.sources
    ]
    return schemas_catalog.ProviderCatalogOut(items=items, sources=sources, total=len(items))


@router.get(
    "/providers/{provider_id}",
    response_model=schemas_catalog.ProviderOut,
    summary="Dettaglio provider",
)
def get_provider(
    provider_id: uuid.UUID,
    country: str = Query("IT", min_length=2, max_length=2),
    db: Session = Depends(get_db_dep),
    _user: AppUser = Depends(get_current_user),
) -> schemas_catalog.ProviderOut:
    summary = providers_service.get_provider(db, provider_id, country_code=country.upper())
    return schemas_catalog.ProviderOut.model_validate(summary)
