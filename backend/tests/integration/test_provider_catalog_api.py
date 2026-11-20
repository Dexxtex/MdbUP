"""Provider discovery: TMDb + JustWatch + optional TVDB company IDs."""

from __future__ import annotations

import httpx
import respx

from app.seed import seed_sources
from app.services.credentials import CredentialKind, set_secret

TMDB = "https://api.themoviedb.org/3"
JUSTWATCH = "https://apis.justwatch.com/graphql"


def _tmdb_payload(movie: bool) -> dict:
    if movie:
        results = [
            {"provider_id": 8, "provider_name": "Netflix", "logo_path": "/nfx.jpg"},
            {"provider_id": 337, "provider_name": "Disney Plus", "logo_path": "/dnp.jpg"},
        ]
    else:
        results = [{"provider_id": 8, "provider_name": "Netflix", "logo_path": "/nfx.jpg"}]
    return {"results": results}


def _justwatch_payload() -> dict:
    return {
        "data": {
            "packages": [
                {
                    "id": "1",
                    "shortName": "nfx",
                    "clearName": "Netflix",
                    "technicalName": "netflix",
                    "monetizationTypes": ["FLATRATE"],
                },
                {
                    "id": "2",
                    "shortName": "dnp",
                    "clearName": "Disney+",
                    "technicalName": "disneyplus",
                    "monetizationTypes": ["FLATRATE"],
                },
            ]
        }
    }


def _configure_tmdb(client, admin, app_settings) -> None:
    response = client.put("/api/credentials/tmdb", json={"value": "test-tmdb"}, headers=admin)
    assert response.status_code == 204, response.text


@respx.mock
def test_catalog_merges_tmdb_and_justwatch(client, admin, app_settings) -> None:
    assert seed_sources() == 0
    _configure_tmdb(client, admin, app_settings)
    respx.get(f"{TMDB}/watch/providers/movie").mock(
        return_value=httpx.Response(200, json=_tmdb_payload(True))
    )
    respx.get(f"{TMDB}/watch/providers/tv").mock(
        return_value=httpx.Response(200, json=_tmdb_payload(False))
    )
    respx.post(JUSTWATCH).mock(return_value=httpx.Response(200, json=_justwatch_payload()))

    response = client.get("/api/providers/catalog?country=IT")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 2
    netflix = next(item for item in body["items"] if item["name"] == "Netflix")
    assert netflix["tmdb_movie_id"] == "8"
    assert netflix["tmdb_tv_id"] == "8"
    assert netflix["justwatch_short_name"] == "nfx"
    assert netflix["available_in_country"] is True
    disney = next(item for item in body["items"] if item["name"] == "Disney Plus")
    assert disney["justwatch_short_name"] == "dnp"
    assert disney["sources"] == ["tmdb", "justwatch"]
    statuses = {item["source_key"]: item for item in body["sources"]}
    assert statuses["tmdb"]["status"] == "OK"
    assert statuses["justwatch"]["status"] == "OK"
    assert statuses["tvdb"]["status"] == "MISSING_CREDENTIAL"


@respx.mock
def test_catalog_adds_tvdb_company_without_country_claim(client, admin, app_settings) -> None:
    assert seed_sources() == 0
    _configure_tmdb(client, admin, app_settings)
    from app.db.session import get_session_factory

    with get_session_factory()() as session:
        set_secret(session, app_settings, CredentialKind.TVDB, "tvdb-key")
        session.commit()

    respx.get(f"{TMDB}/watch/providers/movie").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    respx.get(f"{TMDB}/watch/providers/tv").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    respx.post(JUSTWATCH).mock(return_value=httpx.Response(200, json={"data": {"packages": []}}))
    respx.post("https://api4.thetvdb.com/v4/login").mock(
        return_value=httpx.Response(200, json={"status": "success", "data": {"token": "t"}})
    )
    respx.get("https://api4.thetvdb.com/v4/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "success",
                "data": {
                    "items": [
                        {
                            "id": "123",
                            "name": "TVDB Only",
                            "company_type": "SVOD",
                            "slug": "tvdb-only",
                            "country": "ita",
                        }
                    ]
                },
            },
        )
    )

    response = client.get("/api/providers/catalog")

    assert response.status_code == 200, response.text
    body = response.json()
    item = next(item for item in body["items"] if item["name"] == "TVDB Only")
    assert item["tvdb_company_id"] == "123"
    assert item["country_code"] is None
    assert item["available_in_country"] is None
    assert item["sources"] == ["tvdb"]
    assert {entry["source_key"]: entry["status"] for entry in body["sources"]}["tvdb"] == "OK"


@respx.mock
def test_catalog_works_without_tmdb_or_tvdb_credentials(client, admin) -> None:
    assert seed_sources() == 0
    respx.post(JUSTWATCH).mock(return_value=httpx.Response(200, json={"data": {"packages": []}}))

    response = client.get("/api/providers/catalog")

    assert response.status_code == 200, response.text
    statuses = {item["source_key"]: item["status"] for item in response.json()["sources"]}
    assert statuses == {
        "tmdb": "MISSING_CREDENTIAL",
        "justwatch": "OK",
        "tvdb": "MISSING_CREDENTIAL",
    }
