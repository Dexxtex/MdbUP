"""JustWatch connector: collections, partitioned pagination, hierarchy."""

from __future__ import annotations

import httpx
import pytest
import respx

from app.connectors.base import NotSupportedError, RawItem, SourceCollection
from app.connectors.justwatch.connector import (
    JUSTWATCH_SOURCE_KEY,
    JustWatchConnector,
    YearRanges,
)
from app.domain.enums import (
    CollectionKind,
    CollectionOrigin,
    DateBasis,
    MediaType,
)
from app.integrations.justwatch.client import MAX_REACHABLE_ITEMS, JustWatchClient
from app.integrations.justwatch.models import (
    JustWatchEpisode,
    JustWatchOffer,
    JustWatchPage,
    JustWatchSeason,
    JustWatchTitle,
)

BASE = "https://apis.justwatch.com/graphql"


def _offer(package: str = "nfx", monetization: str = "FLATRATE") -> JustWatchOffer:
    return JustWatchOffer(monetization_type=monetization, package_short_name=package)


def _title(
    node_id: str,
    *,
    media_type: MediaType = MediaType.MOVIE,
    offers: tuple[JustWatchOffer, ...] | None = None,
) -> JustWatchTitle:
    return JustWatchTitle(
        node_id=node_id,
        media_type=media_type,
        title=f"Title {node_id}",
        year=1999,
        tmdb_id=603,
        imdb_id="tt0133093",
        offers=(_offer(),) if offers is None else offers,
        raw={"id": node_id},
    )


class StubClient:
    """Client stub: totals per releaseYear range, deterministic pages."""

    def __init__(self, totals: dict[tuple[int, int], int]) -> None:
        self.totals = totals
        self.calls: list[dict[str, object]] = []

    def popular_titles(
        self,
        country: str,
        language: str,
        *,
        offset: int = 0,
        limit: int = 100,
        packages=None,
        object_type=None,
        monetization_types=None,
        genres=None,
        subgenres=None,
        release_year=None,
        presentation_types=None,
    ) -> JustWatchPage:
        self.calls.append(
            {
                "offset": offset,
                "limit": limit,
                "release_year": release_year,
                "genres": genres,
                "subgenres": subgenres,
                "presentation_types": presentation_types,
                "packages": packages,
            }
        )
        lo, hi = release_year if release_year else (0, 0)
        total = self.totals.get((lo, hi), 0)
        count = max(0, min(limit, total - offset))
        titles = tuple(_title(f"{lo}-{hi}-{offset + index}") for index in range(count))
        return JustWatchPage(titles=titles, next_cursor=None, total_items=total, raw={})

    def new_titles(self, country, language, page_type, **kwargs) -> JustWatchPage:
        self.calls.append({"page_type": page_type, **kwargs})
        return JustWatchPage(titles=(_title("new-1"),), next_cursor=None, total_items=1, raw={})

    def streaming_charts(self, country, language, **kwargs) -> JustWatchPage:
        self.calls.append({"charts": True, **kwargs})
        return JustWatchPage(charts=(), next_cursor=None, total_items=0, raw={})

    def list_packages(self, country: str):
        from app.integrations.justwatch.models import JustWatchPackage

        return [
            JustWatchPackage(short_name="nfx", name="Netflix", monetization_types=("FLATRATE",)),
            JustWatchPackage(
                short_name="prv", name="Prime Video", monetization_types=("FLATRATE",)
            ),
        ]

    def list_genres(self, language: str):
        return [{"shortName": "act", "slug": "azione-e-avventura"}]

    def seasons(self, show_id: str, country: str, language: str):
        return [JustWatchSeason(node_id="tss26", title="Stagione 1", total_episode_count=7)]

    def episodes(self, season_id: str, country: str, language: str):
        return [
            JustWatchEpisode(
                node_id="tse412",
                title="Questione di chimica",
                season_number=1,
                episode_number=1,
            )
        ]

    def healthcheck(self):
        from app.connectors.base import HealthStatus

        return HealthStatus(ok=True, message="stub")

    def close(self) -> None:
        return None


def _connector(totals: dict[tuple[int, int], int] | None = None) -> JustWatchConnector:
    return JustWatchConnector(StubClient(totals or {}), language="it")


def _collection(
    kind: CollectionKind,
    media_type: MediaType = MediaType.MOVIE,
    *,
    filters: dict | None = None,
    year_from: int = 1900,
    year_to: int = 2030,
) -> SourceCollection:
    return SourceCollection(
        key=f"nfx:{media_type.value}",
        name="Netflix — Film",
        provider_external_id="nfx",
        media_type=media_type,
        kind=kind,
        origin=CollectionOrigin.AGGREGATOR,
        date_basis=DateBasis.UNKNOWN,
        metadata={
            "watch_region": "IT",
            "packages": ["nfx"],
            "media_type": media_type.value,
            "year_from": year_from,
            "year_to": year_to,
            "filters": filters or {},
        },
    )


