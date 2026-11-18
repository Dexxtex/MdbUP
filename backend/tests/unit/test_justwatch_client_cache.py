"""JustWatch client: response cache, cache counters and schema drift detection."""

from __future__ import annotations

import httpx
import pytest
import respx

from app.core.metrics import api_usage_snapshot, reset_api_usage
from app.integrations.justwatch.client import (
    SCHEMA_DRIFT_CODE,
    JustWatchClient,
    JustWatchGraphQLError,
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
        max_retries=1,
        **kwargs,
    )


def _connection(total: int = 1, *, has_next: bool = False) -> dict:
    return {
        "popularTitles": {
            "totalCount": total,
            "pageInfo": {"hasNextPage": has_next, "endCursor": "MTAw"},
            "edges": [
                {
                    "node": {
                        "id": "tm10",
                        "objectType": "MOVIE",
                        "content": {
                            "title": "Matrix",
                            "originalReleaseYear": 1999,
                            "externalIds": {"imdbId": "tt0133093", "tmdbId": "603"},
                        },
                        "offers": [
                            {
                                "monetizationType": "FLATRATE",
                                "package": {"clearName": "Netflix", "shortName": "nfx"},
                            }
                        ],
                    }
                }
            ],
        }
    }


@respx.mock
def test_repeated_query_is_served_from_cache_with_a_deep_copy() -> None:
    route = respx.post(BASE).mock(return_value=httpx.Response(200, json={"data": _connection()}))
    client = _client()
    first = client.popular_titles("IT", "it", limit=1)
    assert route.call_count == 1

    # The caller mutating the payload must not poison the cached copy.
    first.raw["edges"].clear()

    cached = client.popular_titles("IT", "it", limit=1)
    assert route.call_count == 1
    assert len(cached.titles) == 1


@respx.mock
def test_cache_can_be_disabled() -> None:
    route = respx.post(BASE).mock(return_value=httpx.Response(200, json={"data": _connection()}))
    client = _client(cache_ttl_seconds=0)
    client.popular_titles("IT", "it", limit=1)
    client.popular_titles("IT", "it", limit=1)
    assert route.call_count == 2


@respx.mock
def test_errors_are_never_cached() -> None:
    route = respx.post(BASE).mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(200, json={"data": _connection()}),
        ]
    )
    client = _client()
    with pytest.raises(JustWatchRequestError):
        client.popular_titles("IT", "it", limit=1)
    page = client.popular_titles("IT", "it", limit=1)
    assert len(page.titles) == 1
    assert route.call_count == 2


@respx.mock
def test_healthcheck_is_never_cached() -> None:
    route = respx.post(BASE).mock(
        return_value=httpx.Response(200, json={"data": {"__typename": "Query"}})
    )
    client = _client()
    assert client.healthcheck().ok is True
    assert client.healthcheck().ok is True
    assert route.call_count == 2
    assert len(client.cache) == 0


@respx.mock
def test_missing_root_field_is_schema_drift() -> None:
    respx.post(BASE).mock(return_value=httpx.Response(200, json={"data": {"other": {}}}))
    with pytest.raises(JustWatchGraphQLError) as excinfo:
        _client().popular_titles("IT", "it", limit=1)
    assert excinfo.value.code == SCHEMA_DRIFT_CODE
    assert "popularTitles" in str(excinfo.value)


@respx.mock
def test_connection_without_page_info_is_schema_drift() -> None:
    respx.post(BASE).mock(
        return_value=httpx.Response(
            200, json={"data": {"popularTitles": {"totalCount": 1, "edges": []}}}
        )
    )
    with pytest.raises(JustWatchGraphQLError, match="pageInfo"):
        _client().popular_titles("IT", "it", limit=1)


@respx.mock
def test_edges_not_a_list_is_schema_drift() -> None:
    respx.post(BASE).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "popularTitles": {
                        "totalCount": 1,
                        "pageInfo": {"hasNextPage": False},
                        "edges": {"node": []},
                    }
                }
            },
        )
    )
    with pytest.raises(JustWatchGraphQLError, match="edges"):
        _client().popular_titles("IT", "it", limit=1)


@respx.mock
def test_drifted_payload_is_not_cached() -> None:
    route = respx.post(BASE).mock(
        side_effect=[
            httpx.Response(200, json={"data": {"other": {}}}),
            httpx.Response(200, json={"data": _connection()}),
        ]
    )
    client = _client()
    with pytest.raises(JustWatchGraphQLError):
        client.popular_titles("IT", "it", limit=1)
    page = client.popular_titles("IT", "it", limit=1)
    assert len(page.titles) == 1
    assert route.call_count == 2


@respx.mock
def test_cache_hits_and_misses_reach_the_usage_snapshot() -> None:
    reset_api_usage()
    respx.post(BASE).mock(return_value=httpx.Response(200, json={"data": _connection()}))
    client = _client()
    client.popular_titles("IT", "it", limit=1)
    client.popular_titles("IT", "it", limit=1)
    usage = api_usage_snapshot()["justwatch"]
    assert usage["today"] == 1  # only the real HTTP call is an API call
    assert usage["cache_misses"] == 1
    assert usage["cache_hits"] == 1
    reset_api_usage()
