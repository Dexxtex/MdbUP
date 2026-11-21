"""Client IP extraction: trust X-Forwarded-For only from configured proxies."""

from __future__ import annotations

from starlette.requests import Request

from app.api.deps import get_client_ip
from app.core.config import Settings


def _request(peer: str, forwarded: str | None = None) -> Request:
    headers = [(b"x-forwarded-for", forwarded.encode())] if forwarded else []
    return Request({"type": "http", "client": (peer, 1234), "headers": headers})


def test_direct_client_cannot_spoof_forwarded_for() -> None:
    settings = Settings(trusted_proxies="")
    request = _request("203.0.113.9", "198.51.100.7")

    assert get_client_ip(request, settings) == "203.0.113.9"


def test_trusted_proxy_uses_last_forwarded_hop() -> None:
    settings = Settings(trusted_proxies="10.0.0.2, 10.0.0.3")
    request = _request("10.0.0.2", "198.51.100.7, 203.0.113.9")

    assert get_client_ip(request, settings) == "203.0.113.9"


def test_empty_pointer_keeps_peer_when_no_forwarded_header() -> None:
    settings = Settings(trusted_proxies="10.0.0.2")
    request = Request({"type": "http", "client": None, "headers": []})

    assert get_client_ip(request, settings) == "unknown"
