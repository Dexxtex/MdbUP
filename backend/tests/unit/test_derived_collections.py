"""Derived collections: recently detected baseline and shared snapshot reuse."""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.db.models import CollectionSnapshot, SnapshotItem
from app.db.session import get_session_factory
from app.domain.enums import CollectionKind, CollectionOrigin, DateBasis
from app.repositories import availability as availability_repo
from app.repositories import collections as collections_repo
from app.repositories import media as media_repo
from app.services import acquisition


class _FakeConnector:
    key = "tmdb"

    def fetch_collection_page(self, *_args, **_kwargs):
        raise AssertionError("Il connettore non deve essere chiamato")


@pytest.fixture()
def session(db) -> Session:
    factory = get_session_factory()
    db_session = factory()
    try:
        yield db_session
    finally:
        db_session.close()


def _media(session: Session, tmdb_id: int, media_type: str = "MOVIE"):
    media = media_repo.resolve_media(
        session,
        media_type=media_type,
        tmdb_id=tmdb_id,
        imdb_id=None,
        title=f"Media {tmdb_id}",
        year=2020,
    )
    assert media is not None
    return media


def _snapshot(session: Session, collection, media_list, *, started_at, payloads=None):
    snapshot = CollectionSnapshot(
        collection_id=collection.id,
        status="COMPLETE",
        quality="CLEAN",
        is_valid=True,
        started_at=started_at,
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
                source_payload=(payloads or {}).get(media.id, {}),
                date_basis="UNKNOWN",
                resolution_status="RESOLVED",
            )
        )
    collection.last_valid_snapshot_id = snapshot.id
    session.commit()
    return snapshot


def _derived(session: Session, source, *, slug: str, window_days: int = 10):
    return collections_repo.upsert_collection(
        session,
        slug=slug,
        source_id=source.source_id,
        provider_id=source.provider_id,
        country_code=source.country_code,
        media_type=source.media_type,
        kind=CollectionKind.RECENTLY_ADDED.value,
        origin=CollectionOrigin.CUSTOM.value,
        date_basis=DateBasis.APP_FIRST_SEEN.value,
        name="Appena rilevati",
        description="Test",
        source_collection_key=f"custom:{slug}",
        offer_types=["FLATRATE"],
        filters={
            "derivation": "RECENTLY_DETECTED",
            "source_collection_id": str(source.id),
            "window_days": window_days,
        },
        quality_flags={"derivation": "RECENTLY_DETECTED"},
        sort_mode="POPULARITY",
        is_active=True,
    )


def test_recently_detected_skips_baseline_and_old_items(
    session: Session, seeded, app_settings
) -> None:
    source = collections_repo.get_collection_by_slug(session, "netflix-movie")
    assert source is not None
    now = utcnow()
    baseline = now - timedelta(days=20)
    media_baseline_a = _media(session, 1)
    media_baseline_b = _media(session, 2)
    media_new = _media(session, 3)
    media_old = _media(session, 4)
    media_outside_window = _media(session, 5)
    _snapshot(session, source, [media_baseline_a, media_baseline_b], started_at=baseline)
    for media, first_seen in (
        (media_baseline_a, baseline),
        (media_baseline_b, baseline),
        (media_new, baseline + timedelta(days=15)),
        (media_old, baseline - timedelta(days=1)),
        (media_outside_window, baseline + timedelta(days=1)),
    ):
        availability_repo.upsert_observed(
            session,
            media_id=media.id,
            provider_id=source.provider_id,
            country_code=source.country_code,
            offer_type="FLATRATE",
            source_id=source.source_id,
            first_seen_at=first_seen,
            seen_at=now,
        )
    session.commit()
    derived = _derived(session, source, slug="netflix-movie-recenti-test", window_days=10)

    outcome = acquisition.acquire_collection(
        session, derived.id, _FakeConnector(), actor_type="SYSTEM"
    )
    assert outcome.items_count == 1
    assert outcome.is_valid is True
    items = session.query(SnapshotItem).filter_by(snapshot_id=outcome.snapshot_id).all()
    assert [item.media_id for item in items] == [media_new.id]


def test_recently_detected_without_source_snapshot_is_empty_baseline(
    session: Session, seeded, app_settings
) -> None:
    source = collections_repo.get_collection_by_slug(session, "netflix-movie")
    assert source is not None
    derived = _derived(session, source, slug="netflix-movie-recenti-empty", window_days=14)

    outcome = acquisition.acquire_collection(
        session, derived.id, _FakeConnector(), actor_type="SYSTEM"
    )
    assert outcome.items_count == 0
    assert outcome.is_valid is False
    assert outcome.invalid_reason == "baseline_empty"


def test_shared_snapshot_reuses_genre_filtered_items(
    session: Session, seeded, app_settings
) -> None:
    source = collections_repo.get_collection_by_slug(session, "netflix-movie")
    assert source is not None
    action = _media(session, 10)
    adventure = _media(session, 11)
    _snapshot(
        session,
        source,
        [action, adventure],
        started_at=utcnow(),
        payloads={action.id: {"genre_ids": [28]}, adventure.id: {"genre_ids": [12]}},
    )
    target = collections_repo.upsert_collection(
        session,
        slug="netflix-movie-azione-shared-test",
        source_id=source.source_id,
        provider_id=source.provider_id,
        country_code=source.country_code,
        media_type=source.media_type,
        kind=CollectionKind.CATALOG.value,
        origin=CollectionOrigin.AGGREGATOR.value,
        date_basis=DateBasis.UNKNOWN.value,
        name="Azione condivisa",
        description="Test",
        source_collection_key="custom:shared-test",
        offer_types=["FLATRATE"],
        filters={
            "shared_snapshot_collection_id": str(source.id),
            "with_genres": "28",
        },
        quality_flags={},
        sort_mode="POPULARITY",
        is_active=True,
    )
    outcome = acquisition.acquire_collection(
        session, target.id, _FakeConnector(), actor_type="SYSTEM"
    )
    assert outcome.items_count == 1
    items = session.query(SnapshotItem).filter_by(snapshot_id=outcome.snapshot_id).all()
    assert [item.media_id for item in items] == [action.id]
