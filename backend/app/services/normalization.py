"""Normalization helpers: media identity, deduplication and snapshot checksum.

The identity key always carries the media type, so the same numeric TMDb id can
exist once as a movie and once as a show. Items without any external id are
kept (they are reported as unresolved) but never deduplicated against each
other, because there is no reliable key.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass

from app.connectors.base import NormalizedItem
from app.domain.enums import MediaType, ResolutionStatus


def media_key(
    media_type: MediaType | str,
    tmdb_id: int | None,
    imdb_id: str | None,
) -> str | None:
    """Stable identity key: ``<MEDIA_TYPE>:tmdb:<id>`` else ``<MEDIA_TYPE>:imdb:<id>``."""
    prefix = str(media_type)
    if tmdb_id is not None:
        return f"{prefix}:tmdb:{tmdb_id}"
    if imdb_id:
        return f"{prefix}:imdb:{imdb_id}"
    return None


def item_key(item: NormalizedItem) -> str | None:
    return media_key(item.media_type, item.tmdb_id, item.imdb_id)


def resolution_status(item: NormalizedItem) -> ResolutionStatus:
    return ResolutionStatus.RESOLVED if item_key(item) else ResolutionStatus.UNRESOLVED


@dataclass(frozen=True)
class DeduplicationResult:
    items: tuple[NormalizedItem, ...]
    duplicates: int


def deduplicate(items: Iterable[NormalizedItem]) -> DeduplicationResult:
    """Keep the first occurrence of each identity key, count the dropped ones."""
    seen: set[str] = set()
    unique: list[NormalizedItem] = []
    duplicates = 0
    for item in items:
        key = item_key(item)
        if key is None:
            unique.append(item)
            continue
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        unique.append(item)
    return DeduplicationResult(items=tuple(unique), duplicates=duplicates)


def checksum(items: Iterable[NormalizedItem]) -> str:
    """SHA-256 of the sorted normalized identity keys (order independent)."""
    keys = sorted(key for key in (item_key(item) for item in items) if key)
    return hashlib.sha256("\n".join(keys).encode("utf-8")).hexdigest()
