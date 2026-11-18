"""TMDb client contract tests with respx (no live network)."""

from __future__ import annotations

import httpx
import pytest
import respx

from app.domain.enums import MediaType
from app.integrations.tmdb.client import (
    TMDbAuthError,
    TMDbClient,
    TMDbNotFoundError,
    TMDbRateLimitError,
    TMDbRequestError,
    tmdb_auth_mode,
)

BASE = "https://api.themoviedb.org/3"


def _client(**kwargs: object) -> TMDbClient:
    return TMDbClient(
        "a.b.c",
        base_url=BASE,
        sleep=lambda _seconds: None,
        backoff_base_seconds=0,
        backoff_max_seconds=0,
        jitter_ratio=0,
        **kwargs,
    )


@respx.mock
def test_watch_providers_sends_region_and_language() -> None:
    route = respx.get(f"{BASE}/watch/providers/movie").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {
                        "provider_id": 8,
                        "provider_name": "Netflix",
                        "display_priority": 1,
                        "logo_path": "/logo.png",
                    }
                ]
            },
        )
    )
    client = _client()
    providers = client.list_movie_providers("IT")
    params = route.calls.last.request.url.params
    assert params["watch_region"] == "IT"
    assert params["language"] == "it-IT"
    assert providers[0].provider_id == 8
    assert providers[0].name == "Netflix"
    assert route.calls.last.request.headers["Authorization"] == "Bearer a.b.c"
    assert "api_key" not in route.calls.last.request.url.params
    client.close()


@respx.mock
def test_tmdb_auth_mode_detects_v3_and_v4() -> None:
    assert tmdb_auth_mode("0123456789abcdef0123456789abcdef") == "query"
    assert tmdb_auth_mode("a.b.c") == "bearer"


@respx.mock
def test_v3_api_key_uses_query_parameter() -> None:
    route = respx.get(f"{BASE}/watch/providers/movie").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    client = TMDbClient("0123456789abcdef0123456789abcdef", base_url=BASE)
    client.list_movie_providers("IT")
    request = route.calls.last.request
    assert request.url.params["api_key"] == "0123456789abcdef0123456789abcdef"
    assert "Authorization" not in request.headers
    client.close()


@respx.mock
def test_discover_movies_parses_page_and_items() -> None:
    respx.get(f"{BASE}/discover/movie").mock(
        return_value=httpx.Response(
            200,
            json={
                "page": 2,
                "total_pages": 5,
                "total_results": 100,
                "results": [
                    {
                        "id": 603,
                        "title": "Matrix",
                        "original_title": "The Matrix",
                        "release_date": "1999-03-31",
                        "popularity": 42.0,
                        "overview": "Neo...",
                    }
                ],
            },
        )
    )
    client = _client()
    page = client.discover_movies(8, "IT", 2)
    assert page.page == 2
    assert page.total_pages == 5
    assert page.total_results == 100
    assert page.items[0].tmdb_id == 603
    assert page.items[0].release_year == 1999
    assert page.items[0].media_type is MediaType.MOVIE
    client.close()


@respx.mock
def test_discover_tv_uses_name_and_first_air_date() -> None:
    respx.get(f"{BASE}/discover/tv").mock(
        return_value=httpx.Response(
            200,
            json={
                "page": 1,
                "total_pages": 1,
                "total_results": 1,
                "results": [
                    {
                        "id": 1399,
                        "name": "Il Trono di Spade",
                        "original_name": "Game of Thrones",
                        "first_air_date": "2011-04-17",
                    }
                ],
            },
        )
    )
    client = _client()
    page = client.discover_tv(8, "IT", 1)
    assert page.items[0].title == "Il Trono di Spade"
    assert page.items[0].release_year == 2011
    assert page.items[0].media_type is MediaType.SHOW
    client.close()


@respx.mock
def test_rate_limit_is_retried_once_when_wait_is_short() -> None:
    route = respx.get(f"{BASE}/discover/movie").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "0"}),
            httpx.Response(
                200,
                json={"page": 1, "total_pages": 1, "total_results": 0, "results": []},
            ),
        ]
    )
    client = _client()
    page = client.discover_movies(8, "IT", 1)
    assert route.call_count == 2
    assert page.items == ()
    client.close()