# -- capabilities ---------------------------------------------------------


def test_capabilities_declare_full_pagination_and_hierarchy() -> None:
    capabilities = _connector().capabilities
    assert _connector().key == JUSTWATCH_SOURCE_KEY
    assert capabilities.catalog is True
    assert capabilities.charts is True
    assert capabilities.upcoming is True
    assert capabilities.recently_added is True
    assert capabilities.full_pagination is True
    assert capabilities.seasons_episodes is True
    assert capabilities.added_dates is False
    assert capabilities.requires_credentials is False
    assert capabilities.requires_contract is False
    assert capabilities.max_page_size == 100


# -- collections ----------------------------------------------------------


def test_list_collections_is_per_provider_and_per_kind() -> None:
    collections = _connector().list_collections("IT")
    keys = {collection.key for collection in collections}
    # 2 providers x 4 kinds x 2 media types
    assert len(collections) == 16
    assert "nfx:MOVIE" in keys
    assert "chart:nfx:SHOW" in keys
    assert "recently-added:prv:MOVIE" in keys
    assert "upcoming:nfx:SHOW" in keys
    for collection in collections:
        assert collection.provider_external_id
        assert collection.metadata["packages"] == [collection.provider_external_id]
        assert collection.origin is CollectionOrigin.AGGREGATOR
        assert collection.date_basis is DateBasis.UNKNOWN


# -- partitioned pagination -----------------------------------------------


def test_year_ranges_roundtrip_and_split() -> None:
    state = YearRanges.start(1900, 2030)
    assert state.serialize() == "1900-2030:0"
    split = state.split(1965)
    assert split.ranges == ((1900, 1965), (1966, 2030))
    assert YearRanges.parse(split.serialize(), 1900, 2030) == split
    assert YearRanges.parse("garbage", 1900, 2030) == state
    assert split.advance() == YearRanges(((1966, 2030),), 0)


def test_catalog_walk_covers_more_than_the_1999_cap() -> None:
    """A range above the cap is split; the walk reaches every leaf."""
    totals = {
        (1900, 2030): 5000,  # forces a split
        (1900, 1965): 1200,
        (1966, 2030): 3800,  # forces another split
        (1966, 1998): 1700,
        (1999, 2030): 2100,  # forces a third split
        (1999, 2014): 1000,
        (2015, 2030): 1100,
    }
    connector = _connector(totals)
    collection = _collection(CollectionKind.CATALOG)

    seen: list[str] = []
    cursor: str | None = None
    for _ in range(200):
        page = connector.fetch_collection_page(collection, cursor, 500)
        seen.extend(item.source_item_id for item in page.items)
        cursor = page.next_cursor
        if cursor is None:
            break
    assert cursor is None, "la paginazione non è terminata"
    assert len(seen) == 5000
    assert len(set(seen)) == 5000, "titoli duplicati tra le partizioni"


def test_catalog_page_advances_to_next_year_when_range_is_done() -> None:
    totals = {(1900, 2030): 5000, (1900, 1965): 10, (1966, 2030): 20}
    connector = _connector(totals)
    collection = _collection(CollectionKind.CATALOG)

    first = connector.fetch_collection_page(collection, None, 100)
    assert len(first.items) == 10
    assert first.next_cursor is not None
    # The cursor now points at the second half of the split range.
    second = connector.fetch_collection_page(collection, first.next_cursor, 100)
    assert len(second.items) == 20
    assert second.next_cursor is None


def test_catalog_truncates_a_single_year_above_the_cap() -> None:
    totals = {(2020, 2020): MAX_REACHABLE_ITEMS + 500}
    connector = _connector(totals)
    collection = _collection(CollectionKind.CATALOG, year_from=2020, year_to=2020)

    seen: list[str] = []
    cursor: str | None = None
    truncated = False
    for _ in range(50):
        page = connector.fetch_collection_page(collection, cursor, 1000)
        seen.extend(item.source_item_id for item in page.items)
        truncated = truncated or bool(page.raw.get("_truncated"))
        cursor = page.next_cursor
        if cursor is None:
            break
    assert len(seen) == MAX_REACHABLE_ITEMS
    assert len(set(seen)) == MAX_REACHABLE_ITEMS
    assert truncated is True


def test_catalog_passes_genre_and_quality_filters() -> None:
    client = StubClient({(1900, 2030): 1})
    connector = JustWatchConnector(client, language="it")
    collection = _collection(
        CollectionKind.CATALOG,
        filters={"genres": ["act"], "subgenres": ["adva"], "presentation_types": ["4K"]},
    )
    connector.fetch_collection_page(collection, None, 50)
    call = client.calls[-1]
    assert call["genres"] == ["act"]
    assert call["subgenres"] == ["adva"]
    assert call["presentation_types"] == ["4K"]


