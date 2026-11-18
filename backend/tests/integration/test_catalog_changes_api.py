"""Catalog change feed endpoint: auth, response shape and filters."""

from __future__ import annotations

from datetime import timedelta

from app.core.time import utcnow
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


def _snapshot(session, collection, media_list, *, started_at, finished_at):
    snapshot = CollectionSnapshot(
        collection_id=collection.id,
        status="COMPLETE",
        quality="CLEAN",
        is_valid=True,
        started_at=started_at,
        finished_at=finished_at,
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
                source_payload={},
                date_basis="UNKNOWN",
                resolution_status="RESOLVED",
            )
        )
    collection.last_valid_snapshot_id = snapshot.id
    session.commit()
    return snapshot


def _seed_snapshots() -> None:
    session = get_session_factory()()
    try:
        collection = collections_repo.get_collection_by_slug(session, "netflix-movie")
        assert collection is not None
        now = utcnow()
        _snapshot(
            session,
            collection,
            [_media(session, 1)],
            started_at=now - timedelta(days=2),
            finished_at=now - timedelta(days=2),
        )
        _snapshot(
            session,
            collection,
            [_media(session, 1), _media(session, 2)],
            started_at=now - timedelta(hours=1),
            finished_at=now,
        )
    finally:
        session.close()


def test_catalog_changes_requires_authentication(client, seeded) -> None:
    response = client.get("/api/catalog-changes")
    assert response.status_code == 401


def test_catalog_changes_feed_and_filters(client, admin, seeded) -> None:
    _seed_snapshots()
    response = client.get("/api/catalog-changes?window=24h")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["window"] == "24h"
    assert body["total"] == 1
    assert body["page"] == 1
    assert body["page_size"] == 50
    assert body["generated_at"]
    item = body["items"][0]
    assert item["direction"] == "ADDED"
    assert item["title"] == "Media 2"
    assert item["media_type"] == "MOVIE"
    assert item["provider_slug"] == "netflix"
    assert item["source_key"] == "tmdb"
    assert item["source_label"] == "TMDb"
    assert item["detected_at_rome"].endswith("+01:00") or item["detected_at_rome"].endswith(
        "+02:00"
    )
    assert body["counters"]["added_window"] == 1
    assert body["counters"]["removed_window"] == 0

    filtered = client.get("/api/catalog-changes?window=24h&direction=REMOVED").json()
    assert filtered["total"] == 0
    by_search = client.get("/api/catalog-changes?window=24h&search=Media%202").json()
    assert by_search["total"] == 1
    by_source = client.get("/api/catalog-changes?window=24h&source_key=tmdb").json()
    assert by_source["total"] == 1

    too_large = client.get("/api/catalog-changes?page_size=300")
    assert too_large.status_code == 422
