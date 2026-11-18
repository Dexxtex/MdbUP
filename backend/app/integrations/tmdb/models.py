"""Typed payloads returned by the TMDb client.

Only fields the acquisition pipeline actually consumes are modelled; the full
payload is kept in ``raw`` so a later mapper can evolve without a client change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.domain.enums import MediaType


@dataclass(frozen=True)
class TMDbProvider:
    """A watch provider as listed by ``/watch/providers/{movie|tv}``."""

    provider_id: int
    name: str
    country_code: str
    display_priority: int | None = None
    logo_path: str | None = None


@dataclass(frozen=True)
class TMDbDiscoverItem:
    """One result of ``/discover/{movie|tv}``."""

    tmdb_id: int
    media_type: MediaType
    title: str
    original_title: str | None = None
    release_year: int | None = None
    popularity: float | None = None
    overview: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TMDbDiscoverPage:
    """One page of a discover query."""

    page: int
    total_pages: int
    total_results: int
    items: tuple[TMDbDiscoverItem, ...]
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TMDbExternalIds:
    """External identifiers for a movie or a show."""

    tmdb_id: int
    imdb_id: str | None = None


@dataclass(frozen=True)
class TMDbSeason:
    """A season summary embedded in ``/tv/{id}``."""

    season_number: int
    name: str | None = None
    episode_count: int | None = None
    air_date: str | None = None


@dataclass(frozen=True)
class TMDbTvDetails:
    """Show-level metadata used to detect new seasons/episodes.

    Seasons and episodes are *events* associated with the parent show; they are
    never inserted as separate ``media`` rows and never sent to MDBList.
    """

    tmdb_id: int
    name: str
    number_of_seasons: int | None = None
    number_of_episodes: int | None = None
    seasons: tuple[TMDbSeason, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict)
