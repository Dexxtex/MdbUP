"""JustWatch read model, collection creation and binding guardrails through the API.

The JustWatch endpoint and the MDBList API are both mocked with respx: no real
list is ever read or written.
"""

from __future__ import annotations

import uuid

import httpx
import respx

BASE_JUSTWATCH = "https://apis.justwatch.com/graphql"
BASE_MDBLIST = "https://api.mdblist.com"

_PACKAGES = [
    {
        "id": 8,
        "shortName": "nfx",
        "technicalName": "netflix",
        "clearName": "Netflix",
        "monetizationTypes": ["FLATRATE"],
    }
]


def _mock_packages() -> None:
    respx.post(BASE_JUSTWATCH).mock(
        return_value=httpx.Response(200, json={"data": {"packages": _PACKAGES}})
    )


def _sync_justwatch(app_settings) -> None:
    from app.db.session import session_scope
    from app.services import justwatch_collections

    with session_scope() as session:
        justwatch_collections.sync_collections(session, app_settings, provider_slugs=["netflix"])


def _provider_id(client, slug: str) -> str:
    items = client.get("/api/providers").json()["items"]
    return next(item["id"] for item in items if item["slug"] == slug)


def _collection(client, slug: str) -> dict:
    items = client.get("/api/collections").json()["items"]
    return next(item for item in items if item["slug"] == slug)


def _set_mdblist_credential(app_settings) -> None:
    from app.db.session import get_session_factory
    from app.services import credentials as credentials_service
    from app.services.credentials import CredentialKind

    session = get_session_factory()()
    try:
        credentials_service.set_secret(
            session, app_settings, CredentialKind.MDBLIST, "test-mdblist-key"
        )
    finally:
        session.close()


def _create_snapshot(collection_id: str, tmdb_ids: list[int], media_type: str) -> str:
    from app.db.models import Collection, CollectionSnapshot, SnapshotItem
    from app.db.session import get_session_factory
    from app.repositories import media as media_repo

    session = get_session_factory()()
    try:
        collection = session.get(Collection, uuid.UUID(collection_id))
        assert collection is not None
        media_ids = []
        for tmdb_id in tmdb_ids:
            media = media_repo.resolve_media(
                session,
                media_type=media_type,
                tmdb_id=tmdb_id,
                imdb_id=None,
                title=f"Media {tmdb_id}",
                year=2020,
            )
            assert media is not None
            media_ids.append(media.id)
        snapshot = CollectionSnapshot(
            collection_id=collection.id,
            status="COMPLETE",
            quality="CLEAN",
            is_valid=True,
            items_count=len(media_ids),
            resolved_count=len(media_ids),
            unresolved_count=0,
            duplicate_count=0,
            error_count=0,
            checksum="checksum",
        )
        session.add(snapshot)
        session.flush()
        for position, media_id in enumerate(media_ids):
            session.add(
                SnapshotItem(
                    snapshot_id=snapshot.id,
                    media_id=media_id,
                    position=position,
                    source_payload={"id": f"jw-{position}"},
                    date_basis="UNKNOWN",
                    resolution_status="RESOLVED",
                )
            )
        collection.last_valid_snapshot_id = snapshot.id
        session.commit()
        return str(media_ids[0])
    finally:
        session.close()


def _create_target(mediatype: str = "MOVIE", remote_list_id: int = 42) -> str:
    from app.db.session import get_session_factory
    from app.repositories import targets as targets_repo

    session = get_session_factory()()
    try:
        target = targets_repo.create_target(
            session, remote_list_id=remote_list_id, name="Test list", mediatype=mediatype
        )
        session.commit()
        return str(target.id)
    finally:
        session.close()


