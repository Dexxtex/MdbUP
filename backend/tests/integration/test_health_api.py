"""Health and readiness endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import APP_VERSION


def test_health_is_always_ok(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": APP_VERSION}


def test_ready_reports_dependency_checks(client: TestClient) -> None:
    response = client.get("/api/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["checks"]["db"] is True
    assert body["checks"]["encryption_key"] is True
    # No Redis in the test environment: degraded, but the API is still usable.
    assert body["checks"]["redis"] is False
    assert body["status"] == "degraded"


def test_ready_reports_missing_encryption_key(client: TestClient, app_settings) -> None:
    app_settings.app_encryption_key = ""

    response = client.get("/api/ready")

    assert response.status_code == 200
    assert response.json()["checks"]["encryption_key"] is False
