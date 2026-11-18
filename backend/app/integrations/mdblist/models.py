"""Typed payloads returned by the MDBList client.

Only the fields the sync engine consumes are modelled; the original payload is
kept in ``raw`` so a mapper can evolve without changing the client. Media types
are normalized to the project domain values (``MOVIE``/``SHOW``/``SEASON``/
``EPISODE``); MDBList sends them lowercase.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.domain.enums import TargetMediaType

_MEDIA_TYPE_BY_WIRE = {
    "movie": TargetMediaType.MOVIE.value,
    "show": TargetMediaType.SHOW.value,
    "season": TargetMediaType.SEASON.value,
    "episode": TargetMediaType.EPISODE.value,
}


def normalize_media_type(value: Any) -> str | None:
    """Map an MDBList ``mediatype`` value onto the domain enum."""
    if not isinstance(value, str):
        return None
    return _MEDIA_TYPE_BY_WIRE.get(value.strip().lower())


@dataclass(frozen=True)
class MdbListId:
    """External identifiers accepted by add/remove/reorder payloads."""

    tmdb: int | None = None
    imdb: str | None = None
    tvdb: int | None = None
    trakt: int | None = None

    def as_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if self.tmdb is not None:
            payload["tmdb"] = self.tmdb
        if self.imdb:
            payload["imdb"] = self.imdb
        if self.tvdb is not None:
            payload["tvdb"] = self.tvdb
        if self.trakt is not None:
            payload["trakt"] = self.trakt
        return payload


@dataclass(frozen=True)
class MdbListUser:
    """The authenticated MDBList account (used for target ownership checks)."""

    id: int | None
    user_name: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MdbListList:
    """A static MDBList list. ``id`` is the stable key; slug/URL are display only."""

    id: int
    name: str
    slug: str | None = None
    private: bool = False
    mediatype: str | None = None
    user_id: int | None = None
    user_name: str | None = None
    item_count: int | None = None
    likes: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MdbListListItem:
    """One element of a list, normalized to a media type plus external ids."""

    mediatype: str
    tmdb_id: int | None = None
    imdb_id: str | None = None
    tvdb_id: int | None = None
    trakt_id: int | None = None
    mdblist_id: str | None = None
    title: str | None = None
    release_year: int | None = None
    rank: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MdbListItemPage:
    """One cursor page of ``GET /lists/{id}/items``."""

    items: tuple[MdbListListItem, ...]
    next_cursor: str | None
    has_more: bool
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MdbListMutationResult:
    """Aggregated counters returned by add/remove.

    MDBList does not identify *which* element was ``not_found`` or ``existing``;
    the sync engine reconciles those batches with a full remote read.
    """

    added: dict[str, int] = field(default_factory=dict)
    removed: dict[str, int] = field(default_factory=dict)
    existing: dict[str, int] = field(default_factory=dict)
    not_found: dict[str, int] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def _total(bucket: dict[str, int]) -> int:
        return sum(int(value) for value in bucket.values())

    @property
    def added_total(self) -> int:
        return self._total(self.added)

    @property
    def removed_total(self) -> int:
        return self._total(self.removed)

    @property
    def existing_total(self) -> int:
        return self._total(self.existing)

    @property
    def not_found_total(self) -> int:
        return self._total(self.not_found)


@dataclass(frozen=True)
class MdbListReorderResult:
    """Result of ``POST /lists/{id}/items/reorder``."""

    updated: int = 0
    not_found: int = 0
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MdbListMembership:
    """List ids that contain a given media item."""

    list_ids: tuple[int, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict)
