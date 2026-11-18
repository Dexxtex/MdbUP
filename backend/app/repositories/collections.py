"""Catalog collection persistence."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Collection


def get_collection(db: Session, collection_id: uuid.UUID) -> Collection | None:
    return db.get(Collection, collection_id)


def get_collection_by_slug(db: Session, slug: str) -> Collection | None:
    return db.scalar(select(Collection).where(Collection.slug == slug))


def list_collections(
    db: Session,
    *,
    provider_id: uuid.UUID | None = None,
    media_type: str | None = None,
    origin: str | None = None,
    kind: str | None = None,
    country_code: str | None = None,
    is_active: bool | None = None,
) -> list[Collection]:
    stmt = select(Collection)
    if provider_id is not None:
        stmt = stmt.where(Collection.provider_id == provider_id)
    if media_type is not None:
        stmt = stmt.where(Collection.media_type == media_type)
    if origin is not None:
        stmt = stmt.where(Collection.origin == origin)
    if kind is not None:
        stmt = stmt.where(Collection.kind == kind)
    if country_code is not None:
        stmt = stmt.where(Collection.country_code == country_code)
    if is_active is not None:
        stmt = stmt.where(Collection.is_active.is_(is_active))
    return list(db.scalars(stmt.order_by(Collection.name)).all())


def count_by_provider(
    db: Session, *, country_code: str | None = None
) -> dict[uuid.UUID, dict[str, int]]:
    """Collection count per provider and media type."""
    stmt = select(Collection.provider_id, Collection.media_type, func.count()).group_by(
        Collection.provider_id, Collection.media_type
    )
    if country_code is not None:
        stmt = stmt.where(Collection.country_code == country_code)
    counts: dict[uuid.UUID, dict[str, int]] = {}
    for provider_id, media_type, total in db.execute(stmt).all():
        counts.setdefault(provider_id, {})[media_type] = int(total)
    return counts


def upsert_collection(db: Session, *, slug: str, **fields: Any) -> Collection:
    """Insert or update a collection identified by its stable slug."""
    collection = get_collection_by_slug(db, slug)
    if collection is None:
        collection = Collection(slug=slug, **fields)
        db.add(collection)
    else:
        for key, value in fields.items():
            setattr(collection, key, value)
    db.flush()
    return collection


def set_last_valid_snapshot(
    db: Session, collection: Collection, snapshot_id: uuid.UUID | None
) -> None:
    collection.last_valid_snapshot_id = snapshot_id
    db.flush()