@respx.mock
def test_rate_limit_with_long_wait_raises_without_retry() -> None:
    route = respx.get(f"{BASE}/discover/movie").mock(
        return_value=httpx.Response(429, headers={"Retry-After": "60"})
    )
    client = _client()
    with pytest.raises(TMDbRateLimitError) as excinfo:
        client.discover_movies(8, "IT", 1)
    assert excinfo.value.retry_after_seconds == 60.0
    assert route.call_count == 1
    client.close()


@respx.mock
def test_auth_error_is_not_retried() -> None:
    route = respx.get(f"{BASE}/configuration").mock(
        return_value=httpx.Response(401, json={"status_message": "Invalid API key"})
    )
    client = _client()
    with pytest.raises(TMDbAuthError):
        client._get("/configuration")
    assert route.call_count == 1
    client.close()


@respx.mock
def test_healthcheck_reports_failure_without_raising() -> None:
    respx.get(f"{BASE}/configuration").mock(return_value=httpx.Response(500))
    client = _client()
    health = client.healthcheck()
    assert health.ok is False
    assert health.latency_ms is not None
    client.close()


@respx.mock
def test_healthcheck_ok() -> None:
    respx.get(f"{BASE}/configuration").mock(return_value=httpx.Response(200, json={"images": {}}))
    client = _client()
    health = client.healthcheck()
    assert health.ok is True
    client.close()


@respx.mock
def test_external_ids_and_find() -> None:
    respx.get(f"{BASE}/movie/603/external_ids").mock(
        return_value=httpx.Response(200, json={"id": 603, "imdb_id": "tt0133093"})
    )
    respx.get(f"{BASE}/find/tt0903747").mock(
        return_value=httpx.Response(
            200,
            json={"movie_results": [], "tv_results": [{"id": 1396}]},
        )
    )
    client = _client()
    external = client.external_ids(MediaType.MOVIE, 603)
    assert external.imdb_id == "tt0133093"
    assert client.find_by_imdb("tt0903747", MediaType.SHOW) == 1396
    assert client.find_by_imdb("tt0903747", MediaType.MOVIE) is None
    client.close()


@respx.mock
def test_not_found_maps_to_dedicated_error() -> None:
    respx.get(f"{BASE}/movie/999/external_ids").mock(return_value=httpx.Response(404))
    client = _client()
    with pytest.raises(TMDbNotFoundError):
        client.external_ids(MediaType.MOVIE, 999)
    client.close()


@respx.mock
def test_network_error_maps_to_request_error() -> None:
    respx.get(f"{BASE}/configuration").mock(side_effect=httpx.ConnectError("no route"))
    client = _client()
    with pytest.raises(TMDbRequestError):
        client._get("/configuration")
    client.close()


@respx.mock
def test_5xx_is_retried_then_succeeds() -> None:
    route = respx.get(f"{BASE}/configuration").mock(
        side_effect=[
            httpx.Response(500),
            httpx.Response(200, json={"images": {}}),
        ]
    )
    client = _client(max_retries=3)
    assert client._get("/configuration") == {"images": {}}
    assert route.call_count == 2
    client.close()


@respx.mock
def test_5xx_exhausts_bounded_retries() -> None:
    route = respx.get(f"{BASE}/configuration").mock(return_value=httpx.Response(503))
    client = _client(max_retries=3)
    with pytest.raises(TMDbRequestError):
        client._get("/configuration")
    assert route.call_count == 3
    client.close()


@respx.mock
def test_timeout_is_retried_then_succeeds() -> None:
    route = respx.get(f"{BASE}/configuration").mock(
        side_effect=[
            httpx.ReadTimeout("slow"),
            httpx.Response(200, json={"images": {}}),
        ]
    )
    client = _client(max_retries=3)
    assert client._get("/configuration") == {"images": {}}
    assert route.call_count == 2
    client.close()


@respx.mock
def test_tv_details_parses_season_counts() -> None:
    respx.get(f"{BASE}/tv/1399").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": 1399,
                "name": "Il Trono di Spade",
                "number_of_seasons": 8,
                "number_of_episodes": 73,
                "seasons": [
                    {"season_number": 1, "name": "Stagione 1", "episode_count": 10},
                    {"season_number": 2, "name": "Stagione 2", "episode_count": 10},
                ],
            },
        )
    )
    client = _client()
    details = client.tv_details(1399)
    assert details.tmdb_id == 1399
    assert details.number_of_seasons == 8
    assert details.number_of_episodes == 73
    assert [season.season_number for season in details.seasons] == [1, 2]
    assert details.seasons[0].episode_count == 10
    client.close()
