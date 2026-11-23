"""Provider discovery: TMDb + JustWatch + optional TVDB company IDs."""

from __future__ import annotations

import httpx
import respx

from app.services.credentials import CredentialKind, set_secret
from app.services.seed import seed_sources

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
def test_catalog_keeps_tmdb_and_justwatch_separate(client, admin, app_settings) -> None:
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
    assert body["total"] == 4
    netflix_tmdb = next(
        item for item in body["items"] if item["name"] == "Netflix" and item["source_key"] == "tmdb"
    )
    assert netflix_tmdb["tmdb_movie_id"] == "8"
    assert netflix_tmdb["tmdb_tv_id"] == "8"
    assert netflix_tmdb["justwatch_short_name"] is None
    assert netflix_tmdb["sources"] == ["tmdb"]
    netflix_jw = next(
        item
        for item in body["items"]
        if item["name"] == "Netflix" and item["source_key"] == "justwatch"
    )
    assert netflix_jw["tmdb_movie_id"] is None
    assert netflix_jw["justwatch_short_name"] == "nfx"
    assert netflix_jw["sources"] == ["justwatch"]
    disney_tmdb = next(
        item
        for item in body["items"]
        if item["name"] == "Disney Plus" and item["source_key"] == "tmdb"
    )
    disney_jw = next(
        item
        for item in body["items"]
        if item["name"] == "Disney+" and item["source_key"] == "justwatch"
    )
    assert disney_tmdb["tmdb_movie_id"] == "337"
    assert disney_jw["justwatch_short_name"] == "dnp"
    statuses = {item["source_key"]: item for item in body["sources"]}
    assert statuses["tmdb"]["status"] == "OK"
    assert statuses["justwatch"]["status"] == "OK"
    assert statuses["tvdb"]["status"] == "MISSING_CREDENTIAL"


@respx.mock
def test_catalog_marks_tvdb_as_manual_only(client, admin, app_settings) -> None:
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
    response = client.get("/api/providers/catalog")

    assert response.status_code == 200, response.text
    body = response.json()
    assert not any(item["source_key"] == "tvdb" for item in body["items"])
    statuses = {entry["source_key"]: entry for entry in body["sources"]}
    assert statuses["tvdb"]["status"] == "MANUAL_ONLY"
    assert statuses["tvdb"]["count"] == 0


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
