"""JustWatch public client: parsing, pagination caps and error mapping (respx)."""

from __future__ import annotations

import httpx
import pytest
import respx

from app.domain.enums import MediaType
from app.integrations.justwatch.client import (
    MAX_PAGE_SIZE,
    MAX_REACHABLE_ITEMS,
    JustWatchAuthError,
    JustWatchClient,
    JustWatchGraphQLError,
    JustWatchRateLimitError,
    JustWatchRequestError,
)

BASE = "https://apis.justwatch.com/graphql"


def _client(**kwargs: object) -> JustWatchClient:
    return JustWatchClient(
        BASE,
        sleep=lambda _seconds: None,
        monotonic=lambda: 0.0,
        min_interval_seconds=0,
        backoff_base_seconds=0,
        backoff_max_seconds=0,
        jitter_ratio=0,
        **kwargs,
    )


def _node(
    node_id: str = "tm10",
    *,
    object_type: str = "MOVIE",
    title: str = "Matrix",
    year: int = 1999,
    tmdb: str | None = "603",
    imdb: str | None = "tt0133093",
    offers: list[dict] | None = None,
) -> dict:
    return {
        "id": node_id,
        "objectType": object_type,
        "content": {
            "title": title,
            "originalReleaseYear": year,
            "fullPath": "/it/film/the-matrix",
            "runtime": 131,
            "externalIds": {"imdbId": imdb, "tmdbId": tmdb},
        },
        "offers": offers
        if offers is not None
        else [
            {
                "monetizationType": "FLATRATE",
                "presentationType": "HD",
                "standardWebURL": "https://example.test/watch",
                "package": {"clearName": "Netflix", "shortName": "nfx"},
            }
        ],
    }


def _connection(nodes: list[dict], *, has_next: bool = False, total: int = 1) -> dict:
    return {
        "totalCount": total,
        "pageInfo": {"hasNextPage": has_next, "endCursor": "MTAw"},
        "edges": [{"node": node} for node in nodes],
    }


@respx.mock
def test_popular_titles_parses_ids_offers_and_cursor() -> None:
    route = respx.post(BASE).mock(
        return_value=httpx.Response(
            200, json={"data": {"popularTitles": _connection([_node()], total=8513)}}
        )
    )
    page = _client().popular_titles("IT", "it", offset=0, limit=50, packages=["nfx"])

    assert len(page.titles) == 1
    title = page.titles[0]
    assert title.node_id == "tm10"
    assert title.media_type is MediaType.MOVIE
    assert title.tmdb_id == 603
    assert title.imdb_id == "tt0133093"
    assert title.year == 1999
    assert title.offer_types == frozenset({"FLATRATE"})
    assert title.package_short_names == frozenset({"nfx"})
    assert page.total_items == 8513
    assert page.next_cursor is None  # hasNextPage false

    payload = route.calls.last.request.content
    assert b'"packages":["nfx"]' in payload
    assert b'"objectTypes"' not in payload


@respx.mock
def test_page_size_is_clamped_to_server_limit() -> None:
    route = respx.post(BASE).mock(
        return_value=httpx.Response(200, json={"data": {"popularTitles": _connection([])}})
    )
    _client().popular_titles("IT", "it", limit=500)
    assert f'"first":{MAX_PAGE_SIZE}'.encode() in route.calls.last.request.content


@respx.mock
def test_offset_past_reachable_cap_short_circuits() -> None:
    connector = _client()
    page = connector.popular_titles("IT", "it", offset=MAX_REACHABLE_ITEMS)
    assert page.titles == ()
    assert page.next_cursor is None
    # No HTTP call was made: the endpoint returns nothing past #1999 anyway.
    assert not respx.calls


@respx.mock
def test_next_cursor_advances_by_items_returned() -> None:
    respx.post(BASE).mock(
        return_value=httpx.Response(
            200,
            json={"data": {"popularTitles": _connection([_node(), _node("tm11")], has_next=True)}},
        )
    )
    page = _client().popular_titles("IT", "it", offset=10, limit=2)
    assert page.next_cursor == "12"


