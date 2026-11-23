"""Binding endpoints: list, detail, create and start a run."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import (
    get_current_user,
    get_db_dep,
    get_settings_dep,
    require_csrf,
)
from app.api.schemas import catalog as schemas_catalog
from app.api.schemas import sync as schemas_sync
from app.core.config import Settings
from app.db.models import AppUser
from app.services import bindings as bindings_service
from app.services import runs as runs_service
from app.services.bindings import BindingView
from app.services.targets import target_view

router = APIRouter(tags=["bindings"])


def _binding_out(view: BindingView) -> schemas_sync.BindingOut:
    return schemas_sync.BindingOut(
        id=view.id,
        collection_id=view.collection_id,
        target_id=view.target_id,
        collection=schemas_catalog.CollectionOut.model_validate(view.collection),
        target=(
            schemas_sync.TargetOut.model_validate(target_view(view.target))
            if view.target is not None
            else None
        ),
        media_type=view.media_type,
        mode=view.mode,
        schedule=view.schedule,
        schedule_time=view.schedule_time,
        schedule_cron=view.schedule_cron,
        schedule_interval_hours=view.schedule_interval_hours,
        max_removal_pct=view.max_removal_pct,
        max_removal_abs=view.max_removal_abs,
        max_remove_count=view.max_remove_count,
        max_remove_percent=view.max_remove_percent,
        thresholds=view.thresholds,
        preserve_order=view.preserve_order,
        reorder_enabled=view.reorder_enabled,
        schedule_policy=view.schedule_policy,
        require_review=view.require_review,
        enabled=view.enabled,
        policy_version=view.policy_version,
        policy_accepted_at=view.policy_accepted_at,
        created_at=view.created_at,
        next_run_at=view.next_run_at,
        last_run_id=view.last_run_id,
    )


@router.get(
    "/bindings",
    response_model=schemas_sync.BindingListOut,
    summary="Binding con collezione e target",
)
def list_bindings(
    collection_id: uuid.UUID | None = None,
    target_id: uuid.UUID | None = None,
    enabled: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db_dep),
    _user: AppUser = Depends(get_current_user),
) -> schemas_sync.BindingListOut:
    items = bindings_service.list_bindings(
        db, collection_id=collection_id, target_id=target_id, enabled=enabled
    )
    start = (page - 1) * page_size
    page_items = items[start : start + page_size]
    return schemas_sync.BindingListOut(
        items=[_binding_out(item) for item in page_items],
        total=len(items),
        page=page,
        page_size=page_size,
        has_more=start + page_size < len(items),
    )


@router.post(
    "/bindings",
    status_code=201,
    response_model=schemas_sync.BindingOut,
    dependencies=[Depends(require_csrf)],
    summary="Crea un binding",
)
def create_binding(
    payload: schemas_sync.BindingCreateIn,
    db: Session = Depends(get_db_dep),
    settings: Settings = Depends(get_settings_dep),
    user: AppUser = Depends(get_current_user),
) -> schemas_sync.BindingOut:
    view = bindings_service.create_binding(db, settings, payload, actor_user_id=user.id)
    return _binding_out(view)


@router.get(
    "/bindings/{binding_id}",
    response_model=schemas_sync.BindingOut,
    summary="Dettaglio binding",
)
def get_binding(
    binding_id: uuid.UUID,
    db: Session = Depends(get_db_dep),
    _user: AppUser = Depends(get_current_user),
) -> schemas_sync.BindingOut:
    return _binding_out(bindings_service.get_binding(db, binding_id))


@router.patch(
    "/bindings/{binding_id}",
    response_model=schemas_sync.BindingOut,
    dependencies=[Depends(require_csrf)],
    summary="Modifica un binding esistente",
)
def update_binding(
    binding_id: uuid.UUID,
    payload: schemas_sync.BindingUpdateIn,
    db: Session = Depends(get_db_dep),
    settings: Settings = Depends(get_settings_dep),
    user: AppUser = Depends(get_current_user),
) -> schemas_sync.BindingOut:
    view = bindings_service.update_binding(db, settings, binding_id, payload, actor_user_id=user.id)
    return _binding_out(view)


@router.post(
    "/bindings/{binding_id}/runs",
    status_code=202,
    response_model=schemas_sync.RunAcceptedOut,
    dependencies=[Depends(require_csrf)],
    summary="Avvia un run (dry-run o reale)",
)
def start_binding_run(
    binding_id: uuid.UUID,
    payload: schemas_sync.StartRunIn,
    db: Session = Depends(get_db_dep),
    settings: Settings = Depends(get_settings_dep),
    user: AppUser = Depends(get_current_user),
) -> schemas_sync.RunAcceptedOut:
    run, job = runs_service.start_run(db, settings, binding_id, payload, actor_user_id=user.id)
    return schemas_sync.RunAcceptedOut(run_id=run.id, job_id=job.id, status=run.status)
