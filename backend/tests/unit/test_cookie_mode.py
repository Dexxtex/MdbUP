"""LAN vs HTTPS cookie naming and Secure flag."""

from __future__ import annotations

from app.core.config import Settings
from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD, BOOTSTRAP_TOKEN


def test_lan_mode_strips_host_prefix_and_does_not_force_secure() -> None:
    settings = Settings(
        app_base_url="http://192.0.2.10:8088",
        cookie_secure=False,
        session_cookie_name="__Host-mdbsync-session",
        csrf_cookie_name="__Host-mdbsync-csrf",
    )
    assert settings.session_cookie == "mdbsync-session"
    assert settings.csrf_cookie == "mdbsync-csrf"


def test_https_mode_forces_host_prefix() -> None:
    settings = Settings(
        app_base_url="https://mdbup.example.com",
        cookie_secure=True,
        session_cookie_name="mdbsync-session",
        csrf_cookie_name="mdbsync-csrf",
    )
    assert settings.session_cookie == "__Host-mdbsync-session"
    assert settings.csrf_cookie == "__Host-mdbsync-csrf"


def test_https_login_sets_host_prefixed_secure_cookies(client, app_settings) -> None:
    app_settings.cookie_secure = True
    app_settings.app_base_url = "https://mdbup.example.com"
    bootstrap = client.post(
        "/api/auth/bootstrap",
        json={"token": BOOTSTRAP_TOKEN, "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert bootstrap.status_code == 201
    login = client.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert login.status_code == 200
    cookies = " ".join(login.headers.get_list("set-cookie"))
    assert "__Host-mdbsync-session=" in cookies
    assert "__Host-mdbsync-csrf=" in cookies
    assert "Secure" in cookies
    # A Secure cookie is not sent over the TestClient's plain HTTP transport.
    assert client.get("/api/auth/session").status_code == 401
