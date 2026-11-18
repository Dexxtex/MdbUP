"""JustWatch connector backed by the public GraphQL endpoint.

What this source is:

- ``AGGREGATOR``, never ``OFFICIAL``. The endpoint publishes no provider-declared
  add date, so ``date_basis`` is ``UNKNOWN`` and ``source_date_created`` is
  ``None``. Nothing here can be promoted to ``PROVIDER_OFFICIAL``.
- Complete on pagination. The endpoint stops at item #1999 per query, so the
  catalog is walked by partitioning ``releaseYear`` ranges: a range that holds
  more than 1999 titles is split in half until every leaf fits. The cursor
  carries the pending ranges, so a page fetch is stateless and resumable.
- Complete on hierarchy: seasons and per-episode offers are exposed through
  :meth:`JustWatchConnector.list_seasons` / :meth:`list_episodes`.

Hard limits of the endpoint (measured, not assumed): 100 items per page, no
reachable item past #1999, no rate-limit headers and no ``429`` observed. The
client still throttles locally (``JUSTWATCH_MIN_INTERVAL_MS``) because the only
failure mode is a silent IP block.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from app.connectors.base import (
    ConnectorCapabilities,
    HealthStatus,
    NormalizedItem,
    NotSupportedError,
    Page,
    RawItem,
    SourceCollection,
    SourceProvider,
)
from app.domain.enums import (
    CollectionKind,
    CollectionOrigin,
    DateBasis,
    MediaType,
)
from app.integrations.justwatch.client import (
    MAX_PAGE_SIZE,
    MAX_REACHABLE_ITEMS,
    JustWatchClient,
    JustWatchPage,
)
from app.integrations.justwatch.models import (
    JustWatchChartEntry,
    JustWatchEpisode,
    JustWatchSeason,
    JustWatchTitle,
)

JUSTWATCH_SOURCE_KEY = "justwatch"

DEFAULT_YEAR_FROM = 1900
DEFAULT_YEAR_TO = datetime.now(UTC).year + 1

CAPABILITIES = ConnectorCapabilities(
    catalog=True,
    recently_added=True,
    upcoming=True,
    charts=True,
    ordering=True,
    added_dates=False,
    seasons_episodes=True,
    full_pagination=True,
    data_export=False,
    requires_credentials=False,
    requires_contract=False,
    max_page_size=MAX_PAGE_SIZE,
    notes=(
        "AGGREGATOR: nessuna data di aggiunta, quindi date_basis=UNKNOWN. "
        "Paginazione completa tramite partizioni releaseYear (tetto 1999 per query). "
        "Stagioni ed episodi con offerte per episodio. Throttle locale obbligatorio: "
        "il servizio non espone rate limit e non avvisa prima di un blocco."
    ),
)

# Every collection is bound to exactly one package: the app requires a
# provider on each collection, and the endpoint filters by package anyway.
PROVIDER_COLLECTIONS: tuple[tuple[CollectionKind, str], ...] = (
    (CollectionKind.CATALOG, ""),
    (CollectionKind.CHART, "chart"),
    (CollectionKind.RECENTLY_ADDED, "recently-added"),
    (CollectionKind.UPCOMING, "upcoming"),
)

_PAGE_TYPES = {
    CollectionKind.RECENTLY_ADDED: "NEW",
    CollectionKind.UPCOMING: "UPCOMING",
}


@dataclass(frozen=True)
class YearRanges:
    """Cursor for partitioned pagination: current range first, then pending ones.

    Serialized as ``"1900-2030|1966-2030:300"``: the ranges still to walk and the
    offset inside the first one. It makes a page fetch stateless, so a run can
    resume from the cursor alone.
    """

    ranges: tuple[tuple[int, int], ...]
    offset: int = 0

    @classmethod
    def start(cls, year_from: int, year_to: int) -> YearRanges:
        return cls(((int(year_from), int(year_to)),), 0)

    @classmethod
    def parse(cls, raw: str | None, year_from: int, year_to: int) -> YearRanges:
        if not raw:
            return cls.start(year_from, year_to)
        try:
            ranges_part, offset_part = raw.rsplit(":", 1)
            ranges: list[tuple[int, int]] = []
            for chunk in ranges_part.split("|"):
                lo_text, hi_text = chunk.split("-", 1)
                lo, hi = int(lo_text), int(hi_text)
                if lo > hi:
                    raise ValueError("range invertito")
                ranges.append((lo, hi))
            if not ranges:
                raise ValueError("nessun range")
            return cls(tuple(ranges), max(0, int(offset_part)))
        except (AttributeError, TypeError, ValueError):
            return cls.start(year_from, year_to)

    def serialize(self) -> str:
        body = "|".join(f"{lo}-{hi}" for lo, hi in self.ranges)
        return f"{body}:{self.offset}"

    def advance(self) -> YearRanges | None:
        """Move to the next pending range, or ``None`` when the walk is done."""
        if len(self.ranges) <= 1:
            return None
        return YearRanges(self.ranges[1:], 0)

    def split(self, mid: int) -> YearRanges:
        """Split the current range in two, keeping the pending ones after them."""
        lo, hi = self.ranges[0]
        return YearRanges(((lo, mid), (mid + 1, hi)) + self.ranges[1:], 0)

    def with_offset(self, offset: int) -> YearRanges:
        return YearRanges(self.ranges, max(0, offset))


class JustWatchConnector:
    """``SourceConnector`` implementation over :class:`JustWatchClient`."""

    key = JUSTWATCH_SOURCE_KEY
    capabilities = CAPABILITIES

    def __init__(
        self,
        client: JustWatchClient,
        *,
        language: str = "it",
        year_from: int = DEFAULT_YEAR_FROM,
        year_to: int = DEFAULT_YEAR_TO,
    ) -> None:
        self._client = client
        self._language = language
        self._year_from = year_from
        self._year_to = year_to

    # -- discovery ---------------------------------------------------------
    def healthcheck(self) -> HealthStatus:
        return self._client.healthcheck()

    def list_providers(self, country_code: str = "IT") -> Sequence[SourceProvider]:
        return [
            SourceProvider(
                external_id=package.short_name,
                name=package.name,
                country_code=country_code,
            )
            for package in self._client.list_packages(country_code)
        ]

    def provider_monetization_types(self, country_code: str = "IT") -> dict[str, tuple[str, ...]]:
        """Offer types each package reports, keyed by package short name."""
        return {
            package.short_name: package.monetization_types
            for package in self._client.list_packages(country_code)
        }

    def list_genres(self) -> list[dict[str, str]]:
        """Genres with their localized slug, for building filtered collections."""
        rows: list[dict[str, str]] = []
        for genre in self._client.list_genres(self._language):
            short_name = genre.get("shortName")
            if not short_name:
                continue
            rows.append(
                {
                    "short_name": str(short_name),
                    "slug": str(genre.get("slug") or genre.get("technicalName") or short_name),
                }
            )
        return rows

    def list_collections(self, country_code: str = "IT") -> Sequence[SourceCollection]:
        collections: list[SourceCollection] = []
        for provider in self.list_providers(country_code):
            for kind, slug in PROVIDER_COLLECTIONS:
                for media_type in (MediaType.MOVIE, MediaType.SHOW):
                    collections.append(
                        self._collection(provider, kind, slug, media_type, country_code)
                    )
        return collections

    def _collection(
        self,
        provider: SourceProvider,
        kind: CollectionKind,
        slug: str,
        media_type: MediaType,
        country_code: str,
    ) -> SourceCollection:
        label = "Film" if media_type is MediaType.MOVIE else "Serie"
        prefix = f"{slug}:" if slug else ""
        suffix = {
            CollectionKind.CATALOG: "",
            CollectionKind.CHART: " (classifica)",
            CollectionKind.RECENTLY_ADDED: " (novità)",
            CollectionKind.UPCOMING: " (in arrivo)",
        }[kind]
        return SourceCollection(
            key=f"{prefix}{provider.external_id}:{media_type.value}",
            name=f"{provider.name} — {label}{suffix}",
            provider_external_id=provider.external_id,
            media_type=media_type,
            kind=kind,
            origin=CollectionOrigin.AGGREGATOR,
            date_basis=DateBasis.UNKNOWN,
            source_url=None,
            metadata={
                "media_type": media_type.value,
                "watch_region": country_code,
                "packages": [provider.external_id],
                "year_from": self._year_from,
                "year_to": self._year_to,
            },
        )

    # -- acquisition -------------------------------------------------------
    def fetch_collection_page(
        self,
        collection: SourceCollection,
        cursor: str | None,
        page_size: int,
    ) -> Page:
        country = str(collection.metadata.get("watch_region") or "IT")
        kind = collection.kind
        filters = collection.metadata.get("filters") or {}
        if not isinstance(filters, dict):
            filters = {}
        packages = _packages(collection, filters)
        genres = _string_list(filters.get("genres"))
        subgenres = _string_list(filters.get("subgenres"))
        presentation_types = _string_list(filters.get("presentation_types"))

        if kind is CollectionKind.CHART:
            result = self._client.streaming_charts(
                country,
                self._language,
                after=cursor,
                limit=page_size,
                object_type=collection.media_type,
                packages=packages,
            )
            return Page(
                items=tuple(
                    _raw_from_chart(entry)
                    for entry in result.charts
                    if entry.title.tmdb_id is not None or entry.title.imdb_id
                ),
                next_cursor=result.next_cursor,
                total_pages=None,
                total_items=result.total_items,
                raw=dict(result.raw),
            )

        if kind in _PAGE_TYPES:
            result = self._client.new_titles(
                country,
                self._language,
                _PAGE_TYPES[kind],
                offset=_offset(cursor),
                limit=page_size,
                packages=packages,
                object_type=collection.media_type,
            )
            return self._plain_page(result)

        if kind is CollectionKind.CATALOG:
            return self._catalog_page(
                collection,
                country,
                cursor,
                page_size,
                packages=packages,
                genres=genres,
                subgenres=subgenres,
                presentation_types=presentation_types,
            )

        raise NotSupportedError(
            f"JustWatch non supporta collezioni di tipo {kind.value} "
            f"(collezione '{collection.key}')."
        )

    def _catalog_page(
        self,
        collection: SourceCollection,
        country: str,
        cursor: str | None,
        page_size: int,
        *,
        packages: list[str] | None,
        genres: list[str] | None,
        subgenres: list[str] | None,
        presentation_types: list[str] | None,
    ) -> Page:
        """Walk the catalog by splitting ``releaseYear`` ranges under the 1999 cap."""
        year_from = int(collection.metadata.get("year_from") or self._year_from)
        year_to = int(collection.metadata.get("year_to") or self._year_to)
        state = YearRanges.parse(cursor, year_from, year_to)
        lo, hi = state.ranges[0]

        result = self._client.popular_titles(
            country,
            self._language,
            offset=state.offset,
            limit=max(1, min(page_size, MAX_REACHABLE_ITEMS - state.offset)),
            packages=packages,
            object_type=collection.media_type,
            genres=genres,
            subgenres=subgenres,
            release_year=(lo, hi),
            presentation_types=presentation_types,
        )
        total = result.total_items or 0
        raw = dict(result.raw)
        raw["_range"] = {"from": lo, "to": hi, "offset": state.offset, "total": total}

        # Too big for one range: split and restart from the first half.
        if state.offset == 0 and total > MAX_REACHABLE_ITEMS and lo < hi:
            mid = (lo + hi) // 2
            return self._catalog_page(
                collection,
                country,
                state.split(mid).serialize(),
                page_size,
                packages=packages,
                genres=genres,
                subgenres=subgenres,
                presentation_types=presentation_types,
            )

        # Titles without any external id cannot be resolved or synced. Skip
        # them, but advance the offset by the source rows, not by the kept rows.
        items = tuple(
            _raw_from_title(title)
            for title in result.titles
            if title.tmdb_id is not None or title.imdb_id
        )
        next_offset = state.offset + len(result.titles)
        if next_offset >= min(total, MAX_REACHABLE_ITEMS):
            if total > MAX_REACHABLE_ITEMS:
                # Single year above the cap: nothing more can be reached.
                raw["_truncated"] = True
            following = state.advance()
            return Page(
                items=items,
                next_cursor=following.serialize() if following else None,
                total_pages=None,
                total_items=total,
                raw=raw,
            )
        return Page(
            items=items,
            next_cursor=state.with_offset(next_offset).serialize(),
            total_pages=None,
            total_items=total,
            raw=raw,
        )

    def _plain_page(self, result: JustWatchPage) -> Page:
        return Page(
            items=tuple(
                _raw_from_title(title)
                for title in result.titles
                if title.tmdb_id is not None or title.imdb_id
            ),
            next_cursor=result.next_cursor,
            total_pages=None,
            total_items=result.total_items,
            raw=dict(result.raw),
        )

    # -- hierarchy ---------------------------------------------------------
    def list_seasons(self, show_id: str, country_code: str = "IT") -> list[JustWatchSeason]:
        return self._client.seasons(show_id, country_code, self._language)

    def list_episodes(self, season_id: str, country_code: str = "IT") -> list[JustWatchEpisode]:
        return self._client.episodes(season_id, country_code, self._language)

    # -- normalization -----------------------------------------------------
    def normalize_item(self, raw: RawItem) -> NormalizedItem:
        return NormalizedItem(
            media_type=raw.media_type,
            tmdb_id=raw.tmdb_id,
            imdb_id=raw.imdb_id,
            title=raw.title,
            year=raw.year,
            offer_types=frozenset(raw.offer_types),
            source_date_created=None,
            date_basis=DateBasis.UNKNOWN,
            raw=dict(raw.source_payload),
        )

    def close(self) -> None:
        self._client.close()


def _offset(cursor: str | None) -> int:
    if cursor is None:
        return 0
    try:
        return max(0, min(int(cursor), MAX_REACHABLE_ITEMS))
    except (TypeError, ValueError):
        return 0


def _string_list(value: object) -> list[str] | None:
    if not value:
        return None
    values = value if isinstance(value, (list, tuple)) else str(value).split(",")
    parsed = [str(item).strip() for item in values if str(item).strip()]
    return parsed or None


def _packages(collection: SourceCollection, filters: dict[str, object]) -> list[str] | None:
    return _string_list(filters.get("packages")) or _string_list(
        collection.metadata.get("packages")
    )


def _raw_from_title(title: JustWatchTitle) -> RawItem:
    return RawItem(
        source_item_id=title.node_id,
        media_type=title.media_type,
        title=title.title,
        year=title.year,
        tmdb_id=title.tmdb_id,
        imdb_id=title.imdb_id,
        tvdb_id=None,
        source_date_created=None,
        offer_types=title.offer_types,
        source_payload=dict(title.raw),
    )


def _raw_from_chart(entry: JustWatchChartEntry) -> RawItem:
    payload = dict(entry.title.raw)
    payload["_chart"] = {
        "rank": entry.rank,
        "trend": entry.trend,
        "trendDifference": entry.trend_difference,
        "daysInTop10": entry.days_in_top10,
        "topRank": entry.top_rank,
    }
    return RawItem(
        source_item_id=entry.title.node_id,
        media_type=entry.title.media_type,
        title=entry.title.title,
        year=entry.title.year,
        tmdb_id=entry.title.tmdb_id,
        imdb_id=entry.title.imdb_id,
        tvdb_id=None,
        source_date_created=None,
        offer_types=entry.title.offer_types,
        source_payload=payload,
    )
