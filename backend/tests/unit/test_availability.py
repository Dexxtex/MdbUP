"""Availability backfill from historical snapshots."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Availability, CollectionSnapshot, SnapshotItem
from app.db.session import get_session_factory
from app.repositories import collections as collections_repo
from app.repositories import media as media_repo
from app.services import availability


def test_backfill_observes_only_resolved_items_and_skips_derived(db, seeded) -> None:
    session: Session = get_session_factory()()
    try:
        collection = collections_repo.get_collection_by_slug(session, "netflix-movie")
        assert collection is not None
        media = media_repo.resolve_media(
            session, media_type="MOVIE", tmdb_id=8801, imdb_id=None, title="Backfill", year=2020
        )
        assert media is not None
        snapshot = CollectionSnapshot(
            collection_id=collection.id,
            status="COMPLETE",
            quality="CLEAN",
            is_valid=True,
            items_count=2,
            resolved_count=1,
            unresolved_count=0,
            duplicate_count=0,
            error_count=0,
            checksum="backfill",
        )
        session.add(snapshot)
        session.flush()
        session.add(
            SnapshotItem(
                snapshot_id=snapshot.id,
                media_id=media.id,
                position=0,
                date_basis="UNKNOWN",
                resolution_status="RESOLVED",
            )
        )
        session.add(
            SnapshotItem(
                snapshot_id=snapshot.id,
                media_id=None,
                position=1,
                date_basis="UNKNOWN",
                resolution_status="UNRESOLVED",
            )
        )
        # A derived collection is skipped even when it has historical snapshots.
        prime = collections_repo.get_collection_by_slug(session, "prime-video-movie")
        assert prime is not None
        prime_snapshot = CollectionSnapshot(
            collection_id=prime.id,
            status="COMPLETE",
            quality="CLEAN",
            is_valid=True,
            items_count=1,
            resolved_count=1,
            unresolved_count=0,
            duplicate_count=0,
            error_count=0,
            checksum="derived-backfill",
        )
        session.add(prime_snapshot)
        session.flush()
        session.add(
            SnapshotItem(
                snapshot_id=prime_snapshot.id,
                media_id=media.id,
                position=0,
                date_basis="UNKNOWN",
                resolution_status="RESOLVED",
            )
        )
        prime.kind = "RECENTLY_ADDED"
        session.commit()

        outcome = availability.backfill_from_snapshots(session)
        assert outcome.snapshots >= 1
        assert outcome.items == 1
        assert outcome.created_or_updated == 1
        assert session.scalar(select(Availability).where(Availability.media_id == media.id))
    finally:
        session.close()
