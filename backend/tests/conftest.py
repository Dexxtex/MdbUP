"""Shared fixtures for the foundation tests.

Each test gets its own SQLite database file and a freshly cached settings object,
so no state leaks between cases. Lane F extends these fixtures for the full suite.
"""

from __future__ import annotations

import base64
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

ENCRYPTION_KEY = base64.b64encode(b"0123456789abcdef0123456789abcdef").decode()
BOOTSTRAP_TOKEN = "test-bootstrap-token"
ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "correct horse battery staple"


@pytest.fixture()
def app_settings(tmp_path, monkeypatch) -> Iterator[object]:
    """Configure the environment and return the cached settings object."""
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'mdbup-test.db'}")
    monkeypatch.setenv("APP_ENCRYPTION_KEY", ENCRYPTION_KEY)
    monkeypatch.setenv("BOOTSTRAP_TOKEN", BOOTSTRAP_TOKEN)
    monkeypatch.setenv("COOKIE_SECURE", "false")
    monkeypatch.setenv("LOG_FORMAT", "console")
    monkeypatch.setenv("REDIS_URL", "")

    from app.api.deps import reset_rate_limiters
    from app.core.config import get_settings
    from app.core.metrics import reset_api_usage
    from app.db.session import reset_engine

    get_settings.cache_clear()
    reset_engine()
    reset_rate_limiters()
    reset_api_usage()
    yield get_settings()
    get_settings.cache_clear()
    reset_engine()
    reset_rate_limiters()
    reset_api_usage()


@pytest.fixture()
def db(app_settings) -> Iterator[Engine]:
    """Create the schema on a fresh SQLite database."""
    from app.db import models  # noqa: F401  (registers the tables)
    from app.db.base import Base
    from app.db.session import get_engine

    engine = get_engine()
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


@pytest.fixture()
def client(db) -> Iterator[TestClient]:
    """HTTP client bound to a freshly built application."""
    from app.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture()
def seeded(db) -> None:
    """Seed the canonical providers and the base sources."""
    from app.cli import seed_reference_data

    assert seed_reference_data() == 0


@pytest.fixture()
def admin(client) -> dict[str, str]:
    """Bootstrap the admin and log in, returning the CSRF header."""
    response = client.post(
        "/api/auth/bootstrap",
        json={"token": BOOTSTRAP_TOKEN, "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 201, response.text
    login = client.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert login.status_code == 200, login.text
    return {"X-CSRF-Token": login.json()["csrf_token"]}
