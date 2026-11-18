"""Runtime settings: defaults, validation, persistence."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_settings_require_authentication(client: TestClient) -> None:
    assert client.get("/api/settings").status_code == 401


def test_settings_expose_defaults(client: TestClient, admin: dict[str, str]) -> None:
    response = client.get("/api/settings")

    assert response.status_code == 200
    items = {item["key"]: item for item in response.json()["items"]}
    assert items["sync_batch_size"]["value"] == 100
    assert items["sync_max_removal_percent"]["value"] == 10.0
    assert items["sync_batch_size"]["updated_at"] is None


def test_patch_persists_value(client: TestClient, admin: dict[str, str]) -> None:
    response = client.patch("/api/settings", json={"items": {"sync_batch_size": 25}}, headers=admin)

    assert response.status_code == 200
    items = {item["key"]: item for item in response.json()["items"]}
    assert items["sync_batch_size"]["value"] == 25
    assert items["sync_batch_size"]["updated_at"] is not None

    reread = client.get("/api/settings").json()["items"]
    assert {item["key"]: item["value"] for item in reread}["sync_batch_size"] == 25


def test_patch_rejects_unknown_key(client: TestClient, admin: dict[str, str]) -> None:
    response = client.patch("/api/settings", json={"items": {"unknown_setting": 1}}, headers=admin)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_UNKNOWN_SETTING"


def test_patch_rejects_wrong_type(client: TestClient, admin: dict[str, str]) -> None:
    response = client.patch(
        "/api/settings", json={"items": {"sync_batch_size": "many"}}, headers=admin
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_INVALID_SETTING"


def test_patch_rejects_out_of_range(client: TestClient, admin: dict[str, str]) -> None:
    response = client.patch(
        "/api/settings", json={"items": {"sync_max_removal_percent": 150}}, headers=admin
    )

    assert response.status_code == 422
