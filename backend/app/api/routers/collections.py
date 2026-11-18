"""Collection endpoints: list, detail, snapshot history and acquisition."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api import schemas_catalog
from app.api.deps import (
    get_client_ip,
    get_current_user,
    get_db_dep,
    get_request_id,
    get_settings_dep,
    require_csrf,
)
from app.api.errors import NotFoundError, SourceUnavailableError
from app.connectors import registry
from app.core.config import Settings
from app.db.models import AppUser
from app.domain.enums import AuditActorType, CollectionKind, CollectionOrigin, MediaType
from app.jobs import tasks
from app.repositories import audit
from app.repositories import collections as collections_repo
from app.repositories import sources as sources_repo
from app.services import collection_admin
from app.services import collections as collections_service
from app.services import tv_events as tv_events_service

router = APIRouter(tags=["collections"])


@router.get(
    "/genres",
    response_model=schemas_catalog.GenreListOut,
    summary="Generi TMDb ufficiali per tipo media",
)
def list_genres(
    media_type: MediaType = Query(MediaType.MOVIE),
    _user: AppUser = Depends(get_current_user),
) -> schemas_catalog.GenreListOut:
    return schemas_catalog.GenreListOut(
        media_type=media_type.value,
        items=[
            schemas_catalog.GenreOut(id=item["id"], name=str(item["name"]))
            for item in collection_admin.list_genres(media_type.value)
        ],
    )


@router.get(
    "/collections",
    response_model=schemas_catalog.CollectionListOut,
    summary="Collezioni con filtri",
)
def list_collections(
    provider_id: uuid.UUID | None = None,
    media_type: MediaType | None = None,
    origin: CollectionOrigin | None = None,
    kind: CollectionKind | None = None,
    country: str | None = Query(None, min_length=2, max_length=2),
    is_active: bool | None = None,
    db: Session = Depends(get_db_dep),
    _user: AppUser = Depends(get_current_user),
) -> schemas_catalog.CollectionListOut:
    items = collections_service.list_collections(
        db,
        provider_id=provider_id,
        media_type=media_type.value if media_type else None,
        origin=origin.value if origin else None,
        kind=kind.value if kind else None,
        country_code=country.upper() if country else None,
        is_active=is_active,
    )
    return schemas_catalog.CollectionListOut(
        items=[schemas_catalog.CollectionOut.model_validate(item) for item in items],
        total=len(items),
    )


@router.get(
    "/collections/{collection_id}",
    response_model=schemas_catalog.CollectionOut,
    summary="Dettaglio collezione con ultimo snapshot valido",
)
def get_collection(
    collection_id: uuid.UUID,
    db: Session = Depends(get_db_dep),
    _user: AppUser = Depends(get_current_user),
) -> schemas_catalog.CollectionOut:
    summary = collections_service.get_collection(db, collection_id)
    return schemas_catalog.CollectionOut.model_validate(summary)


@router.get(
    "/collections/{collection_id}/snapshots",
    response_model=schemas_catalog.SnapshotListOut,
    summary="Storico snapshot della collezione",
)
def list_collection_snapshots(
    collection_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db_dep),
    _user: AppUser = Depends(get_current_user),
) -> schemas_catalog.SnapshotListOut:
    items, total = collections_service.list_collection_snapshots(
        db, collection_id, page=page, page_size=page_size
    )
    return schemas_catalog.SnapshotListOut(
        items=[schemas_catalog.SnapshotOut.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/collections/{collection_id}/episode-events",
    response_model=schemas_catalog.EpisodeEventListOut,
    summary="Eventi stagione/episodio delle serie madri nella collezione",
)
def list_collection_episode_events(
    collection_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db_dep),
    _user: AppUser = Depends(get_current_user),
) -> schemas_catalog.EpisodeEventListOut:
    items, total = tv_events_service.list_collection_episode_events(db, collection_id, limit=limit)
    return schemas_catalog.EpisodeEventListOut(
        items=[schemas_catalog.EpisodeEventOut.model_validate(item) for item in items],
        total=total,
    )


@router.post(
    "/collections",
    status_code=201,
    response_model=schemas_catalog.CollectionOut,
    dependencies=[Depends(require_csrf)],
    summary="Crea una collezione TMDb",
)
def create_collection(
    payload: schemas_catalog.CollectionCreateIn,
    db: Session = Depends(get_db_dep),
    settings: Settings = Depends(get_settings_dep),
    user: AppUser = Depends(get_current_user),
) -> schemas_catalog.CollectionOut:
    summary = collection_admin.create_collection(db, settings, payload, actor_user_id=user.id)
    return schemas_catalog.CollectionOut.model_validate(summary)


@router.patch(
    "/collections/{collection_id}",
    response_model=schemas_catalog.CollectionOut,
    dependencies=[Depends(require_csrf)],
    summary="Modifica una collezione esistente",
)
def update_collection(
    collection_id: uuid.UUID,
    payload: schemas_catalog.CollectionUpdateIn,
    db: Session = Depends(get_db_dep),
    settings: Settings = Depends(get_settings_dep),
    user: AppUser = Depends(get_current_user),
) -> schemas_catalog.CollectionOut:
    summary = collection_admin.update_collection(
        db, settings, collection_id, payload, actor_user_id=user.id
    )
    return schemas_catalog.CollectionOut.model_validate(summary)


@router.post(
    "/collections/{collection_id}/acquire",
    status_code=202,
    response_model=schemas_catalog.AcquireOut,
    dependencies=[Depends(require_csrf)],
    summary="Avvia l'acquisizione della collezione",
)
def acquire_collection(
    collection_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db_dep),
    settings: Settings = Depends(get_settings_dep),
    user: AppUser = Depends(get_current_user),
) -> schemas_catalog.AcquireOut:
    collection = collections_repo.get_collection(db, collection_id)
    if collection is None:
        raise NotFoundError(
            "Collezione non trovata.", details={"collection_id": str(collection_id)}
        )
    source = sources_repo.get_source(db, collection.source_id)
    if source is None:
        raise SourceUnavailableError(
            "Fonte della collezione non trovata.",
            details={"collection_id": str(collection_id)},
        )
    if not registry.is_registered(source.key):
        raise SourceUnavailableError(
            f"Connettore non disponibile per la fonte '{source.key}'.",
            details={"source_key": source.key},
        )
    registry.ensure_source_credentials(db, settings, source.key)
    job = tasks.enqueue_acquire_collection(db, settings, collection.id, actor_user_id=user.id)
    audit.record(
        db,
        action="collection_acquisition_enqueued",
        entity_type="collection",
        entity_id=collection.id,
        actor_user_id=user.id,
        actor_type=AuditActorType.USER,
        after={"job_id": str(job.id), "source_key": source.key},
        ip=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_id=get_request_id(request),
    )
    db.commit()
    snapshot_id = job.result.get("snapshot_id") if job.result else None
    return schemas_catalog.AcquireOut(
        job_id=job.id,
        collection_id=collection.id,
        status=job.status,
        snapshot_id=snapshot_id,
    )
