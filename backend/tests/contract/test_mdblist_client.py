"""MDBList client contract tests with respx (no live network)."""

from __future__ import annotations

import httpx
import pytest
import respx

from app.integrations.mdblist.client import (
    MdbListAuthError,
    MdbListClient,
    MdbListNotFoundError,
    MdbListPermissionError,
    MdbListRateLimitError,
    MdbListSchemaError,
    MdbListServerError,
    MdbListTimeout,
)
from app.integrations.mdblist.models import MdbListId
from app.services.reconciliation import read_all_remote_items

BASE = "https://api.mdblist.com"


def _client(**kwargs: object) -> MdbListClient:
    return MdbListClient(
        "test-key",
        base_url=BASE,
        sleep=lambda _seconds: None,
        backoff_base_seconds=0,
        backoff_max_seconds=0,
        jitter_ratio=0,
        **kwargs,
    )


@respx.mock
def test_get_items_follows_cursor_and_parses_ids() -> None:
    first = respx.get(f"{BASE}/lists/42/items").mock(
        side_effect=[
            httpx.Response(
                200,
                headers={"X-Has-More": "true"},
                json={
                    "movies": [
                        {
                            "id": 603,
                            "rank": 1,
                            "title": "Matrix",
                            "imdb_id": "tt0133093",
                            "ids": {"tmdb": 603, "imdb": "tt0133093", "mdblist": "m603"},
                            "mediatype": "movie",
                        }
                    ],
                    "shows": [],
                    "pagination": {"next_cursor": "cursor-2"},
                },
            ),
            httpx.Response(
                200,
                headers={"X-Has-More": "false"},
                json={
                    "movies": [],
                    "shows": [
                        {
                            "id": 1396,
                            "title": "Breaking Bad",
                            "ids": {"tmdb": 1396, "imdb": "tt0903747"},
                            "mediatype": "show",
                        }
                    ],
                    "pagination": {},
                },
            ),
        ]
    )
    client = _client()
    page = client.get_items(42, limit=100)
    assert page.has_more is True
    assert page.next_cursor == "cursor-2"
    assert page.items[0].tmdb_id == 603
    assert page.items[0].mediatype == "MOVIE"
    assert page.items[0].imdb_id == "tt0133093"

    second = client.get_items(42, cursor=page.next_cursor, limit=100)
    assert second.has_more is False
    assert second.items[0].mediatype == "SHOW"
    assert second.items[0].tmdb_id == 1396

    first_request = first.calls[0].request
    assert first_request.url.params["apikey"] == "test-key"
    assert first_request.url.params["limit"] == "100"
    assert "cursor" not in first_request.url.params
    second_request = first.calls[1].request
    assert second_request.url.params["cursor"] == "cursor-2"
    client.close()


@respx.mock
def test_iter_items_reads_every_page() -> None:
    respx.get(f"{BASE}/lists/7/items").mock(
        side_effect=[
            httpx.Response(
                200,
                headers={"X-Has-More": "true"},
                json={
                    "movies": [{"ids": {"tmdb": 1}}],
                    "pagination": {"next_cursor": "c2"},
                },
            ),
            httpx.Response(
                200,
                headers={"X-Has-More": "false"},
                json={"movies": [{"ids": {"tmdb": 2}}], "pagination": {}},
            ),
        ]
    )
    client = _client()
    items = list(client.iter_items(7))
    assert [item.tmdb_id for item in items] == [1, 2]
    client.close()


@respx.mock
def test_has_more_without_cursor_is_a_schema_error() -> None:
    respx.get(f"{BASE}/lists/7/items").mock(
        return_value=httpx.Response(
            200, headers={"X-Has-More": "true"}, json={"movies": [], "pagination": {}}
        )
    )
    client = _client()
    with pytest.raises(MdbListSchemaError):
        client.get_items(7)
    client.close()


@respx.mock
def test_add_items_sends_documented_payload_and_parses_counters() -> None:
    route = respx.post(f"{BASE}/lists/42/items/add").mock(
        return_value=httpx.Response(
            200,
            json={
                "added": {"movies": 1, "shows": 1},
                "removed": {"movies": 0, "shows": 0},
                "existing": {"movies": 1, "shows": 0},
                "not_found": {"movies": 0, "shows": 1},
            },
        )
    )
    client = _client()
    result = client.add_items(
        42,
        movies=[MdbListId(tmdb=603, imdb="tt0133093")],
        shows=[MdbListId(tmdb=1396)],
    )
    assert result.added_total == 2
    assert result.existing_total == 1
    assert result.not_found_total == 1
    body = route.calls.last.request.read().decode()
    assert '"tmdb":603' in body
    assert '"imdb":"tt0133093"' in body
    assert route.calls.last.request.url.params["apikey"] == "test-key"
    client.close()