@respx.mock
def test_streaming_charts_reads_rank_from_edge_info() -> None:
    respx.post(BASE).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "streamingCharts": {
                        "totalCount": 20429,
                        "pageInfo": {"hasNextPage": True, "endCursor": "Mw=="},
                        "edges": [
                            {
                                "streamingChartInfo": {
                                    "rank": 1,
                                    "trend": "STABLE",
                                    "trendDifference": 0,
                                    "daysInTop10": 28,
                                    "topRank": 1,
                                },
                                "node": _node("tm1150069"),
                            }
                        ],
                    }
                }
            },
        )
    )
    page = _client().streaming_charts("IT", "it", limit=1, object_type=MediaType.MOVIE)
    assert page.next_cursor == "Mw=="
    entry = page.charts[0]
    assert entry.rank == 1
    assert entry.trend == "STABLE"
    assert entry.days_in_top10 == 28
    assert entry.top_rank == 1
    assert entry.title.node_id == "tm1150069"


def test_new_titles_rejects_unknown_page_type() -> None:
    with pytest.raises(ValueError, match="pageType"):
        _client().new_titles("IT", "it", "LEAVING")


@respx.mock
def test_graphql_errors_become_typed_exception() -> None:
    respx.post(BASE).mock(
        return_value=httpx.Response(
            422,
            json={
                "errors": [
                    {
                        "message": "page too large",
                        "extensions": {"code": "GRAPHQL_VALIDATION_FAILED"},
                    }
                ]
            },
        )
    )
    with pytest.raises(JustWatchGraphQLError) as excinfo:
        _client().popular_titles("IT", "it", limit=1)
    assert "page too large" in str(excinfo.value)
    assert excinfo.value.code == "GRAPHQL_VALIDATION_FAILED"


@respx.mock
def test_auth_error_is_not_retried() -> None:
    route = respx.post(BASE).mock(return_value=httpx.Response(403))
    with pytest.raises(JustWatchAuthError):
        _client().popular_titles("IT", "it", limit=1)
    assert route.call_count == 1


@respx.mock
def test_rate_limit_with_long_retry_after_raises() -> None:
    respx.post(BASE).mock(return_value=httpx.Response(429, headers={"retry-after": "120"}))
    with pytest.raises(JustWatchRateLimitError) as excinfo:
        _client().popular_titles("IT", "it", limit=1)
    assert excinfo.value.retry_after_seconds == 120


@respx.mock
def test_server_error_is_retried_then_succeeds() -> None:
    route = respx.post(BASE).mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(200, json={"data": {"popularTitles": _connection([_node()])}}),
        ]
    )
    page = _client(max_retries=2).popular_titles("IT", "it", limit=1)
    assert len(page.titles) == 1
    assert route.call_count == 2


@respx.mock
def test_healthcheck_never_raises() -> None:
    respx.post(BASE).mock(return_value=httpx.Response(500))
    status = _client(max_retries=1).healthcheck()
    assert status.ok is False
    assert status.latency_ms is not None


@respx.mock
def test_healthcheck_ok() -> None:
    respx.post(BASE).mock(return_value=httpx.Response(200, json={"data": {"__typename": "Query"}}))
    status = _client().healthcheck()
    assert status.ok is True


@respx.mock
def test_non_json_payload_is_request_error() -> None:
    respx.post(BASE).mock(return_value=httpx.Response(200, text="<html>nope</html>"))
    with pytest.raises(JustWatchRequestError):
        _client().popular_titles("IT", "it", limit=1)


@respx.mock
def test_list_packages_skips_rows_without_short_name() -> None:
    respx.post(BASE).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "packages": [
                        {
                            "id": 8,
                            "shortName": "nfx",
                            "clearName": "Netflix",
                            "technicalName": "netflix",
                            "monetizationTypes": ["FLATRATE"],
                        },
                        {"id": 9, "shortName": None, "clearName": "Broken"},
                    ]
                }
            },
        )
    )
    packages = _client().list_packages("IT")
    assert [package.short_name for package in packages] == ["nfx"]
    assert packages[0].monetization_types == ("FLATRATE",)


@respx.mock
def test_new_titles_maps_show_season_to_parent_show() -> None:
    """``newTitles`` returns Season nodes for shows; the parent Show is nested."""
    show = _node("ts1", object_type="SHOW", title="Serie", tmdb="123")
    route = respx.post(BASE).mock(
        return_value=httpx.Response(
            200,
            json={"data": {"newTitles": _connection([{"show": show}], total=1)}},
        )
    )

    page = _client().new_titles("IT", "it", "NEW", limit=10, object_type=MediaType.SHOW)

    assert len(page.titles) == 1
    assert page.titles[0].media_type is MediaType.SHOW
    assert page.titles[0].title == "Serie"
    assert page.titles[0].tmdb_id == 123
    assert b"on Season" in route.calls.last.request.content
