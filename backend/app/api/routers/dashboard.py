"""Dashboard endpoint: counters, alerts and recent activity."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api import schemas_catalog
from app.api.deps import get_current_user, get_db_dep, get_settings_dep
from app.core.config import Settings
from app.db.models import AppUser
from app.services import dashboard as dashboard_service

router = APIRouter(tags=["dashboard"])


@router.get(
    "/dashboard",
    response_model=schemas_catalog.DashboardOut,
    summary="Contatori, ultimi run, alert",
)
def get_dashboard(
    db: Session = Depends(get_db_dep),
    settings: Settings = Depends(get_settings_dep),
    _user: AppUser = Depends(get_current_user),
) -> schemas_catalog.DashboardOut:
    summary = dashboard_service.get_dashboard(db, settings)
    return schemas_catalog.DashboardOut.model_validate(summary)