@respx.mock
def test_remove_items_uses_remove_endpoint() -> None:
    route = respx.post(f"{BASE}/lists/42/items/remove").mock(
        return_value=httpx.Response(200, json={"removed": {"movies": 1}})
    )
    client = _client()
    result = client.remove_items(42, movies=[MdbListId(tmdb=603)])
    assert result.removed_total == 1
    assert route.called
    client.close()


@respx.mock
def test_reorder_sends_items_and_position() -> None:
    route = respx.post(f"{BASE}/lists/42/items/reorder").mock(
        return_value=httpx.Response(200, json={"updated": 2, "not_found": 0})
    )
    client = _client()
    result = client.reorder(
        42,
        [("MOVIE", MdbListId(tmdb=603)), ("MOVIE", MdbListId(tmdb=238))],
        position="top",
    )
    assert result.updated == 2
    body = route.calls.last.request.read().decode()
    assert '"mediatype":"movie"' in body
    assert '"position":"top"' in body
    client.close()


@respx.mock
def test_reorder_uses_after_for_following_chunks() -> None:
    route = respx.post(f"{BASE}/lists/42/items/reorder").mock(
        return_value=httpx.Response(200, json={"updated": 1, "not_found": 0})
    )
    client = _client()
    client.reorder(
        42,
        [("SHOW", MdbListId(tmdb=1396))],
        after=("MOVIE", MdbListId(tmdb=603)),
    )
    body = route.calls.last.request.read().decode()
    assert '"after"' in body
    assert '"mediatype":"movie"' in body
    client.close()


@respx.mock
def test_read_rate_limit_exposes_retry_after() -> None:
    respx.get(f"{BASE}/lists/42/items").mock(
        return_value=httpx.Response(429, headers={"Retry-After": "30"})
    )
    client = _client()
    with pytest.raises(MdbListRateLimitError) as excinfo:
        client.get_items(42)
    assert excinfo.value.retry_after_seconds == 30.0
    client.close()


@respx.mock
def test_write_rate_limit_never_retries() -> None:
    route = respx.post(f"{BASE}/lists/42/items/add").mock(
        return_value=httpx.Response(429, headers={"Retry-After": "30"})
    )
    client = _client()
    with pytest.raises(MdbListRateLimitError):
        client.add_items(42, movies=[MdbListId(tmdb=603)])
    assert route.call_count == 1
    client.close()


@respx.mock
def test_permission_and_auth_and_not_found_errors() -> None:
    client = _client()
    respx.get(f"{BASE}/lists/1").mock(return_value=httpx.Response(403))
    with pytest.raises(MdbListPermissionError):
        client.get_list(1)
    respx.get(f"{BASE}/lists/2").mock(return_value=httpx.Response(401))
    with pytest.raises(MdbListAuthError):
        client.get_list(2)
    respx.get(f"{BASE}/lists/3").mock(return_value=httpx.Response(404))
    with pytest.raises(MdbListNotFoundError):
        client.get_list(3)
    client.close()


@respx.mock
def test_get_items_supports_live_offset_pagination() -> None:
    route = respx.get(f"{BASE}/lists/7/items").mock(
        return_value=httpx.Response(
            200,
            headers={"x-has-more": "true"},
            json={
                "movies": [
                    {
                        "id": 1,
                        "title": "Film",
                        "ids": {"tmdb": 1, "imdb": "tt1"},
                    }
                ],
                "shows": [],
                "seasons": [],
                "episodes": [],
                "pagination": {"offset": 0, "limit": 100, "total": 150, "has_more": True},
            },
        )
    )
    client = _client()
    page = client.get_items(7, offset=0, limit=100)
    assert page.has_more is True
    assert page.next_cursor == "100"
    assert route.calls.last.request.url.params["offset"] == "0"
    client.close()


@respx.mock
def test_read_all_remote_items_follows_offset_pages() -> None:
    route = respx.get(f"{BASE}/lists/7/items").mock(
        side_effect=[
            httpx.Response(
                200,
                headers={"x-has-more": "true"},
                json={
                    "movies": [
                        {"id": 1, "title": "A", "ids": {"tmdb": 1}},
                        {"id": 2, "title": "B", "ids": {"tmdb": 2}},
                    ],
                    "shows": [],
                    "seasons": [],
                    "episodes": [],
                    "pagination": {"offset": 0, "limit": 2, "total": 3, "has_more": True},
                },
            ),
            httpx.Response(
                200,
                headers={"x-has-more": "false"},
                json={
                    "movies": [{"id": 3, "title": "C", "ids": {"tmdb": 3}}],
                    "shows": [],
                    "seasons": [],
                    "episodes": [],
                    "pagination": {"offset": 2, "limit": 2, "total": 3, "has_more": False},
                },
            ),
        ]
    )
    client = _client()
    remote = read_all_remote_items(client, 7, page_size=2)
    assert [item.tmdb_id for item in remote.items] == [1, 2, 3]
    assert remote.pages == 2
    assert route.call_count == 2
    assert route.calls[1].request.url.params["offset"] == "2"
    client.close()