def test_recently_added_uses_new_titles_page_type() -> None:
    client = StubClient({})
    connector = JustWatchConnector(client, language="it")
    connector.fetch_collection_page(_collection(CollectionKind.RECENTLY_ADDED), None, 100)
    assert client.calls[-1]["page_type"] == "NEW"


def test_unsupported_collection_kind_raises() -> None:
    with pytest.raises(NotSupportedError):
        _connector().fetch_collection_page(_collection(CollectionKind.CUSTOM_FILTER), None, 100)


# -- hierarchy ------------------------------------------------------------


def test_seasons_and_episodes_are_exposed() -> None:
    connector = _connector()
    seasons = connector.list_seasons("ts4")
    assert seasons[0].node_id == "tss26"
    assert seasons[0].total_episode_count == 7
    episodes = connector.list_episodes("tss26")
    assert episodes[0].episode_number == 1


# -- normalization --------------------------------------------------------


def test_normalize_item_is_aggregator_without_date() -> None:
    normalized = _connector().normalize_item(
        RawItem(
            source_item_id="tm10",
            media_type=MediaType.MOVIE,
            title="Matrix",
            year=1999,
            tmdb_id=603,
            imdb_id="tt0133093",
            offer_types=frozenset({"FLATRATE"}),
            source_payload={"id": "tm10"},
        )
    )
    assert normalized.tmdb_id == 603
    assert normalized.date_basis is DateBasis.UNKNOWN
    assert normalized.source_date_created is None
    assert normalized.offer_types == frozenset({"FLATRATE"})


# -- registry -------------------------------------------------------------


def test_registry_registers_justwatch_without_any_flag() -> None:
    from app.connectors.registry import create_connector, is_registered
    from app.core.config import Settings

    assert is_registered(JUSTWATCH_SOURCE_KEY) is True
    connector = create_connector(None, Settings(), JUSTWATCH_SOURCE_KEY)  # type: ignore[arg-type]
    assert isinstance(connector, JustWatchConnector)
    connector.close()


# -- live-shaped payload through the real client --------------------------


@respx.mock
def test_catalog_page_through_http_client_keeps_ids() -> None:
    respx.post(BASE).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "popularTitles": {
                        "totalCount": 1,
                        "pageInfo": {"hasNextPage": False, "endCursor": "MQ=="},
                        "edges": [
                            {
                                "node": {
                                    "id": "tm10",
                                    "objectType": "MOVIE",
                                    "content": {
                                        "title": "Matrix",
                                        "originalReleaseYear": 1999,
                                        "fullPath": "/it/film/the-matrix",
                                        "runtime": 131,
                                        "externalIds": {"imdbId": "tt0133093", "tmdbId": "603"},
                                    },
                                    "offers": [
                                        {
                                            "monetizationType": "FLATRATE",
                                            "presentationType": "HD",
                                            "standardWebURL": "https://example.test",
                                            "package": {"clearName": "Netflix", "shortName": "nfx"},
                                        }
                                    ],
                                }
                            }
                        ],
                    }
                }
            },
        )
    )
    client = JustWatchClient(
        BASE,
        sleep=lambda _seconds: None,
        monotonic=lambda: 0.0,
        min_interval_seconds=0,
        backoff_base_seconds=0,
        backoff_max_seconds=0,
        jitter_ratio=0,
    )
    connector = JustWatchConnector(client, language="it")
    page = connector.fetch_collection_page(_collection(CollectionKind.CATALOG), None, 100)
    item = page.items[0]
    assert item.source_item_id == "tm10"
    assert item.tmdb_id == 603
    assert item.imdb_id == "tt0133093"
    assert item.offer_types == frozenset({"FLATRATE"})
    assert page.next_cursor is None


def test_titles_without_external_ids_are_skipped_but_pagination_advances() -> None:
    class MissingIdClient(StubClient):
        def new_titles(self, country, language, page_type, **kwargs):
            return JustWatchPage(
                titles=(
                    JustWatchTitle(
                        node_id="no-ids",
                        media_type=MediaType.MOVIE,
                        title="Senza ID",
                        year=2020,
                        tmdb_id=None,
                        imdb_id=None,
                        raw={"id": "no-ids"},
                    ),
                    _title("with-id"),
                ),
                next_cursor="next",
                total_items=2,
                raw={},
            )

    connector = JustWatchConnector(MissingIdClient({}), language="it")
    page = connector.fetch_collection_page(_collection(CollectionKind.RECENTLY_ADDED), None, 100)
    assert [item.source_item_id for item in page.items] == ["with-id"]
    assert page.next_cursor == "next"
