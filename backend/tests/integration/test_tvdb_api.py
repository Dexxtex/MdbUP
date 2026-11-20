"""TheTVDB source endpoints: metadata only, no country availability."""

from __future__ import annotations

import httpx
import respx

from app.seed import seed_sources
from app.services.credentials import CredentialKind, set_secret

TVDB = "https://api4.thetvdb.com/v4"


def _configure(client, admin, app_settings) -> None:
    assert seed_sources() == 0
    from app.db.session import get_session_factory

    with get_session_factory()() as session:
        set_secret(session, app_settings, CredentialKind.TVDB, "tvdb-key")
        session.commit()
    assert client.get("/api/sources").status_code == 200
    assert admin


def _mock_companies() -> None:
    respx.post(f"{TVDB}/login").mock(
        return_value=httpx.Response(200, json={"status": "success", "data": {"token": "t"}})
    )
    respx.get(f"{TVDB}/companies").mock(
        return_value=httpx.Response(200, json={"status": "success", "data": []})
    )
    respx.get(f"{TVDB}/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "success",
                "data": {
                    "items": [
                        {
                            "id": "123",
                            "name": "TVDB Service",
                            "company_type": "SVOD",
                            "slug": "tvdb-service",
                            "country": "usa",
                        }
                    ]
                },
            },
        )
    )


@respx.mock
def test_tvdb_companies_and_healthcheck(client, admin, app_settings) -> None:
    _configure(client, admin, app_settings)
    _mock_companies()

    response = client.get("/api/sources/tvdb/companies")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["company_id"] == "123"
    assert body["items"][0]["country"] == "usa"

    sources = client.get("/api/sources").json()["items"]
    tvdb = next(item for item in sources if item["key"] == "tvdb")
    assert tvdb["connector_available"] is True
    assert tvdb["credential_configured"] is True

    health = client.post(
        f"/api/sources/{tvdb['id']}/healthcheck",
        headers=admin,
    )
    assert health.status_code == 200, health.text
    assert health.json()["ok"] is True
    assert health.json()["source_key"] == "tvdb"