@respx.mock
def test_timeout_is_typed() -> None:
    respx.post(f"{BASE}/lists/42/items/add").mock(side_effect=httpx.ReadTimeout("boom"))
    client = _client()
    with pytest.raises(MdbListTimeout):
        client.add_items(42, movies=[MdbListId(tmdb=603)])
    client.close()


@respx.mock
def test_create_list_and_get_user() -> None:
    respx.post(f"{BASE}/lists/user/add").mock(
        return_value=httpx.Response(200, json={"id": 99, "name": "Test", "slug": "test"})
    )
    respx.get(f"{BASE}/user").mock(
        return_value=httpx.Response(200, json={"id": 5, "user_name": "owner"})
    )
    client = _client()
    created = client.create_list("Test", private=True)
    assert created.id == 99
    assert created.slug == "test"
    user = client.get_user()
    assert user.id == 5
    assert user.user_name == "owner"
    client.close()


@respx.mock
def test_get_list_accepts_live_array_shape() -> None:
    respx.get(f"{BASE}/lists/43").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": 43,
                    "name": "Netflix IT — Film Azione",
                    "slug": "netflix-it-film-azione",
                    "private": False,
                    "mediatype": None,
                    "user_id": 5,
                    "user_name": "owner",
                    "items": 0,
                }
            ],
        )
    )
    client = _client()
    remote = client.get_list(43)
    assert remote.id == 43
    assert remote.slug == "netflix-it-film-azione"
    assert remote.item_count == 0
    client.close()


@respx.mock
def test_get_list_parses_ownership_metadata() -> None:
    respx.get(f"{BASE}/lists/42").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": 42,
                "name": "Netflix IT",
                "slug": "netflix-it",
                "private": True,
                "mediatype": "movie",
                "user_id": 5,
                "user_name": "owner",
                "items": 12,
            },
        )
    )
    client = _client()
    remote = client.get_list(42)
    assert remote.id == 42
    assert remote.private is True
    assert remote.mediatype == "MOVIE"
    assert remote.user_id == 5
    assert remote.item_count == 12
    client.close()


@respx.mock
def test_read_5xx_is_retried_then_succeeds() -> None:
    route = respx.get(f"{BASE}/lists/42/items").mock(
        side_effect=[
            httpx.Response(500),
            httpx.Response(
                200,
                headers={"X-Has-More": "false"},
                json={"movies": [], "shows": [], "pagination": {"has_more": False}},
            ),
        ]
    )
    client = _client(max_retries=3)
    page = client.get_items(42)
    assert page.items == ()
    assert route.call_count == 2
    client.close()


@respx.mock
def test_read_timeout_is_retried_then_succeeds() -> None:
    route = respx.get(f"{BASE}/lists/42/items").mock(
        side_effect=[
            httpx.ReadTimeout("slow"),
            httpx.Response(
                200,
                headers={"X-Has-More": "false"},
                json={"movies": [], "shows": [], "pagination": {"has_more": False}},
            ),
        ]
    )
    client = _client(max_retries=3)
    page = client.get_items(42)
    assert page.items == ()
    assert route.call_count == 2
    client.close()


@respx.mock
def test_write_5xx_is_not_retried_blindly() -> None:
    route = respx.post(f"{BASE}/lists/42/items/add").mock(return_value=httpx.Response(500))
    client = _client(max_retries=3)
    with pytest.raises(MdbListServerError):
        client.add_items(42, movies=[MdbListId(tmdb=603)])
    assert route.call_count == 1
    client.close()


@respx.mock
def test_update_list_metadata_uses_put() -> None:
    route = respx.put(f"{BASE}/lists/42").mock(
        return_value=httpx.Response(
            200, json={"success": True, "id": 42, "name": "Renamed", "private": True}
        )
    )
    client = _client()
    updated = client.update_list(42, name="Renamed", private=True)
    assert updated.id == 42
    assert updated.name == "Renamed"
    assert updated.private is True
    body = route.calls.last.request.read().decode()
    assert '"name":"Renamed"' in body
    assert '"private":true' in body
    client.close()
