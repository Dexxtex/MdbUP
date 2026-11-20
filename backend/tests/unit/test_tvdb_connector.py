"""TheTVDB connector is metadata-only and never fabricates availability."""

from __future__ import annotations

import pytest

from app.connectors.base import NotSupportedError
from app.connectors.tvdb.connector import TVDbConnector
from app.integrations.tvdb.client import TVDbAuthError


class _Client:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.closed = False

    def healthcheck(self) -> None:
        if self.error:
            raise self.error

    def close(self) -> None:
        self.closed = True


def test_connector_healthcheck_and_no_country_providers() -> None:
    client = _Client()
    connector = TVDbConnector(client)  # type: ignore[arg-type]
    assert connector.list_providers("IT") == ()
    assert connector.healthcheck().ok is True
    connector.close()
    assert client.closed is True


def test_connector_reports_auth_error_and_rejects_collections() -> None:
    connector = TVDbConnector(_Client(TVDbAuthError("bad key")))  # type: ignore[arg-type]
    health = connector.healthcheck()
    assert health.ok is False
    assert "bad key" in health.message
    with pytest.raises(NotSupportedError):
        connector.list_collections("IT")
