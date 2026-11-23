"""User-managed providers: no demo catalogue is required at startup."""

from __future__ import annotations

from app.services.seed import seed_sources
from tests.integration.factories import (
    assert_local_history_deleted,
    assert_no_episode_events,
    attach_local_history,
    provider_with_collection,
)


def test_seed_sources_leaves_providers_and_collections_empty(client, admin) -> None:
    assert seed_sources() == 0
    providers = client.get("/api/providers").json()
    collections = client.get("/api/collections").json()
    assert providers["total"] == 0
    assert collections["total"] == 0


def test_create_provider_with_manual_mappings(client, admin) -> None:
    assert seed_sources() == 0
    response = client.post(
        "/api/providers",
        json={
            "slug": "mio-provider",
            "name": "Mio Provider",
            "kind": "SVOD",
            "tmdb_movie_id": "9999",
            "tmdb_tv_id": "9998",
            "justwatch_short_name": "mio",
            "justwatch_technical_name": "mioprovider",
            "justwatch_monetization_types": ["FLATRATE"],
            "tvdb_company_id": "98765",
        },
        headers=admin,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["slug"] == "mio-provider"
    assert body["tmdb_provider_id_movie"] == "9999"
    assert body["tmdb_provider_id_tv"] == "9998"
    assert body["mapping_verified"] is False
    assert body["mapping_verified_movie"] is False
    assert body["mapping_verified_tv"] is False
    assert body["justwatch_provider_id"] == "mio"
    assert body["justwatch_verified"] is False
    assert body["justwatch_movie_verified"] is False
    assert body["justwatch_tv_verified"] is False
    assert body["justwatch_monetization_types"] == ["FLATRATE"]
    assert body["tvdb_company_id"] == "98765"

    # The manual mapping is usable by the collection builder but stays unverified.
    created = client.post(
        "/api/collections",
        json={
            "provider_id": body["id"],
            "media_type": "MOVIE",
            "name": "Mio catalogo",
            "slug": "mio-catalogo",
            "kind": "CATALOG",
        },
        headers=admin,
    )
    assert created.status_code == 201, created.text
    assert created.json()["provider_id"] == body["id"]
    assert created.json()["quality_flags"]["provider_mapping_verified"] is False

    justwatch_created = client.post(
        "/api/collections",
        json={
            "source_key": "justwatch",
            "provider_id": body["id"],
            "media_type": "MOVIE",
            "name": "Mio catalogo JustWatch",
            "slug": "mio-catalogo-justwatch",
            "kind": "CATALOG",
        },
        headers=admin,
    )
    assert justwatch_created.status_code == 201, justwatch_created.text
    assert justwatch_created.json()["filters"]["packages"] == ["mio"]
    assert justwatch_created.json()["quality_flags"]["provider_mapping_verified"] is False


def test_provider_detail_returns_country_aware_summary(client, admin) -> None:
    assert seed_sources() == 0
    created = client.post(
        "/api/providers",
        json={"slug": "detail-provider", "name": "Detail Provider"},
        headers=admin,
    )
    assert created.status_code == 201, created.text
    provider_id = created.json()["id"]

    response = client.get(f"/api/providers/{provider_id}?country=it")

    assert response.status_code == 200, response.text
    assert response.json()["id"] == provider_id
    assert response.json()["slug"] == "detail-provider"


def test_create_provider_validates_slug_and_duplicates(client, admin) -> None:
    assert seed_sources() == 0
    payload = {"slug": "provider-test", "name": "Provider Test"}
    assert client.post("/api/providers", json=payload, headers=admin).status_code == 201
    assert client.post("/api/providers", json=payload, headers=admin).status_code == 409
    assert (
        client.post(
            "/api/providers",
            json={"slug": "Not Valid", "name": "Bad"},
            headers=admin,
        ).status_code
        == 422
    )


def test_seed_providers_does_not_create_demo_collections(client, admin) -> None:
    from app.services.seed import seed_reference_data

    assert seed_reference_data() == 0
    assert client.get("/api/providers").json()["total"] == 12
    assert client.get("/api/collections").json()["total"] == 0


def test_delete_unused_provider_removes_it(client, admin) -> None:
    assert seed_sources() == 0
    created = client.post(
        "/api/providers",
        json={
            "slug": "da-eliminare",
            "name": "Da eliminare",
            "tmdb_movie_id": "12345",
            "justwatch_short_name": "del",
        },
        headers=admin,
    )
    assert created.status_code == 201, created.text
    provider_id = created.json()["id"]

    deleted = client.delete(f"/api/providers/{provider_id}", headers=admin)

    assert deleted.status_code == 204
    assert deleted.content == b""
    assert client.get(f"/api/providers/{provider_id}").status_code == 404


def test_delete_provider_with_collections_removes_local_data(client, admin) -> None:
    assert seed_sources() == 0
    provider, collection = provider_with_collection(client, admin)
    ids = attach_local_history(provider["id"], collection["id"], run_status="SUCCEEDED")

    response = client.delete(f"/api/providers/{provider['id']}", headers=admin)

    assert response.status_code == 204, response.text
    assert client.get(f"/api/providers/{provider['id']}").status_code == 404
    assert client.get(f"/api/collections/{collection['id']}").status_code == 404
    assert client.get("/api/collections").json()["total"] == 0
    assert_local_history_deleted(ids)
    assert_no_episode_events()


def test_delete_provider_is_blocked_while_a_sync_run_is_active(client, admin) -> None:
    assert seed_sources() == 0
    provider, collection = provider_with_collection(client, admin)
    ids = attach_local_history(provider["id"], collection["id"], run_status="APPLYING")

    response = client.delete(f"/api/providers/{provider['id']}", headers=admin)

    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "PROVIDER_RUN_ACTIVE"
    assert client.get(f"/api/providers/{provider['id']}").status_code == 200

    # Once the run is terminal the provider and its local collections can go.
    import uuid

    from app.core.time import utcnow
    from app.db.models import SyncRun
    from app.db.session import get_session_factory

    session = get_session_factory()()
    try:
        run = session.get(SyncRun, uuid.UUID(ids["run"]))
        assert run is not None
        run.status = "CANCELLED"
        run.finished_at = utcnow()
        session.commit()
    finally:
        session.close()

    deleted = client.delete(f"/api/providers/{provider['id']}", headers=admin)
    assert deleted.status_code == 204, deleted.text
    assert client.get(f"/api/providers/{provider['id']}").status_code == 404
