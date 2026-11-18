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
    assert items["default_source"]["value"] == "justwatch"
    assert "JustWatch" in items["default_source"]["description"]
    assert items["catalog_schedule_enabled"]["value"] is True
    assert "JustWatch" in items["catalog_schedule_enabled"]["description"]


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


def test_patch_default_source_accepts_only_the_supported_values(
    client: TestClient, admin: dict[str, str]
) -> None:
    accepted = client.patch(
        "/api/settings", json={"items": {"default_source": "tmdb"}}, headers=admin
    )
    assert accepted.status_code == 200, accepted.text
    values = {item["key"]: item["value"] for item in accepted.json()["items"]}
    assert values["default_source"] == "tmdb"

    rejected = client.patch(
        "/api/settings", json={"items": {"default_source": "mdblist"}}, headers=admin
    )
    assert rejected.status_code == 422
    assert rejected.json()["error"]["code"] == "VALIDATION_INVALID_SETTING"


def test_patch_catalog_schedule_enabled(client: TestClient, admin: dict[str, str]) -> None:
    response = client.patch(
        "/api/settings", json={"items": {"catalog_schedule_enabled": False}}, headers=admin
    )

    assert response.status_code == 200, response.text
    values = {item["key"]: item["value"] for item in response.json()["items"]}
    assert values["catalog_schedule_enabled"] is False


def test_default_source_round_trips_through_config_export(
    client: TestClient, admin: dict[str, str], seeded
) -> None:
    exported = client.get("/api/config/export").json()
    assert exported["settings"]["default_source"] == "justwatch"
    assert exported["settings"]["catalog_schedule_enabled"] is True

    client.patch("/api/settings", json={"items": {"default_source": "tmdb"}}, headers=admin)
    changed = client.get("/api/config/export").json()
    assert changed["settings"]["default_source"] == "tmdb"

    client.patch("/api/settings", json={"items": {"default_source": "justwatch"}}, headers=admin)
    imported = client.post("/api/config/import", json=changed, headers=admin)
    assert imported.status_code == 200, imported.text
    settings = {item["key"]: item["value"] for item in client.get("/api/settings").json()["items"]}
    assert settings["default_source"] == "tmdb"
