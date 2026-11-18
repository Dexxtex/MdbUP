"""Canonical media identities.

Identity is ``(media_type, tmdb_id)`` with ``(media_type, imdb_id)`` as fallback.
The title is never a key, and a row is never created without an external id.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Media
from app.domain.enums import MediaType, ResolutionStatus


def find_by_tmdb(db: Session, media_type: MediaType | str, tmdb_id: int) -> Media | None:
    return db.scalar(
        select(Media).where(
            Media.media_type == str(media_type),
            Media.tmdb_id == tmdb_id,
        )
    )


def find_by_imdb(db: Session, media_type: MediaType | str, imdb_id: str) -> Media | None:
    return db.scalar(
        select(Media).where(
            Media.media_type == str(media_type),
            Media.imdb_id == imdb_id,
        )
    )


def resolve_media(
    db: Session,
    *,
    media_type: MediaType | str,
    tmdb_id: int | None,
    imdb_id: str | None,
    title: str,
    year: int | None,
    metadata: dict[str, Any] | None = None,
) -> Media | None:
    """Find or create the media row; ``None`` when no external id is available."""
    if tmdb_id is None and not imdb_id:
        return None
    media: Media | None = None
    if tmdb_id is not None:
        media = find_by_tmdb(db, media_type, tmdb_id)
    if media is None and imdb_id:
        media = find_by_imdb(db, media_type, imdb_id)
    if media is None:
        media = Media(
            media_type=str(media_type),
            tmdb_id=tmdb_id,
            imdb_id=imdb_id,
            title=title[:512] or "Senza titolo",
            release_year=year,
            metadata_json=metadata or {},
            resolution_status=ResolutionStatus.RESOLVED.value,
        )
        db.add(media)
        db.flush()
        return media
    if (
        tmdb_id is not None
        and media.tmdb_id is None
        and find_by_tmdb(db, media_type, tmdb_id) is None
    ):
        media.tmdb_id = tmdb_id
    if imdb_id and media.imdb_id is None and find_by_imdb(db, media_type, imdb_id) is None:
        media.imdb_id = imdb_id
    if not media.title and title:
        media.title = title[:512]
    if media.release_year is None and year is not None:
        media.release_year = year
    db.flush()
    return media


def count_media(db: Session) -> int:
    return int(db.scalar(select(func.count()).select_from(Media)) or 0)


def find_by_id(db: Session, media_id: uuid.UUID) -> Media | None:
    return db.get(Media, media_id)
