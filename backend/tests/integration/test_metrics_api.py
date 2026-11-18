"""Prometheus endpoint: token auth, content type and metric families."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

TOKEN = "metrics-test-token"


def _backup_status_file(tmp_path, *, status: str = "OK", hours_ago: int = 2):
    moment = datetime.now(UTC) - timedelta(hours=hours_ago)
    path = tmp_path / "last_backup.json"
    path.write_text(
        json.dumps(
            {
                "timestamp": moment.isoformat().replace("+00:00", "Z"),
                "file": "mdbup-20261118T100000Z.dump.age",
                "size": 1024,
                "sha256": "b" * 64,
                "status": status,
                "error": None,
            }
        ),
        encoding="utf-8",
    )
    return path, moment


def test_metrics_returns_503_without_a_configured_token(client: TestClient, app_settings) -> None:
    app_settings.metrics_token = ""

    response = client.get("/api/metrics")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "METRICS_TOKEN_MISSING"


def test_metrics_requires_the_header(client: TestClient, app_settings) -> None:
    app_settings.metrics_token = TOKEN

    response = client.get("/api/metrics")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "METRICS_TOKEN_REQUIRED"


def test_metrics_rejects_a_wrong_token(client: TestClient, app_settings) -> None:
    app_settings.metrics_token = TOKEN

    response = client.get("/api/metrics", headers={"Authorization": "Bearer nope"})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "METRICS_TOKEN_INVALID"


def test_metrics_can_be_disabled(client: TestClient, app_settings) -> None:
    app_settings.metrics_token = TOKEN
    app_settings.metrics_enabled = False

    response = client.get("/api/metrics", headers={"Authorization": f"Bearer {TOKEN}"})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "METRICS_DISABLED"


def test_metrics_exposes_prometheus_text(
    client: TestClient, app_settings, seeded, tmp_path
) -> None:
    app_settings.metrics_token = TOKEN
    status_file, moment = _backup_status_file(tmp_path)
    app_settings.backup_dir = str(tmp_path)
    app_settings.backup_status_file = str(status_file)

    response = client.get("/api/metrics", headers={"Authorization": f"Bearer {TOKEN}"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain; version=0.0.4")
    body = response.text
    assert "# TYPE mdbup_up gauge" in body
    assert "mdbup_up 1" in body
    assert "mdbup_database_up 1" in body
    assert "mdbup_redis_up 0" in body
    assert "mdbup_encryption_key_ready 1" in body
    assert "mdbup_worker_up 0" in body
    assert 'mdbup_service_up{service="tmdb"} 0' in body
    assert 'mdbup_service_up{service="mdblist"} 0' in body
    for queue in ("celery", "maintenance", "sync", "acquisitions"):
        assert f'mdbup_celery_queue_depth{{queue="{queue}"}} 0' in body
    for status in ("SUCCEEDED", "FAILED", "AWAITING_APPROVAL", "PARTIAL"):
        assert f'mdbup_sync_runs{{status="{status}"}} 0' in body
    assert 'mdbup_api_calls{provider="tmdb",window="hour"} 0' in body
    assert 'mdbup_api_calls{provider="mdblist",window="day"} 0' in body
    assert f"mdbup_last_backup_valid_timestamp_seconds {int(moment.timestamp())}" in body
    assert "mdbup_backup_status_ok 1" in body
    assert "mdbup_pending_approvals 0" in body


def test_metrics_accepts_the_x_metrics_token_header(
    client: TestClient, app_settings, seeded
) -> None:
    app_settings.metrics_token = TOKEN

    response = client.get("/api/metrics", headers={"X-Metrics-Token": TOKEN})

    assert response.status_code == 200
    assert "mdbup_up 1" in response.text


def test_metrics_reports_zero_without_a_backup_status_file(
    client: TestClient, app_settings, seeded, tmp_path
) -> None:
    app_settings.metrics_token = TOKEN
    app_settings.backup_dir = str(tmp_path)
    app_settings.backup_status_file = str(tmp_path / "absent.json")

    body = client.get("/api/metrics", headers={"X-Metrics-Token": TOKEN}).text

    assert "mdbup_last_backup_valid_timestamp_seconds 0" in body
    assert "mdbup_backup_status_ok 0" in body
    assert "mdbup_backup_age_hours -1" in body
