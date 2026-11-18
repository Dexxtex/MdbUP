"""TMDb connector: normalization, discover paging and collection shape."""

from __future__ import annotations

import httpx
import pytest
import respx

from app.connectors.base import RawItem, SourceCollection, SourceProvider
from app.connectors.tmdb.connector import MAX_DISCOVER_PAGES, TMDbConnector
from app.domain.enums import (
    CollectionKind,
    CollectionOrigin,
    DateBasis,
    MediaType,
    ResolutionStatus,
)
from app.integrations.tmdb.client import TMDbClient, TMDbRateLimitError
from app.services import normalization

BASE = "https://api.themoviedb.org/3"


def _connector() -> TMDbConnector:
    return TMDbConnector(TMDbClient("test-token", base_url=BASE))


def _collection(media_type: MediaType = MediaType.MOVIE) -> SourceCollection:
    return SourceCollection(
        key=f"8:{media_type.value}",
        name="Netflix — Film",
        provider_external_id="8",
        media_type=media_type,
        kind=CollectionKind.CATALOG,
        origin=CollectionOrigin.AGGREGATOR,
        date_basis=DateBasis.UNKNOWN,
        metadata={"provider_id": 8, "watch_region": "IT"},
    )


def test_capabilities_are_aggregator_and_credentialed() -> None:
    connector = _connector()
    assert connector.key == "tmdb"
    assert connector.capabilities.catalog is True
    assert connector.capabilities.added_dates is False
    assert connector.capabilities.recently_added is False
    assert connector.capabilities.full_pagination is False
    assert connector.capabilities.requires_credentials is True
    assert connector.capabilities.requires_contract is False


def test_normalize_item_with_tmdb_id() -> None:
    connector = _connector()
    raw = RawItem(
        source_item_id="603",
        media_type=MediaType.MOVIE,
        title="Matrix",
        year=1999,
        tmdb_id=603,
        offer_types=frozenset({"FLATRATE"}),
        source_payload={"id": 603, "title": "Matrix"},
    )
    item = connector.normalize_item(raw)
    assert item.tmdb_id == 603
    assert item.imdb_id is None
    assert item.date_basis is DateBasis.UNKNOWN
    assert item.source_date_created is None
    assert item.offer_types == frozenset({"FLATRATE"})
    assert normalization.resolution_status(item) is ResolutionStatus.RESOLVED


def test_normalize_item_with_only_imdb_id() -> None:
    connector = _connector()
    raw = RawItem(
        source_item_id="tt0133093",
        media_type=MediaType.MOVIE,
        title="Matrix",
        imdb_id="tt0133093",
    )
    item = connector.normalize_item(raw)
    assert item.tmdb_id is None
    assert item.imdb_id == "tt0133093"
    assert item.offer_types == frozenset({"FLATRATE"})
    assert normalization.resolution_status(item) is ResolutionStatus.RESOLVED


def test_normalize_item_without_ids_is_unresolved() -> None:
    connector = _connector()
    raw = RawItem(
        source_item_id="unknown",
        media_type=MediaType.SHOW,
        title="Senza identificativi",
    )
    item = connector.normalize_item(raw)
    assert item.tmdb_id is None
    assert item.imdb_id is None
    assert normalization.resolution_status(item) is ResolutionStatus.UNRESOLVED


@respx.mock
def test_fetch_collection_page_maps_discover_payload() -> None:
    route = respx.get(f"{BASE}/discover/movie").mock(
        return_value=httpx.Response(
            200,
            json={
                "page": 1,
                "total_pages": 3,
                "total_results": 45,
                "results": [
                    {
                        "id": 101,
                        "title": "Film A",
                        "original_title": "Film A",
                        "release_date": "2020-05-01",
                        "popularity": 12.5,
                    }
                ],
            },
        )
    )
    connector = _connector()
    page = connector.fetch_collection_page(_collection(), None, 20)
    assert route.called
    params = route.calls.last.request.url.params
    assert params["watch_region"] == "IT"
    assert params["with_watch_providers"] == "8"
    assert params["with_watch_monetization_types"] == "flatrate"
    assert params["sort_by"] == "popularity.desc"
    assert page.total_pages == 3
    assert page.next_cursor == "2"
    assert page.total_items == 45
    assert len(page.items) == 1
    raw = page.items[0]
    assert raw.tmdb_id == 101
    assert raw.title == "Film A"
    assert raw.year == 2020
    assert raw.source_date_created is None
    connector.close()


