"""TMDb source connector.

TMDb exposes *current* availability only: there is no provider add date, so
every collection is ``AGGREGATOR`` with ``date_basis=UNKNOWN`` and
``source_date_created=None``. Discover is capped at 500 pages by the API.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.connectors.base import (
    ConnectorCapabilities,
    HealthStatus,
    NormalizedItem,
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
    OfferType,
)
from app.integrations.tmdb.client import TMDbClient
from app.integrations.tmdb.models import TMDbProvider

MAX_DISCOVER_PAGES = 500
TMDB_SOURCE_KEY = "tmdb"

CAPABILITIES = ConnectorCapabilities(
    catalog=True,
    recently_added=False,
    upcoming=False,
    charts=False,
    ordering=False,
    added_dates=False,
    seasons_episodes=True,
    full_pagination=False,
    data_export=False,
    requires_credentials=True,
    requires_contract=False,
    max_page_size=20,
    notes="Aggregatore: nessuna data di aggiunta, cap 500 pagine, flatrate.",
)

_FLATRATE = frozenset({OfferType.FLATRATE.value})


class TMDbConnector:
    """``SourceConnector`` implementation backed by :class:`TMDbClient`."""

    key = TMDB_SOURCE_KEY
    capabilities = CAPABILITIES

    def __init__(self, client: TMDbClient) -> None:
        self._client = client

    def healthcheck(self) -> HealthStatus:
        return self._client.healthcheck()

    def list_providers(self, country_code: str = "IT") -> Sequence[SourceProvider]:
        providers: dict[int, TMDbProvider] = {}
        for provider in self._client.list_movie_providers(country_code):
            providers.setdefault(provider.provider_id, provider)
        for provider in self._client.list_tv_providers(country_code):
            providers.setdefault(provider.provider_id, provider)
        ordered = sorted(
            providers.values(),
            key=lambda item: (item.display_priority or 10_000, item.name.lower()),
        )
        return [
            SourceProvider(
                external_id=str(provider.provider_id),
                name=provider.name,
                country_code=country_code,
            )
            for provider in ordered
        ]

    def list_collections(self, country_code: str = "IT") -> Sequence[SourceCollection]:
        collections: list[SourceCollection] = []
        for provider in self.list_providers(country_code):
            for media_type in (MediaType.MOVIE, MediaType.SHOW):
                collections.append(self._build_collection(provider, media_type, country_code))
        return collections

    def _build_collection(
        self,
        provider: SourceProvider,
        media_type: MediaType,
        country_code: str,
    ) -> SourceCollection:
        label = "Film" if media_type is MediaType.MOVIE else "Serie"
        return SourceCollection(
            key=f"{provider.external_id}:{media_type.value}",
            name=f"{provider.name} — {label}",
            provider_external_id=provider.external_id,
            media_type=media_type,
            kind=CollectionKind.CATALOG,
            origin=CollectionOrigin.AGGREGATOR,
            date_basis=DateBasis.UNKNOWN,
            source_url=None,
            metadata={
                "provider_id": int(provider.external_id),
                "media_type": media_type.value,
                "offer_types": sorted(_FLATRATE),
                "watch_region": country_code,
            },
        )

    def fetch_collection_page(
        self,
        collection: SourceCollection,
        cursor: str | None,
        page_size: int,
    ) -> Page:
        page_number = _parse_cursor(cursor)
        if page_number > MAX_DISCOVER_PAGES:
            return Page(items=(), next_cursor=None, total_pages=MAX_DISCOVER_PAGES)
        provider_id = _provider_id(collection)
        country = str(collection.metadata.get("watch_region") or "IT")
        genre_ids = _genre_ids(collection)
        filters = collection.metadata.get("filters") or {}
        sort_by = (
            str(filters.get("sort_by"))
            if isinstance(filters, dict) and filters.get("sort_by")
            else "popularity.desc"
        )
        if collection.media_type is MediaType.MOVIE:
            discover = self._client.discover_movies(
                provider_id, country, page_number, genre_ids, sort_by
            )
        else:
            discover = self._client.discover_tv(
                provider_id, country, page_number, genre_ids, sort_by
            )
        items = tuple(
            RawItem(
                source_item_id=str(item.tmdb_id),
                media_type=item.media_type,
                title=item.title,
                year=item.release_year,
                tmdb_id=item.tmdb_id,
                imdb_id=None,
                source_date_created=None,
                offer_types=_FLATRATE,
                source_payload=dict(item.raw),
            )
            for item in discover.items
        )
        total_pages = min(discover.total_pages or 0, MAX_DISCOVER_PAGES)
        has_next = bool(total_pages) and page_number < total_pages
        return Page(
            items=items,
            next_cursor=str(page_number + 1) if has_next else None,
            total_pages=total_pages or None,
            total_items=discover.total_results or None,
            raw=dict(discover.raw),
        )

    def normalize_item(self, raw: RawItem) -> NormalizedItem:
        return NormalizedItem(
            media_type=raw.media_type,
            tmdb_id=raw.tmdb_id,
            imdb_id=raw.imdb_id,
            title=raw.title,
            year=raw.year,
            offer_types=frozenset(raw.offer_types or _FLATRATE),
            source_date_created=None,
            date_basis=DateBasis.UNKNOWN,
            raw=dict(raw.source_payload),
        )

    def close(self) -> None:
        self._client.close()


def _parse_cursor(cursor: str | None) -> int:
    if cursor is None:
        return 1
    try:
        return max(1, int(cursor))
    except (TypeError, ValueError):
        return 1


def _genre_ids(collection: SourceCollection) -> list[int] | None:
    filters = collection.metadata.get("filters") or {}
    raw = filters.get("with_genres") if isinstance(filters, dict) else None
    if raw is None:
        return None
    values = raw if isinstance(raw, (list, tuple)) else str(raw).split(",")
    parsed: list[int] = []
    for value in values:
        try:
            genre_id = int(value)
        except (TypeError, ValueError):
            continue
        if genre_id > 0:
            parsed.append(genre_id)
    return parsed or None


def _provider_id(collection: SourceCollection) -> int:
    raw = collection.metadata.get("provider_id", collection.provider_external_id)
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"provider_id TMDb non valido per la collezione '{collection.key}'."
        ) from exc
