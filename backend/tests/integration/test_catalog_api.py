"""Catalog/dashboard API integration tests (TestClient + SQLite)."""

from __future__ import annotations

import httpx
import respx

BASE = "https://api.themoviedb.org/3"

DISCOVER_MOVIE_PAYLOAD = {
    "page": 1,
    "total_pages": 1,
    "total_results": 2,
    "results": [
        {
            "id": 603,
            "title": "Matrix",
            "original_title": "The Matrix",
            "release_date": "1999-03-31",
            "popularity": 42.0,
        },
        {
            "id": 604,
            "title": "Matrix Reloaded",
            "original_title": "The Matrix Reloaded",
            "release_date": "2003-05-15",
            "popularity": 30.0,
        },
    ],
}


def _set_tmdb_credential(app_settings) -> None:
    from app.db.session import get_session_factory
    from app.services import credentials as credentials_service
    from app.services.credentials import CredentialKind

    session = get_session_factory()()
    try:
        credentials_service.set_secret(session, app_settings, CredentialKind.TMDB, "test-token")
    finally:
        session.close()


def _collection(client, slug: str) -> dict:
    items = client.get("/api/collections").json()["items"]
    return next(item for item in items if item["slug"] == slug)


def test_providers_list_includes_tmdb_mapping(client, admin, seeded) -> None:
    response = client.get("/api/providers")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 12
    netflix = next(item for item in body["items"] if item["slug"] == "netflix")
    assert netflix["tmdb_provider_id"] == "8"
    assert netflix["collections_count"] == 2
    assert netflix["movie_collections"] == 1
    assert netflix["show_collections"] == 1
    # No live TMDb call has verified the mapping yet.
    assert netflix["mapping_verified"] is False


def test_sources_expose_capabilities_and_disabled_justwatch(client, admin, seeded) -> None:
    body = client.get("/api/sources").json()
    by_key = {item["key"]: item for item in body["items"]}
    assert by_key["tmdb"]["capabilities"]["catalog"] is True
    assert by_key["tmdb"]["capabilities"]["added_dates"] is False
    assert by_key["tmdb"]["credential_configured"] is False
    assert by_key["tmdb"]["connector_available"] is True
    assert by_key["justwatch_partner"]["status"] == "DISABLED"
    assert by_key["justwatch_partner"]["requires_contract"] is True
    assert by_key["justwatch_partner"]["connector_available"] is False


def test_collections_filter_by_media_type_and_origin(client, admin, seeded) -> None:
    movies = client.get("/api/collections?media_type=MOVIE").json()
    assert movies["total"] == 12
    assert all(item["media_type"] == "MOVIE" for item in movies["items"])
    assert all(item["origin"] == "AGGREGATOR" for item in movies["items"])
    assert all(item["date_basis"] == "UNKNOWN" for item in movies["items"])
    assert all(item["offer_types"] == ["FLATRATE"] for item in movies["items"])

    custom = client.get("/api/collections?origin=CUSTOM").json()
    assert custom["total"] == 0


def test_collection_detail_without_snapshot(client, admin, seeded) -> None:
    target = _collection(client, "netflix-movie")
    body = client.get(f"/api/collections/{target['id']}").json()
    assert body["latest_snapshot"] is None
    assert body["last_valid_snapshot"] is None
    assert body["last_valid_snapshot_id"] is None
    assert body["provider_slug"] == "netflix"
    assert body["source_key"] == "tmdb"

    snapshots = client.get(f"/api/collections/{target['id']}/snapshots").json()
    assert snapshots["total"] == 0


def test_dashboard_reports_alerts(client, admin, seeded) -> None:
    body = client.get("/api/dashboard").json()
    assert body["counters"]["collections"] == 23
    assert body["counters"]["providers"] == 12
    # Only the contract-gated JustWatch Partner API stays disabled: the public
    # endpoint source is active (phase-8 spec).
    assert body["counters"]["sources_disabled"] == 1
    codes = {alert["code"] for alert in body["alerts"]}
    assert "CREDENTIAL_MISSING" in codes
    assert "SOURCE_DISABLED" in codes
    assert "COLLECTIONS_WITHOUT_SNAPSHOT" in codes


def test_seed_is_idempotent(client, admin, seeded) -> None:
    from app.services.seed import seed_reference_data

    assert seed_reference_data(include_collections=True) == 0
    assert client.get("/api/providers").json()["total"] == 12
    assert client.get("/api/collections").json()["total"] == 23
    netflix = next(
        item for item in client.get("/api/providers").json()["items"] if item["slug"] == "netflix"
    )
    assert netflix["tmdb_provider_id"] == "8"


def test_dashboard_includes_api_usage(client, admin, seeded) -> None:
    body = client.get("/api/dashboard").json()
    assert "api_usage" in body
    assert "tmdb" in body["api_usage"]
    assert "mdblist" in body["api_usage"]
    assert "estimated_per_day" in body["api_usage"]["tmdb"]


