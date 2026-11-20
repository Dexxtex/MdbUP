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
def test_login_and_streaming_company_search() -> None:
    respx.post(f"{BASE}/login").mock(
        return_value=httpx.Response(200, json={"status": "success", "data": {"token": "jwt"}})
    )
    search = respx.get(f"{BASE}/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "success",
                "data": {
                    "items": [
                        {"id": "1", "name": "Netflix", "company_type": "SVOD"},
                        {"id": "2", "name": "Netflix", "company_type": "SVOD"},
                    ]
                },
            },
        )
    )
    client = _client()
    try:
        companies = client.list_streaming_companies()
    finally:
        client.close()
    assert [(item.company_id, item.name) for item in companies] == [
        ("1", "Netflix"),
        ("2", "Netflix"),
    ]
    assert search.call_count == 3


@respx.mock
def test_auth_error_is_not_retried() -> None:
    respx.post(f"{BASE}/login").mock(return_value=httpx.Response(401))
    client = _client()
    with pytest.raises(TVDbAuthError):
        client.list_streaming_companies()
    client.close()


@respx.mock
def test_non_json_payload_is_reported() -> None:
    respx.post(f"{BASE}/login").mock(return_value=httpx.Response(200, text="not-json"))
    client = _client()
    with pytest.raises(TVDbRequestError):
        client.list_streaming_companies()
    client.close()
