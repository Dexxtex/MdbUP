"""Availability history use cases (backfill and derived collections)."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Collection, CollectionSnapshot, SnapshotItem
from app.domain.enums import CollectionKind, OfferType
from app.repositories import availability as availability_repo


@dataclass(frozen=True)
class BackfillOutcome:
    snapshots: int
    items: int
    created_or_updated: int


def backfill_from_snapshots(db: Session) -> BackfillOutcome:
    """Populate Availability from historical snapshots, preserving first seen.

    Existing installations acquired snapshots before Availability was written.
    The snapshot start time is the best available proxy for the first
    observation; derived collections use it as the baseline.
    """
    snapshots = list(
        db.scalars(
            select(CollectionSnapshot)
            .where(CollectionSnapshot.items_count > 0)
            .order_by(CollectionSnapshot.started_at)
        ).all()
    )
    items = 0
    touched = 0
    for snapshot in snapshots:
        collection = db.get(Collection, snapshot.collection_id)
        if collection is None or collection.kind == CollectionKind.RECENTLY_ADDED.value:
            continue
        offer_type = str((collection.offer_types or [OfferType.FLATRATE.value])[0])
        snapshot_items = db.scalars(
            select(SnapshotItem).where(SnapshotItem.snapshot_id == snapshot.id)
        ).all()
        for item in snapshot_items:
            if item.media_id is None:
                continue
            items += 1
            availability_repo.upsert_observed(
                db,
                media_id=item.media_id,
                provider_id=collection.provider_id,
                country_code=collection.country_code,
                offer_type=offer_type,
                source_id=collection.source_id,
                first_seen_at=snapshot.started_at,
                seen_at=snapshot.finished_at or snapshot.started_at,
                metadata={
                    "backfill_snapshot_id": str(snapshot.id),
                    "collection_id": str(collection.id),
                },
            )
            touched += 1
    db.commit()
    return BackfillOutcome(snapshots=len(snapshots), items=items, created_or_updated=touched)
