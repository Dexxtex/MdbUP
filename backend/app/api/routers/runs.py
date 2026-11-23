"""Sync run endpoints: list, detail, operations and control actions."""

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
from app.api.schemas import sync as schemas_sync
from app.core.config import Settings
from app.db.models import AppUser
from app.domain.enums import (
    MediaType,
    SyncOperationAction,
    SyncOperationStatus,
    SyncRunStatus,
)
from app.services import runs as runs_service

router = APIRouter(tags=["runs"])


@router.get("/runs", response_model=schemas_sync.RunListOut, summary="Run di sync")
def list_runs(
    binding_id: uuid.UUID | None = None,
    target_id: uuid.UUID | None = None,
    status: SyncRunStatus | None = None,
    provider_id: uuid.UUID | None = None,
    media_type: MediaType | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db_dep),
    _user: AppUser = Depends(get_current_user),
) -> schemas_sync.RunListOut:
    items, total = runs_service.list_runs(
        db,
        binding_id=binding_id,
        target_id=target_id,
        status=status.value if status else None,
        provider_id=provider_id,
        media_type=media_type.value if media_type else None,
        page=page,
        page_size=page_size,
    )
    return schemas_sync.RunListOut(
        items=[schemas_sync.RunOut.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        has_more=page * page_size < total,
    )


@router.get("/runs/{run_id}", response_model=schemas_sync.RunOut, summary="Dettaglio run")
def get_run(
    run_id: uuid.UUID,
    db: Session = Depends(get_db_dep),
    _user: AppUser = Depends(get_current_user),
) -> schemas_sync.RunOut:
    return schemas_sync.RunOut.model_validate(runs_service.get_run(db, run_id))


@router.get(
    "/runs/{run_id}/operations",
    response_model=schemas_sync.OperationListOut,
    summary="Operation ledger del run",
)
def list_run_operations(
    run_id: uuid.UUID,
    status: SyncOperationStatus | None = None,
    action: SyncOperationAction | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db_dep),
    _user: AppUser = Depends(get_current_user),
) -> schemas_sync.OperationListOut:
    items, total = runs_service.list_operations(
        db,
        run_id,
        status=status.value if status else None,
        action=action.value if action else None,
        page=page,
        page_size=page_size,
    )
    return schemas_sync.OperationListOut(
        items=[schemas_sync.OperationOut.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        has_more=page * page_size < total,
    )


@router.post(
    "/runs/{run_id}/approve",
    status_code=202,
    response_model=schemas_sync.JobAcceptedOut,
    dependencies=[Depends(require_csrf)],
    summary="Approva un piano in attesa",
)
def approve_run(
    run_id: uuid.UUID,
    payload: schemas_sync.ApproveRunIn,
    db: Session = Depends(get_db_dep),
    settings: Settings = Depends(get_settings_dep),
    user: AppUser = Depends(get_current_user),
) -> schemas_sync.JobAcceptedOut:
    job = runs_service.approve_run(db, settings, run_id, payload, actor_user_id=user.id)
    return schemas_sync.JobAcceptedOut(job_id=job.id)


@router.post(
    "/runs/{run_id}/cancel",
    status_code=202,
    response_model=schemas_sync.JobAcceptedOut,
    dependencies=[Depends(require_csrf)],
    summary="Annulla un run non terminale",
)
def cancel_run(
    run_id: uuid.UUID,
    db: Session = Depends(get_db_dep),
    settings: Settings = Depends(get_settings_dep),
    _user: AppUser = Depends(get_current_user),
) -> schemas_sync.JobAcceptedOut:
    job = runs_service.cancel_run(db, settings, run_id)
    return schemas_sync.JobAcceptedOut(job_id=job.id)


@router.post(
    "/runs/{run_id}/reconcile",
    status_code=202,
    response_model=schemas_sync.JobAcceptedOut,
    dependencies=[Depends(require_csrf)],
    summary="Riconcilia un run PARTIAL/FAILED con il remoto",
)
def reconcile_run(
    run_id: uuid.UUID,
    db: Session = Depends(get_db_dep),
    settings: Settings = Depends(get_settings_dep),
    _user: AppUser = Depends(get_current_user),
) -> schemas_sync.JobAcceptedOut:
    job = runs_service.reconcile_run(db, settings, run_id)
    return schemas_sync.JobAcceptedOut(job_id=job.id)


@router.post(
    "/runs/{run_id}/resume",
    status_code=202,
    response_model=schemas_sync.RunAcceptedOut,
    dependencies=[Depends(require_csrf)],
    summary="Riprende un run PARTIAL/FAILED con un nuovo piano",
)
def resume_run(
    run_id: uuid.UUID,
    db: Session = Depends(get_db_dep),
    settings: Settings = Depends(get_settings_dep),
    _user: AppUser = Depends(get_current_user),
) -> schemas_sync.RunAcceptedOut:
    run, job = runs_service.resume_run(db, settings, run_id)
    return schemas_sync.RunAcceptedOut(run_id=run.id, job_id=job.id, status=run.status)