def _add_episode_event(collection_id: str, media_id: str, source_key: str) -> None:
    from app.core.time import utcnow
    from app.db.models import Collection, EpisodeEvent
    from app.db.session import get_session_factory
    from app.repositories import sources as sources_repo

    session = get_session_factory()()
    try:
        collection = session.get(Collection, uuid.UUID(collection_id))
        assert collection is not None
        source = sources_repo.get_source_by_key(session, source_key)
        assert source is not None
        session.add(
            EpisodeEvent(
                show_media_id=uuid.UUID(media_id),
                media_type="SHOW",
                provider_id=collection.provider_id,
                country_code=collection.country_code,
                source_id=source.id,
                event_type="EPISODE_ADDED",
                season_number=2,
                episode_number=5,
                occurred_at=utcnow(),
                source_payload={"source": source_key},
            )
        )
        session.commit()
    finally:
        session.close()


def _mock_mdblist(remote_ids: list[int]) -> None:
    respx.get(f"{BASE_MDBLIST}/lists/42").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": 42,
                "name": "Test list",
                "slug": "test-list",
                "private": False,
                "mediatype": "movie",
                "user_id": 5,
                "user_name": "owner",
                "items": 0,
            },
        )
    )
    respx.get(f"{BASE_MDBLIST}/user").mock(
        return_value=httpx.Response(200, json={"id": 5, "user_name": "owner"})
    )
    respx.get(f"{BASE_MDBLIST}/lists/42/items").mock(
        return_value=httpx.Response(
            200,
            headers={"X-Has-More": "false"},
            json={
                "movies": [{"ids": {"tmdb": tmdb_id}, "title": "m"} for tmdb_id in remote_ids],
                "shows": [],
                "pagination": {},
            },
        )
    )
    respx.post(f"{BASE_MDBLIST}/lists/42/items/add").mock(
        return_value=httpx.Response(200, json={"added": {"movies": 1}})
    )
    respx.post(f"{BASE_MDBLIST}/lists/42/items/remove").mock(
        return_value=httpx.Response(200, json={"removed": {"movies": 1}})
    )


@respx.mock
def test_sources_expose_the_justwatch_runtime_block(client, admin, seeded, app_settings) -> None:
    _mock_packages()
    _sync_justwatch(app_settings)

    body = client.get("/api/sources").json()
    justwatch = next(item for item in body["items"] if item["key"] == "justwatch")
    block = justwatch["justwatch"]
    assert block["throttle_ms"] == 1000
    assert block["cache_ttl_seconds"] == 300
    assert block["cache_max_entries"] == 512
    assert block["requests_hour"] >= 0
    assert block["requests_today"] >= 0
    assert "cache_hits" in block and "cache_misses" in block
    assert "CHART" in block["supported_kinds"]
    assert "UPCOMING" in block["supported_kinds"]
    assert block["supported_offer_types"] == ["FLATRATE"]
    assert len(block["mappings"]) == 1
    mapping = block["mappings"][0]
    assert mapping["provider_slug"] == "netflix"
    assert mapping["external_id"] == "nfx"
    assert mapping["technical_name"] == "netflix"
    assert mapping["clear_name"] == "Netflix"
    assert mapping["monetization_types"] == ["FLATRATE"]
    assert mapping["collections_count"] == 8

    # Other sources do not carry the JustWatch block.
    tmdb = next(item for item in body["items"] if item["key"] == "tmdb")
    assert tmdb["justwatch"] is None


@respx.mock
def test_providers_expose_the_justwatch_mapping(client, admin, seeded, app_settings) -> None:
    _mock_packages()
    _sync_justwatch(app_settings)

    body = client.get("/api/providers").json()
    netflix = next(item for item in body["items"] if item["slug"] == "netflix")
    assert netflix["justwatch_provider_id"] == "nfx"
    assert netflix["justwatch_verified"] is True
    assert netflix["justwatch_movie_verified"] is True
    assert netflix["justwatch_tv_verified"] is True
    assert netflix["justwatch_monetization_types"] == ["FLATRATE"]

    mubi = next(item for item in body["items"] if item["slug"] == "mubi")
    assert mubi["justwatch_provider_id"] is None
    assert mubi["justwatch_verified"] is False
    assert mubi["justwatch_movie_verified"] is False
    assert mubi["justwatch_tv_verified"] is False


