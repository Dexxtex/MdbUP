"""TheTVDB client: login, company search and bounded error handling."""

from __future__ import annotations

import httpx
import pytest
import respx

from app.integrations.tvdb.client import TVDbAuthError, TVDbClient, TVDbRequestError

BASE = "https://api4.thetvdb.com/v4"


def _client() -> TVDbClient:
    return TVDbClient("test-key", base_url=BASE, max_retries=1)


@respx.mock
def test_login_and_company_name_search() -> None:
    respx.post(f"{BASE}/login").mock(
        return_value=httpx.Response(200, json={"status": "success", "data": {"token": "jwt"}})
    )
    search = respx.get(f"{BASE}/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "success",
                "data": [
                    {"id": "company-1", "name": "Netflix", "company_type": "Network"},
                    {"id": "company-2", "name": "Netflix", "company_type": "Network"},
                ],
            },
        )
    )
    client = _client()
    try:
        companies = client.search_companies("netflix")
    finally:
        client.close()
    assert [(item.company_id, item.name) for item in companies] == [
        ("1", "Netflix"),
        ("2", "Netflix"),
    ]
    assert search.call_count == 1
    params = search.calls[0].request.url.params
    assert params["query"] == "netflix"
    assert params["type"] == "company"


@respx.mock
def test_search_accepts_dict_shaped_data() -> None:
    respx.post(f"{BASE}/login").mock(
        return_value=httpx.Response(200, json={"status": "success", "data": {"token": "jwt"}})
    )
    respx.get(f"{BASE}/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "success",
                "data": {"items": [{"id": "company-9", "name": "Example"}]},
            },
        )
    )
    client = _client()
    try:
        companies = client.search_companies("example")
    finally:
        client.close()
    assert [(item.company_id, item.name) for item in companies] == [("9", "Example")]


@respx.mock
def test_short_company_query_does_not_call_tvdb() -> None:
    search = respx.get(f"{BASE}/search").mock(return_value=httpx.Response(500))
    client = _client()
    try:
        assert client.search_companies(" ") == []
    finally:
        client.close()
    assert search.call_count == 0


@respx.mock
def test_auth_error_is_not_retried() -> None:
    respx.post(f"{BASE}/login").mock(return_value=httpx.Response(401))
    client = _client()
    with pytest.raises(TVDbAuthError):
        client.search_companies("netflix")
    client.close()


@respx.mock
def test_non_json_payload_is_reported() -> None:
    respx.post(f"{BASE}/login").mock(return_value=httpx.Response(200, text="not-json"))
    client = _client()
    with pytest.raises(TVDbRequestError):
        client.search_companies("netflix")
    client.close()
