"""Configuration export/import: portable, secret-free and idempotent."""

from __future__ import annotations

import json


def test_export_contains_no_secrets_and_import_is_idempotent(client, admin, seeded) -> None:
    exported = client.get("/api/config/export")
    assert exported.status_code == 200, exported.text
    payload = exported.json()
    assert payload["version"] == 1
    assert len(payload["providers"]) == 12
    assert len(payload["collections"]) == 23
    serialized = json.dumps(payload).lower()
    for forbidden in ("ciphertext", "api_key", "app_encryption", "password", "bearer "):
        assert forbidden not in serialized
    assert all("mappings" in provider for provider in payload["providers"])

    imported = client.post("/api/config/import", json=payload, headers=admin)
    assert imported.status_code == 200, imported.text
    result = imported.json()
    assert result["providers"] == 12
    assert result["collections"] == 23
    assert result["bindings"] == 0
    assert result["settings"] >= 1

    collections = client.get("/api/collections").json()
    assert collections["total"] == 23
    providers = client.get("/api/providers").json()
    assert providers["total"] == 12


def test_import_rejects_unknown_version(client, admin, seeded) -> None:
    response = client.post("/api/config/import", json={"version": 999}, headers=admin)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "CONFIG_VERSION_UNSUPPORTED"
