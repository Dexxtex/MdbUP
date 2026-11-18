"""Collection create/update API and TMDb genre catalogue."""

from __future__ import annotations

from app.db.session import get_session_factory
from app.repositories import providers as providers_repo
from app.repositories import sources as sources_repo


def _mark_netflix_verified() -> None:
    session = get_session_factory()()
    try:
        provider = providers_repo.get_provider_by_slug(session, "netflix")
        source = sources_repo.get_source_by_key(session, "tmdb")
        assert provider is not None and source is not None
        mapping = providers_repo.get_mapping(
            session,
            provider_id=provider.id,
            source_id=source.id,
            country_code="IT",
        )
        assert mapping is not None
        mapping.is_verified = True
        mapping.metadata_json = {
            **(mapping.metadata_json or {}),
            "movie_provider_id": "8",
            "tv_provider_id": "8",
            "movie_verified": True,
            "tv_verified": True,
        }
        session.commit()
    finally:
        session.close()


def _provider_id(client, slug: str) -> str:
    items = client.get("/api/providers").json()["items"]
    return next(item["id"] for item in items if item["slug"] == slug)


def _collection_id(client, slug: str) -> str:
    items = client.get("/api/collections").json()["items"]
    return next(item["id"] for item in items if item["slug"] == slug)


def test_genres_and_collection_create_update(client, admin, seeded) -> None:
    _mark_netflix_verified()
    genres = client.get("/api/genres?media_type=MOVIE").json()
    assert genres["media_type"] == "MOVIE"
    assert any(item["id"] == 28 and item["name"] == "Azione" for item in genres["items"])
    netflix_id = _provider_id(client, "netflix")

    created = client.post(
        "/api/collections",
        json={
            "provider_id": netflix_id,
            "media_type": "MOVIE",
            "name": "Netflix — Test Azione",
            "slug": "test-netflix-azione",
            "kind": "CATALOG",
            "genre_ids": [28, 12],
            "monetization_type": "FLATRATE",
        },
        headers=admin,
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["filters"]["with_genres"] == "28,12"
    assert body["filters"]["with_watch_monetization_types"] == "flatrate"
    assert body["kind"] == "CATALOG"
    assert body["date_basis"] == "UNKNOWN"

    updated = client.patch(
        f"/api/collections/{body['id']}",
        json={"name": "Netflix — Test Horror", "genre_ids": [27], "is_active": False},
        headers=admin,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "Netflix — Test Horror"
    assert updated.json()["filters"]["with_genres"] == "27"
    assert updated.json()["is_active"] is False

    source_id = _collection_id(client, "netflix-movie")
    derived = client.post(
        "/api/collections",
        json={
            "provider_id": netflix_id,
            "media_type": "MOVIE",
            "name": "Netflix — Appena rilevati test",
            "slug": "test-netflix-recenti",
            "kind": "RECENTLY_ADDED",
            "monetization_type": "FLATRATE",
            "window_days": 14,
            "source_collection_id": source_id,
        },
        headers=admin,
    )
    assert derived.status_code == 201, derived.text
    assert derived.json()["kind"] == "RECENTLY_ADDED"
    assert derived.json()["date_basis"] == "APP_FIRST_SEEN"
    assert derived.json()["filters"]["derivation"] == "RECENTLY_DETECTED"
    assert derived.json()["filters"]["window_days"] == 14
    assert derived.json()["filters"]["source_collection_id"] == source_id


def test_collection_create_rejects_unverified_provider(client, admin, seeded) -> None:
    mubi_id = _provider_id(client, "mubi")
    response = client.post(
        "/api/collections",
        json={
            "provider_id": mubi_id,
            "media_type": "MOVIE",
            "name": "MUBI — Test",
            "slug": "test-mubi",
            "genre_ids": [28],
        },
        headers=admin,
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "PROVIDER_NOT_VERIFIED"
