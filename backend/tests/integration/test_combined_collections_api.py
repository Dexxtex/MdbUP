"""Combined collection API: create, update and acquire without external calls."""

from __future__ import annotations

from app.db.models import CollectionSnapshot, SnapshotItem
from app.db.session import get_session_factory
from app.repositories import collections as collections_repo
from app.repositories import media as media_repo


def _media(session, tmdb_id: int):
    media = media_repo.resolve_media(
        session,
        media_type="MOVIE",
        tmdb_id=tmdb_id,
        imdb_id=None,
        title=f"Media {tmdb_id}",
        year=2020,
    )
    assert media is not None
    return media


def _snapshot(session, collection, media_list) -> None:
    snapshot = CollectionSnapshot(
        collection_id=collection.id,
        status="COMPLETE",
        quality="CLEAN",
        is_valid=True,
        items_count=len(media_list),
        resolved_count=len(media_list),
        unresolved_count=0,
        duplicate_count=0,
        error_count=0,
        checksum="checksum",
    )
    session.add(snapshot)
    session.flush()
    for position, media in enumerate(media_list):
        session.add(
            SnapshotItem(
                snapshot_id=snapshot.id,
                media_id=media.id,
                position=position,
                source_payload={"id": media.tmdb_id},
                date_basis="UNKNOWN",
                resolution_status="RESOLVED",
            )
        )
    collection.last_valid_snapshot_id = snapshot.id


def _seed_source_snapshots() -> None:
    session = get_session_factory()()
    try:
        netflix = collections_repo.get_collection_by_slug(session, "netflix-movie")
        prime = collections_repo.get_collection_by_slug(session, "prime-video-movie")
        assert netflix is not None and prime is not None
        _snapshot(session, netflix, [_media(session, 1), _media(session, 2)])
        _snapshot(session, prime, [_media(session, 2), _media(session, 3)])
        session.commit()
    finally:
        session.close()


def _collection_id(client, slug: str) -> str:
    items = client.get("/api/collections").json()["items"]
    return next(item["id"] for item in items if item["slug"] == slug)


def test_combined_collection_create_update_and_acquire_without_external_calls(
    client, admin, seeded, monkeypatch
) -> None:
    _seed_source_snapshots()
    sources = {item["key"]: item for item in client.get("/api/sources").json()["items"]}
    assert sources["combined"]["name"] == "Combinata locale"
    assert sources["combined"]["status"] == "OK"
    assert sources["combined"]["connector_available"] is False
    assert sources["combined"]["capabilities"]["catalog"] is True

    def _external_call_forbidden(*_args, **_kwargs):
        raise AssertionError("Una collezione combinata non deve creare connettori esterni")

    monkeypatch.setattr("app.connectors.registry.create_connector", _external_call_forbidden)

    netflix_id = _collection_id(client, "netflix-movie")
    prime_id = _collection_id(client, "prime-video-movie")
    created = client.post(
        "/api/collections",
        json={
            "media_type": "MOVIE",
            "name": "Combinata API test",
            "slug": "combinata-api-test",
            "kind": "CUSTOM_FILTER",
            "source_key": "combined",
            "combine_mode": "UNION",
            "source_collection_ids": [netflix_id, prime_id],
        },
        headers=admin,
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["source_key"] == "combined"
    assert body["source_label"] == "Combinata locale (JustWatch + TMDb)"
    assert body["filters"]["derivation"] == "COMBINED_LOCAL"
    assert body["filters"]["combine_mode"] == "UNION"
    assert body["date_basis"] == "UNKNOWN"

    acquired = client.post(f"/api/collections/{body['id']}/acquire", headers=admin)
    assert acquired.status_code == 202, acquired.text
    job = acquired.json()
    assert job["status"] == "SUCCEEDED"
    assert job["snapshot_id"] is not None

    items = client.get(f"/api/snapshots/{job['snapshot_id']}/items").json()
    assert items["total"] == 3

    updated = client.patch(
        f"/api/collections/{body['id']}",
        json={"combine_mode": "INTERSECTION", "name": "Combinata API test 2"},
        headers=admin,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["filters"]["combine_mode"] == "INTERSECTION"
    assert updated.json()["name"] == "Combinata API test 2"

    acquired_again = client.post(f"/api/collections/{body['id']}/acquire", headers=admin)
    assert acquired_again.status_code == 202, acquired_again.text
    second_job = acquired_again.json()
    assert second_job["status"] == "SUCCEEDED"
    second_items = client.get(f"/api/snapshots/{second_job['snapshot_id']}/items").json()
    assert second_items["total"] == 1
