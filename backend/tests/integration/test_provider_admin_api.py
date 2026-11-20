"""User-managed providers: no demo catalogue is required at startup."""

from __future__ import annotations

from app.seed import seed_sources


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
        },
        headers=admin,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["slug"] == "mio-provider"
    assert body["mapping_verified_movie"] is True
    assert body["mapping_verified_tv"] is True
    assert body["justwatch_provider_id"] == "mio"
    assert body["justwatch_movie_verified"] is True
    assert body["justwatch_tv_verified"] is True

    # The user-created mapping is usable by the collection builder.
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