def test_dashboard_works_without_seed(client, admin) -> None:
    response = client.get("/api/dashboard")
    assert response.status_code == 200
    body = response.json()
    assert body["counters"]["collections"] == 0
    assert body["counters"]["providers"] == 0
    assert "CREDENTIAL_MISSING" in {alert["code"] for alert in body["alerts"]}
    assert client.get("/api/providers").json()["total"] == 0


def test_acquire_without_tmdb_credential_returns_409(client, admin, seeded) -> None:
    target = _collection(client, "netflix-movie")
    response = client.post(f"/api/collections/{target['id']}/acquire", headers=admin)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CREDENTIAL_MISSING"


def test_healthcheck_without_credential_returns_409(client, admin, seeded) -> None:
    sources = {item["key"]: item for item in client.get("/api/sources").json()["items"]}
    response = client.post(f"/api/sources/{sources['tmdb']['id']}/healthcheck", headers=admin)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CREDENTIAL_MISSING"


@respx.mock
def test_acquire_runs_eagerly_and_creates_valid_snapshot(
    client, admin, seeded, app_settings
) -> None:
    _set_tmdb_credential(app_settings)
    respx.get(f"{BASE}/discover/movie").mock(
        return_value=httpx.Response(200, json=DISCOVER_MOVIE_PAYLOAD)
    )
    target = _collection(client, "netflix-movie")

    response = client.post(f"/api/collections/{target['id']}/acquire", headers=admin)
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "SUCCEEDED"
    assert body["snapshot_id"] is not None
    snapshot_id = body["snapshot_id"]

    detail = client.get(f"/api/collections/{target['id']}").json()
    assert detail["last_valid_snapshot_id"] == snapshot_id
    assert detail["latest_snapshot"]["is_valid"] is True
    assert detail["latest_snapshot"]["status"] == "COMPLETE"
    assert detail["latest_snapshot"]["quality"] == "CLEAN"
    assert detail["latest_snapshot"]["items_count"] == 2
    assert detail["latest_snapshot"]["checksum"] is not None

    history = client.get(f"/api/collections/{target['id']}/snapshots").json()
    assert history["total"] == 1
    assert history["items"][0]["id"] == snapshot_id

    items = client.get(f"/api/snapshots/{snapshot_id}/items").json()
    assert items["total"] == 2
    assert items["items"][0]["title"] == "Matrix"
    assert items["items"][0]["tmdb_id"] == 603
    assert items["items"][0]["resolution_status"] == "RESOLVED"
    assert items["items"][0]["media_id"] is not None

    paged = client.get(f"/api/snapshots/{snapshot_id}/items?page=2&page_size=1").json()
    assert paged["total"] == 2
    assert paged["items"][0]["position"] == 1

    searched = client.get(f"/api/snapshots/{snapshot_id}/items?search=RELOADED").json()
    assert searched["total"] == 1
    assert searched["items"][0]["title"] == "Matrix Reloaded"
    assert searched["items"][0]["position"] == 1

    searched_page = client.get(
        f"/api/snapshots/{snapshot_id}/items?search=matrix&page=2&page_size=1"
    ).json()
    assert searched_page["total"] == 2
    assert searched_page["items"][0]["title"] == "Matrix Reloaded"

    empty = client.get(f"/api/snapshots/{snapshot_id}/items?search=inesistente").json()
    assert empty["total"] == 0
    assert empty["items"] == []

    dashboard = client.get("/api/dashboard").json()
    assert dashboard["counters"]["media"] == 2
    assert dashboard["counters"]["valid_snapshots"] == 1
    assert dashboard["recent_jobs"][0]["status"] == "SUCCEEDED"


@respx.mock
def test_healthcheck_uses_connector_and_updates_source(client, admin, seeded, app_settings) -> None:
    _set_tmdb_credential(app_settings)
    respx.get(f"{BASE}/configuration").mock(return_value=httpx.Response(200, json={"images": {}}))
    sources = {item["key"]: item for item in client.get("/api/sources").json()["items"]}

    response = client.post(f"/api/sources/{sources['tmdb']['id']}/healthcheck", headers=admin)
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["status"] == "OK"
    assert body["source_key"] == "tmdb"

    refreshed = {item["key"]: item for item in client.get("/api/sources").json()["items"]}
    assert refreshed["tmdb"]["status"] == "OK"
    assert refreshed["tmdb"]["last_healthcheck_at"] is not None


def test_healthcheck_disabled_justwatch_is_rejected(client, admin, seeded) -> None:
    sources = {item["key"]: item for item in client.get("/api/sources").json()["items"]}
    response = client.post(
        f"/api/sources/{sources['justwatch_partner']['id']}/healthcheck", headers=admin
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SOURCE_NOT_AVAILABLE"
