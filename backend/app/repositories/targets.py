"""MDBList target persistence. ``remote_list_id`` is the stable key."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.db.models import MdblistTarget


def get_target(db: Session, target_id: uuid.UUID) -> MdblistTarget | None:
    return db.get(MdblistTarget, target_id)


def get_by_remote_list_id(db: Session, remote_list_id: int) -> MdblistTarget | None:
    return db.scalar(select(MdblistTarget).where(MdblistTarget.remote_list_id == remote_list_id))


def list_targets(
    db: Session,
    *,
    mediatype: str | None = None,
) -> list[MdblistTarget]:
    stmt = select(MdblistTarget)
    if mediatype is not None:
        stmt = stmt.where(MdblistTarget.mediatype == mediatype)
    return list(db.scalars(stmt.order_by(MdblistTarget.name)).all())


def create_target(
    db: Session,
    *,
    remote_list_id: int,
    name: str,
    mediatype: str,
    remote_slug: str | None = None,
    remote_url: str | None = None,
    is_private: bool = False,
    item_count: int | None = None,
    capabilities: dict[str, Any] | None = None,
) -> MdblistTarget:
    target = MdblistTarget(
        remote_list_id=remote_list_id,
        name=name[:300],
        mediatype=mediatype,
        remote_slug=(remote_slug or str(remote_list_id))[:200],
        remote_url=remote_url,
        is_private=is_private,
        item_count=item_count,
        capabilities=capabilities or {},
    )
    db.add(target)
    db.flush()
    return target


def upsert_target(
    db: Session,
    *,
    remote_list_id: int,
    name: str,
    mediatype: str,
    remote_slug: str | None = None,
    remote_url: str | None = None,
    is_private: bool = False,
    item_count: int | None = None,
) -> MdblistTarget:
    """Insert or update a target by its stable numeric list id."""
    target = get_by_remote_list_id(db, remote_list_id)
    if target is None:
        return create_target(
            db,
            remote_list_id=remote_list_id,
            name=name,
            mediatype=mediatype,
            remote_slug=remote_slug,
            remote_url=remote_url,
            is_private=is_private,
            item_count=item_count,
        )
    target.name = name[:300]
    target.mediatype = mediatype
    target.remote_slug = (remote_slug or str(remote_list_id))[:200]
    target.remote_url = remote_url
    target.is_private = is_private
    if item_count is not None:
        target.item_count = item_count
    db.flush()
    return target


def update_remote_metadata(
    db: Session,
    target: MdblistTarget,
    *,
    name: str | None = None,
    remote_slug: str | None = None,
    remote_url: str | None = None,
    is_private: bool | None = None,
    item_count: int | None = None,
    capabilities: dict[str, Any] | None = None,
    verified: bool = False,
) -> MdblistTarget:
    """Refresh display metadata; the numeric ``remote_list_id`` never changes."""
    if name:
        target.name = name[:300]
    if remote_slug:
        target.remote_slug = remote_slug[:200]
    if remote_url is not None:
        target.remote_url = remote_url
    if is_private is not None:
        target.is_private = is_private
    if item_count is not None:
        target.item_count = item_count
    if capabilities is not None:
        target.capabilities = capabilities
    if verified:
        target.last_verified_at = utcnow()
    db.flush()
    return target


def mark_remote_read(db: Session, target: MdblistTarget, *, item_count: int | None = None) -> None:
    target.last_remote_read_at = utcnow()
    if item_count is not None:
        target.item_count = item_count
    db.flush()


def set_verified_at(db: Session, target: MdblistTarget, moment: datetime | None = None) -> None:
    target.last_verified_at = moment or utcnow()
    db.flush()
