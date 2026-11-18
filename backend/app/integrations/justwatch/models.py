"""Typed payloads returned by the JustWatch GraphQL client.

Only the fields the acquisition pipeline consumes are modelled; the full node is
kept in ``raw`` so a mapper can evolve without a client change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.domain.enums import MediaType, OfferType


@dataclass(frozen=True)
class JustWatchPackage:
    """A streaming package (provider) for one country."""

    short_name: str
    name: str
    package_id: str | None = None
    technical_name: str | None = None
    monetization_types: tuple[str, ...] = ()


@dataclass(frozen=True)
class JustWatchOffer:
    """One offer attached to a title."""

    monetization_type: str
    presentation_type: str | None = None
    package_short_name: str | None = None
    package_name: str | None = None
    standard_web_url: str | None = None

    @property
    def offer_type(self) -> OfferType | None:
        """Map the JustWatch monetization type onto the app enum."""
        try:
            return OfferType(self.monetization_type)
        except ValueError:
            return None


@dataclass(frozen=True)
class JustWatchTitle:
    """A movie or show node."""

    node_id: str
    media_type: MediaType
    title: str
    year: int | None = None
    tmdb_id: int | None = None
    imdb_id: str | None = None
    full_path: str | None = None
    runtime_minutes: int | None = None
    offers: tuple[JustWatchOffer, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def offer_types(self) -> frozenset[str]:
        mapped = {offer.offer_type.value for offer in self.offers if offer.offer_type}
        return frozenset(mapped)

    @property
    def package_short_names(self) -> frozenset[str]:
        return frozenset(
            offer.package_short_name for offer in self.offers if offer.package_short_name
        )


@dataclass(frozen=True)
class JustWatchChartEntry:
    """A streaming-chart row: the title plus its ranking metadata.

    ``rank`` is not a field of the node: it lives on the edge, in
    ``streamingChartInfo``.
    """

    title: JustWatchTitle
    rank: int | None = None
    trend: str | None = None
    trend_difference: int | None = None
    days_in_top10: int | None = None
    top_rank: int | None = None


@dataclass(frozen=True)
class JustWatchPage:
    """One page of results with the cursor needed for the next call."""

    titles: tuple[JustWatchTitle, ...] = ()
    charts: tuple[JustWatchChartEntry, ...] = ()
    next_cursor: str | None = None
    total_items: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class JustWatchSeason:
    """A season node of a show."""

    node_id: str
    title: str
    total_episode_count: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class JustWatchEpisode:
    """An episode node, with its own offers."""

    node_id: str
    title: str
    season_number: int | None = None
    episode_number: int | None = None
    offers: tuple[JustWatchOffer, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict)