@respx.mock
def test_fetch_collection_page_passes_genre_filter() -> None:
    route = respx.get(f"{BASE}/discover/movie").mock(
        return_value=httpx.Response(
            200,
            json={"page": 1, "total_pages": 1, "total_results": 0, "results": []},
        )
    )
    collection = _collection()
    collection.metadata["filters"] = {"with_genres": "28,12"}
    connector = _connector()
    connector.fetch_collection_page(collection, None, 20)
    assert route.calls.last.request.url.params["with_genres"] == "28,12"
    assert route.calls.last.request.url.params["with_watch_monetization_types"] == "flatrate"
    connector.close()


@respx.mock
def test_fetch_collection_page_caps_discover_at_500_pages() -> None:
    respx.get(f"{BASE}/discover/tv").mock(
        return_value=httpx.Response(
            200,
            json={
                "page": 500,
                "total_pages": 900,
                "total_results": 18000,
                "results": [{"id": 7, "name": "Serie", "first_air_date": "2019-01-01"}],
            },
        )
    )
    connector = _connector()
    page = connector.fetch_collection_page(_collection(MediaType.SHOW), "500", 20)
    assert page.total_pages == MAX_DISCOVER_PAGES
    assert page.next_cursor is None
    assert page.items[0].media_type is MediaType.SHOW
    connector.close()


@respx.mock
def test_list_providers_merges_movie_and_tv_results() -> None:
    respx.get(f"{BASE}/watch/providers/movie").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {"provider_id": 8, "provider_name": "Netflix", "display_priority": 1},
                    {"provider_id": 337, "provider_name": "Disney Plus", "display_priority": 3},
                ]
            },
        )
    )
    respx.get(f"{BASE}/watch/providers/tv").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {"provider_id": 8, "provider_name": "Netflix", "display_priority": 1},
                    {"provider_id": 39, "provider_name": "Now TV", "display_priority": 2},
                ]
            },
        )
    )
    connector = _connector()
    providers = connector.list_providers("IT")
    assert [provider.external_id for provider in providers] == ["8", "39", "337"]
    connector.close()


def test_list_collections_is_aggregator_catalog_flatrate() -> None:
    connector = _connector()
    providers = [SourceProvider(external_id="8", name="Netflix", country_code="IT")]
    connector.list_providers = lambda country_code: providers  # type: ignore[method-assign]
    collections = connector.list_collections("IT")
    assert len(collections) == 2
    for collection in collections:
        assert collection.kind is CollectionKind.CATALOG
        assert collection.origin is CollectionOrigin.AGGREGATOR
        assert collection.date_basis is DateBasis.UNKNOWN
        assert collection.source_url is None
        assert collection.metadata["offer_types"] == ["FLATRATE"]
        assert collection.metadata["provider_id"] == 8
    assert {collection.media_type for collection in collections} == {
        MediaType.MOVIE,
        MediaType.SHOW,
    }


@respx.mock
def test_rate_limit_beyond_wait_budget_raises() -> None:
    respx.get(f"{BASE}/discover/movie").mock(
        return_value=httpx.Response(429, headers={"Retry-After": "120"})
    )
    connector = _connector()
    with pytest.raises(TMDbRateLimitError):
        connector.fetch_collection_page(_collection(), None, 20)
    connector.close()


@respx.mock
def test_fetch_collection_page_preserves_genre_ids_for_shared_snapshots() -> None:
    respx.get(f"{BASE}/discover/movie").mock(
        return_value=httpx.Response(
            200,
            json={
                "page": 1,
                "total_pages": 1,
                "total_results": 1,
                "results": [
                    {
                        "id": 603,
                        "title": "Matrix",
                        "release_date": "1999-03-31",
                        "genre_ids": [28, 878],
                    }
                ],
            },
        )
    )
    connector = _connector()
    page = connector.fetch_collection_page(_collection(), None, 20)
    assert page.items[0].source_payload["genre_ids"] == [28, 878]
    connector.close()


@respx.mock
def test_fetch_collection_page_uses_configured_sort() -> None:
    route = respx.get(f"{BASE}/discover/tv").mock(
        return_value=httpx.Response(
            200,
            json={"page": 1, "total_pages": 1, "total_results": 0, "results": []},
        )
    )
    collection = _collection(MediaType.SHOW)
    collection.metadata["filters"] = {"sort_by": "vote_count.desc"}
    connector = _connector()
    connector.fetch_collection_page(collection, None, 20)
    assert route.calls.last.request.url.params["sort_by"] == "vote_count.desc"
    connector.close()