@respx.mock
def test_create_justwatch_chart_collection(client, admin, seeded, app_settings) -> None:
    _mock_packages()
    _sync_justwatch(app_settings)
    provider_id = _provider_id(client, "netflix")

    response = client.post(
        "/api/collections",
        json={
            "source_key": "justwatch",
            "provider_id": provider_id,
            "media_type": "MOVIE",
            "name": "Netflix — Classifica test",
            "slug": "netflix-chart-test",
            "kind": "CHART",
        },
        headers=admin,
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["origin"] == "AGGREGATOR"
    assert body["date_basis"] == "UNKNOWN"
    assert body["kind"] == "CHART"
    assert body["source_label"] == "Classifica JustWatch"
    assert body["offer_types"] == ["FLATRATE"]
    assert body["filters"]["packages"] == ["nfx"]
    assert body["filters"]["offer_types"] == ["FLATRATE"]
    assert body["filters"]["media_type"] == "MOVIE"


@respx.mock
def test_create_justwatch_collection_requires_a_verified_mapping(
    client, admin, seeded, app_settings
) -> None:
    _mock_packages()
    _sync_justwatch(app_settings)
    mubi_id = _provider_id(client, "mubi")

    response = client.post(
        "/api/collections",
        json={
            "source_key": "justwatch",
            "provider_id": mubi_id,
            "media_type": "MOVIE",
            "name": "MUBI — Catalogo test",
            "slug": "mubi-catalog-test",
            "kind": "CATALOG",
        },
        headers=admin,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "PROVIDER_NOT_VERIFIED"


@respx.mock
def test_create_justwatch_collection_rejects_tmdb_only_kinds(
    client, admin, seeded, app_settings
) -> None:
    _mock_packages()
    _sync_justwatch(app_settings)
    provider_id = _provider_id(client, "netflix")

    response = client.post(
        "/api/collections",
        json={
            "source_key": "justwatch",
            "provider_id": provider_id,
            "media_type": "MOVIE",
            "name": "Netflix — Filtro locale",
            "slug": "netflix-local-filter",
            "kind": "CUSTOM_FILTER",
        },
        headers=admin,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "KIND_NOT_SUPPORTED"


@respx.mock
def test_justwatch_binding_requires_policy_and_starts_disabled(
    client, admin, seeded, app_settings
) -> None:
    _mock_packages()
    _sync_justwatch(app_settings)
    collection = _collection(client, "netflix-movie-justwatch")
    target_id = _create_target()
    payload = {
        "collection_id": collection["id"],
        "target_id": target_id,
        "mode": "MIRROR",
        "schedule": "MANUAL",
        "thresholds": {"max_removal_pct": 100, "max_removal_abs": 100},
        "enabled": True,
        "policy_version": "v1",
    }

    rejected = client.post("/api/bindings", json=payload, headers=admin)
    assert rejected.status_code == 422
    assert rejected.json()["error"]["code"] == "JUSTWATCH_POLICY_NOT_ACCEPTED"

    accepted = client.post(
        "/api/bindings",
        json={**payload, "justwatch_policy_accepted": True},
        headers=admin,
    )
    assert accepted.status_code == 201, accepted.text
    assert accepted.json()["enabled"] is False


@respx.mock
def test_justwatch_real_run_requires_a_successful_dry_run(
    client, admin, seeded, app_settings
) -> None:
    _mock_packages()
    _sync_justwatch(app_settings)
    _set_mdblist_credential(app_settings)
    collection = _collection(client, "netflix-movie-justwatch")
    _create_snapshot(collection["id"], [1], "MOVIE")
    target_id = _create_target()
    created = client.post(
        "/api/bindings",
        json={
            "collection_id": collection["id"],
            "target_id": target_id,
            "mode": "MIRROR",
            "schedule": "MANUAL",
            "thresholds": {"max_removal_pct": 100, "max_removal_abs": 100},
            "enabled": True,
            "policy_version": "v1",
            "justwatch_policy_accepted": True,
        },
        headers=admin,
    )
    assert created.status_code == 201, created.text
    binding_id = created.json()["id"]
    enabled = client.patch(
        f"/api/bindings/{binding_id}",
        json={"enabled": True, "policy_version": "v1"},
        headers=admin,
    )
    assert enabled.status_code == 200, enabled.text
    assert enabled.json()["enabled"] is True
    _mock_mdblist([])

    blocked = client.post(
        f"/api/bindings/{binding_id}/runs", json={"dry_run": False}, headers=admin
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "DRY_RUN_REQUIRED"

    dry = client.post(f"/api/bindings/{binding_id}/runs", json={"dry_run": True}, headers=admin)
    assert dry.status_code == 202, dry.text
    dry_run = client.get(f"/api/runs/{dry.json()['run_id']}").json()
    assert dry_run["status"] == "SUCCEEDED", dry_run

    real = client.post(f"/api/bindings/{binding_id}/runs", json={"dry_run": False}, headers=admin)
    assert real.status_code == 202, real.text


@respx.mock
def test_episode_events_endpoint_lists_the_show_timeline(
    client, admin, seeded, app_settings
) -> None:
    _mock_packages()
    _sync_justwatch(app_settings)
    collection = _collection(client, "netflix-show-justwatch")
    media_id = _create_snapshot(collection["id"], [6001], "SHOW")
    _add_episode_event(collection["id"], media_id, "justwatch")

    response = client.get(f"/api/collections/{collection['id']}/episode-events?limit=10")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 1
    event = body["items"][0]
    assert event["media_id"] == media_id
    assert event["title"] == "Media 6001"
    assert event["event_type"] == "EPISODE_ADDED"
    assert event["season_number"] == 2
    assert event["episode_number"] == 5
    assert event["occurred_at"] is not None
    assert event["source_key"] == "justwatch"


@respx.mock
def test_episode_events_reject_movie_collections(client, admin, seeded, app_settings) -> None:
    _mock_packages()
    _sync_justwatch(app_settings)
    collection = _collection(client, "netflix-movie-justwatch")

    response = client.get(f"/api/collections/{collection['id']}/episode-events")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "COLLECTION_NOT_SHOW"


def test_snapshot_items_expose_availability_and_offer_types(client, admin, seeded) -> None:
    from app.db.models import Collection, CollectionSnapshot, SnapshotItem
    from app.db.session import get_session_factory
    from app.repositories import media as media_repo

    collection = _collection(client, "netflix-movie")
    session = get_session_factory()()
    try:
        row = session.get(Collection, uuid.UUID(collection["id"]))
        assert row is not None
        media = media_repo.resolve_media(
            session, media_type="MOVIE", tmdb_id=90210, imdb_id=None, title="Upcoming", year=2027
        )
        assert media is not None
        snapshot = CollectionSnapshot(
            collection_id=row.id,
            status="COMPLETE",
            quality="CLEAN",
            is_valid=True,
            items_count=1,
            resolved_count=1,
            unresolved_count=0,
            duplicate_count=0,
            error_count=0,
            checksum="availability",
        )
        session.add(snapshot)
        session.flush()
        session.add(
            SnapshotItem(
                snapshot_id=snapshot.id,
                media_id=media.id,
                position=0,
                source_payload={"id": "tm-upcoming", "_offer_types": ["FLATRATE"]},
                date_basis="UNKNOWN",
                resolution_status="RESOLVED",
                availability_status="UPCOMING",
            )
        )
        row.last_valid_snapshot_id = snapshot.id
        session.commit()
        snapshot_id = str(snapshot.id)
    finally:
        session.close()

    body = client.get(f"/api/snapshots/{snapshot_id}/items").json()
    item = body["items"][0]
    assert item["availability_status"] == "UPCOMING"
    assert item["source_offer_types"] == ["FLATRATE"]
