"""Aggregate router mounted by ``app.main`` under ``/api``.

Foundation routers (auth, health, settings, credentials) come from lane A, the
catalog/dashboard routers from lane B and the sync routers from lane C. Every
router stays mounted so the OpenAPI schema is complete while lanes land.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routers import (
    auth,
    bindings,
    catalog_changes,
    collections,
    config,
    credentials,
    dashboard,
    health,
    notifications,
    previews,
    providers,
    runs,
    settings,
    snapshots,
    sources,
    targets,
)

api_router = APIRouter()

# Foundation (lane A).
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(settings.router)
api_router.include_router(credentials.router)
api_router.include_router(notifications.router)
api_router.include_router(config.router)

# Catalog and dashboard (lane B).
api_router.include_router(dashboard.router)
api_router.include_router(providers.router)
api_router.include_router(sources.router)
api_router.include_router(collections.router)
api_router.include_router(catalog_changes.router)
api_router.include_router(snapshots.router)

# Sync (lane C).
api_router.include_router(targets.router)
api_router.include_router(bindings.router)
api_router.include_router(previews.router)
api_router.include_router(runs.router)
