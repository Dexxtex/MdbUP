"""Credential endpoints: masked listing, encrypted storage, deletion, errors."""

from __future__ import annotations

import httpx
import respx
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models import Credential

SECRET = "tmdb-secret-value-123456"


def _credentials_by_kind(client: TestClient) -> dict[str, dict]:
    response = client.get("/api/credentials")
    assert response.status_code == 200, response.text
    return {item["kind"]: item for item in response.json()["items"]}


def test_credentials_require_authentication(client: TestClient) -> None:
    assert client.get("/api/credentials").status_code == 401


def test_credentials_start_missing(client: TestClient, admin: dict[str, str]) -> None:
    items = _credentials_by_kind(client)

    assert items["TMDB"]["configured"] is False
    assert items["TMDB"]["status"] == "MISSING"
    assert items["MDBLIST"]["status"] == "MISSING"
    assert items["JUSTWATCH"]["status"] == "UNAVAILABLE"


def test_put_credential_stores_ciphertext_only(
    client: TestClient, admin: dict[str, str], seeded: None
) -> None:
    put = client.put("/api/credentials/tmdb", json={"value": SECRET}, headers=admin)

    assert put.status_code == 204
    assert put.content == b""

    items = _credentials_by_kind(client)
    assert items["TMDB"]["configured"] is True
    assert items["TMDB"]["masked_hint"] == "\u2022\u2022\u2022\u20223456"
    assert items["TMDB"]["key_version"] == 1
    assert SECRET not in client.get("/api/credentials").text

    from app.db.session import get_session_factory

    with get_session_factory()() as session:
        row = session.scalar(select(Credential).where(Credential.key == "api_key"))
        assert row is not None
        assert SECRET.encode() not in row.ciphertext
        assert row.masked_hint == "\u2022\u2022\u2022\u20223456"


def test_put_credential_requires_configured_source(
    client: TestClient, admin: dict[str, str]
) -> None:
    response = client.put("/api/credentials/tmdb", json={"value": SECRET}, headers=admin)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SOURCE_NOT_AVAILABLE"


def test_delete_credential(client: TestClient, admin: dict[str, str], seeded: None) -> None:
    client.put("/api/credentials/tmdb", json={"value": SECRET}, headers=admin)

    delete = client.delete("/api/credentials/tmdb", headers=admin)
    assert delete.status_code == 204
    assert _credentials_by_kind(client)["TMDB"]["status"] == "MISSING"

    missing = client.delete("/api/credentials/tmdb", headers=admin)
    assert missing.status_code == 404


def test_unknown_credential_kind_is_rejected(client: TestClient, admin: dict[str, str]) -> None:
    response = client.put("/api/credentials/unknown", json={"value": SECRET}, headers=admin)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_UNKNOWN_CREDENTIAL_KIND"


def test_justwatch_is_unavailable(client: TestClient, admin: dict[str, str]) -> None:
    response = client.put("/api/credentials/justwatch", json={"value": SECRET}, headers=admin)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SOURCE_NOT_AVAILABLE"


def test_credential_write_requires_encryption_key(
    client: TestClient, admin: dict[str, str], seeded: None, app_settings
) -> None:
    app_settings.app_encryption_key = ""

    response = client.put("/api/credentials/tmdb", json={"value": SECRET}, headers=admin)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "ENCRYPTION_KEY_MISSING"


def test_verify_requires_configured_credential(
    client: TestClient, admin: dict[str, str], seeded: None
) -> None:
    response = client.post("/api/credentials/tmdb/verify", headers=admin)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CREDENTIAL_MISSING"


@respx.mock
def test_verify_configured_credential_returns_result(
    client: TestClient, admin: dict[str, str], seeded: None
) -> None:
    assert (
        client.put("/api/credentials/tmdb", json={"value": SECRET}, headers=admin).status_code
        == 204
    )
    respx.get("https://api.themoviedb.org/3/configuration").mock(
        return_value=httpx.Response(200, json={"images": {}})
    )

    response = client.post("/api/credentials/tmdb/verify", headers=admin)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["kind"] == "TMDB"
    assert body["ok"] is True
    assert body["status_code"] == 200


def test_source_scoped_credentials_keep_separate_identities(
    client: TestClient, admin: dict[str, str], seeded: None
) -> None:
    client.put("/api/credentials/tmdb", json={"value": "tmdb-secret-aaa111"}, headers=admin)
    items = _credentials_by_kind(client)
    assert items["TMDB"]["configured"] is True
    assert items["TVDB"]["configured"] is False
    assert items["TVDB"]["status"] == "MISSING"

    client.put("/api/credentials/tvdb", json={"value": "tvdb-secret-bbb222"}, headers=admin)
    items = _credentials_by_kind(client)
    assert items["TMDB"]["configured"] is True
    assert items["TVDB"]["configured"] is True
    assert items["TMDB"]["masked_hint"] != items["TVDB"]["masked_hint"]
