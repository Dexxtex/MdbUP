"""TheTVDB source endpoints: metadata only, no country availability."""

from __future__ import annotations

import httpx
import respx

from app.services.credentials import CredentialKind, set_secret
from app.services.seed import seed_sources

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
                "data": [
                    {
                        "id": "company-123",
                        "name": "TVDB Service",
                        "company_type": "Network",
                        "slug": "tvdb-service",
                        "country": "usa",
                    }
                ],
            },
        )
    )


@respx.mock
def test_tvdb_companies_and_healthcheck(client, admin, app_settings) -> None:
    _configure(client, admin, app_settings)
    _mock_companies()

    response = client.get("/api/sources/tvdb/companies?q=service")

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


@respx.mock
def test_tvdb_genre_and_year_catalog(client, admin, app_settings) -> None:
    _configure(client, admin, app_settings)
    respx.post(f"{TVDB}/login").mock(
        return_value=httpx.Response(200, json={"status": "success", "data": {"token": "t"}})
    )
    respx.get(f"{TVDB}/genres").mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "success",
                "data": [{"id": 3, "name": "Drama", "slug": "drama"}],
            },
        )
    )
    filter_route = respx.get(f"{TVDB}/series/filter").mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "success",
                "data": [
                    {
                        "id": 42,
                        "name": "Example",
                        "year": "2024",
                        "score": 12.5,
                        "slug": "example",
                    }
                ],
            },
        )
    )

    genres = client.get("/api/sources/tvdb/genres")
    assert genres.status_code == 200, genres.text
    assert genres.json()["items"][0]["name"] == "Drama"

    catalog = client.get("/api/sources/tvdb/series?genre_id=3&year=2024&country=ita&language=ita")
    assert catalog.status_code == 200, catalog.text
    body = catalog.json()
    assert body["total"] == 1
    assert body["items"][0]["item_id"] == "42"
    assert body["items"][0]["score"] == 12.5
    assert filter_route.called
    params = filter_route.calls[-1].request.url.params
    assert params["country"] == "ita"
    assert params["lang"] == "ita"
    assert params["genre"] == "3"
    assert params["year"] == "2024"

    defaults = client.get("/api/sources/tvdb/series")
    assert defaults.status_code == 200, defaults.text
    default_params = filter_route.calls[-1].request.url.params
    assert default_params["country"] == "ita"
    assert default_params["lang"] == "ita"
    assert "genre" not in default_params
    assert "year" not in default_params


@respx.mock
def test_tvdb_auth_failure_maps_to_source_error(client, admin, app_settings) -> None:
    _configure(client, admin, app_settings)
    respx.post(f"{TVDB}/login").mock(return_value=httpx.Response(401))

    response = client.get("/api/sources/tvdb/genres")

    assert response.status_code == 409, response.text
    error = response.json()["error"]
    assert error["code"] == "SOURCE_AUTH_FAILED"
    assert error["category"] == "SOURCE"
    assert error["retryable"] is False


@respx.mock
def test_tvdb_request_failure_maps_to_source_unavailable(client, admin, app_settings) -> None:
    _configure(client, admin, app_settings)
    respx.post(f"{TVDB}/login").mock(
        return_value=httpx.Response(200, json={"status": "success", "data": {"token": "t"}})
    )
    respx.get(f"{TVDB}/search").mock(return_value=httpx.Response(400))

    response = client.get("/api/sources/tvdb/companies?q=netflix")

    assert response.status_code == 503, response.text
    error = response.json()["error"]
    assert error["code"] == "SOURCE_UNAVAILABLE"
    assert error["category"] == "SOURCE"
    assert error["retryable"] is True
