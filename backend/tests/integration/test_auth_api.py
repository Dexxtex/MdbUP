"""Auth flow: bootstrap once, login, session, CSRF, logout, rate limit."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD, BOOTSTRAP_TOKEN


def _bootstrap(client: TestClient, token: str = BOOTSTRAP_TOKEN):
    return client.post(
        "/api/auth/bootstrap",
        json={"token": token, "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )


def test_bootstrap_rejects_wrong_token(client: TestClient) -> None:
    response = _bootstrap(client, token="wrong-token")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "AUTH_INVALID_BOOTSTRAP_TOKEN"


def test_bootstrap_creates_admin_only_once(client: TestClient) -> None:
    first = _bootstrap(client)
    second = _bootstrap(client)

    assert first.status_code == 201
    assert first.json()["user"]["email"] == ADMIN_EMAIL
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "AUTH_ALREADY_BOOTSTRAPPED"


def test_bootstrap_rejects_weak_password(client: TestClient) -> None:
    response = client.post(
        "/api/auth/bootstrap",
        json={"token": BOOTSTRAP_TOKEN, "email": ADMIN_EMAIL, "password": "short"},
    )

    assert response.status_code == 422


def test_login_sets_cookies_and_session_returns_user(client: TestClient) -> None:
    _bootstrap(client)

    login = client.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})

    assert login.status_code == 200
    body = login.json()
    assert body["user"]["email"] == ADMIN_EMAIL
    assert body["csrf_token"]
    set_cookie = " ".join(login.headers.get_list("set-cookie"))
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie

    session = client.get("/api/auth/session")
    assert session.status_code == 200
    assert session.json()["user"]["email"] == ADMIN_EMAIL
    assert session.json()["csrf_token"] == body["csrf_token"]


def test_login_rejects_bad_password_generically(client: TestClient) -> None:
    _bootstrap(client)

    response = client.post(
        "/api/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong-password"}
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_INVALID_CREDENTIALS"
    assert response.json()["error"]["message"] == "Credenziali non valide."


def test_session_rotates_missing_csrf_cookie(client: TestClient, app_settings) -> None:
    _bootstrap(client)
    login = client.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert login.status_code == 200
    client.cookies.set(app_settings.csrf_cookie, "stale-token")

    session = client.get("/api/auth/session")

    assert session.status_code == 200
    assert session.json()["csrf_token"] != "stale-token"
    assert app_settings.csrf_cookie in " ".join(session.headers.get_list("set-cookie"))


def test_session_requires_cookie(client: TestClient) -> None:
    response = client.get("/api/auth/session")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_UNAUTHENTICATED"


def test_login_is_rate_limited(client: TestClient) -> None:
    _bootstrap(client)

    statuses = [
        client.post(
            "/api/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong-password"}
        ).status_code
        for _ in range(6)
    ]

    assert statuses[:5] == [401] * 5
    assert statuses[5] == 429
    assert (
        client.post(
            "/api/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong-password"}
        ).json()["error"]["code"]
        == "AUTH_RATE_LIMITED"
    )


def test_mutations_require_csrf(client: TestClient, admin: dict[str, str]) -> None:
    missing = client.patch("/api/settings", json={"items": {"sync_batch_size": 50}})
    assert missing.status_code == 403
    assert missing.json()["error"]["code"] == "AUTH_CSRF_INVALID"

    accepted = client.patch("/api/settings", json={"items": {"sync_batch_size": 50}}, headers=admin)
    assert accepted.status_code == 200


def test_csrf_rejects_mismatched_header(client: TestClient, admin: dict[str, str]) -> None:
    response = client.patch(
        "/api/settings",
        json={"items": {"sync_batch_size": 50}},
        headers={"X-CSRF-Token": "forged-token"},
    )

    assert response.status_code == 403


def test_csrf_rejects_foreign_origin(client: TestClient, admin: dict[str, str]) -> None:
    response = client.patch(
        "/api/settings",
        json={"items": {"sync_batch_size": 50}},
        headers={**admin, "Origin": "https://attacker.example"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "AUTH_ORIGIN_REJECTED"


def test_logout_revokes_session(client: TestClient, admin: dict[str, str]) -> None:
    logout = client.post("/api/auth/logout", headers=admin)

    assert logout.status_code == 204
    assert client.get("/api/auth/session").status_code == 401


def test_bootstrap_disabled_without_token(client: TestClient, app_settings) -> None:
    app_settings.bootstrap_token = ""

    response = _bootstrap(client)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "AUTH_BOOTSTRAP_DISABLED"


def test_error_envelope_shape(client: TestClient) -> None:
    response = client.get("/api/does-not-exist")

    assert response.status_code == 404
    error = response.json()["error"]
    assert set(error) >= {"code", "category", "message", "retryable", "request_id", "details"}
    assert response.headers["X-Request-ID"].startswith("req_")


def test_change_password_revokes_sessions_and_accepts_new_password(
    client: TestClient, admin: dict[str, str]
) -> None:
    changed = client.post(
        "/api/auth/change-password",
        json={
            "current_password": ADMIN_PASSWORD,
            "new_password": "new correct horse battery staple",
        },
        headers=admin,
    )
    assert changed.status_code == 204
    assert client.get("/api/auth/session").status_code == 401
    login = client.post(
        "/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": "new correct horse battery staple"},
    )
    assert login.status_code == 200


def test_change_password_rejects_wrong_current_password(
    client: TestClient, admin: dict[str, str]
) -> None:
    response = client.post(
        "/api/auth/change-password",
        json={
            "current_password": "wrong password",
            "new_password": "new correct horse battery staple",
        },
        headers=admin,
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_INVALID_CREDENTIALS"


def test_csrf_rejects_malformed_origin_without_500(
    client: TestClient, admin: dict[str, str]
) -> None:
    response = client.patch(
        "/api/settings",
        json={"items": {"sync_batch_size": 50}},
        headers={**admin, "Origin": "http://app.example:bad"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "AUTH_ORIGIN_REJECTED"
