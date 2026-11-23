"""Dashboard source status must follow the stored credential, not ``Source.status``.

``Source.status`` is only rewritten by a healthcheck, so saving TMDb/TVDB
credentials used to leave the dashboard claiming the sources were
unconfigured. The read model now reconciles the column with the credential.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

TMDB_SECRET = "tmdb-dashboard-secret-123456"
TVDB_SECRET = "tvdb-dashboard-secret-123456"


def _dashboard(client: TestClient, admin: dict[str, str]) -> dict:
    response = client.get("/api/dashboard", headers=admin)
    assert response.status_code == 200, response.text
    return response.json()


def _sources_by_key(payload: dict) -> dict[str, dict]:
    return {row["key"]: row for row in payload["sources"]}


def _alert_codes(payload: dict) -> set[str]:
    return {alert["code"] for alert in payload["alerts"]}


def _save(client: TestClient, admin: dict[str, str], kind: str, secret: str) -> None:
    response = client.put(f"/api/credentials/{kind}", json={"value": secret}, headers=admin)
    assert response.status_code == 204, response.text


def test_sources_are_unconfigured_until_credentials_arrive(
    client: TestClient, admin: dict[str, str], seeded: None
) -> None:
    payload = _dashboard(client, admin)
    sources = _sources_by_key(payload)

    assert sources["tmdb"]["status"] == "UNCONFIGURED"
    assert sources["tvdb"]["status"] == "UNCONFIGURED"
    assert payload["counters"]["sources_unconfigured"] == 2
    assert "SOURCE_UNCONFIGURED" in _alert_codes(payload)


def test_saved_credentials_clear_the_unconfigured_status(
    client: TestClient, admin: dict[str, str], seeded: None
) -> None:
    _save(client, admin, "tmdb", TMDB_SECRET)
    _save(client, admin, "tvdb", TVDB_SECRET)

    payload = _dashboard(client, admin)
    sources = _sources_by_key(payload)

    assert sources["tmdb"]["status"] == "OK"
    assert sources["tvdb"]["status"] == "OK"
    # No healthcheck ran: the status comes from the credential, not from a check.
    assert sources["tmdb"]["last_healthcheck_at"] is None
    assert payload["counters"]["sources_unconfigured"] == 0
    assert payload["counters"]["sources_ok"] >= 2
    alerts = _alert_codes(payload)
    assert "SOURCE_UNCONFIGURED" not in alerts
    assert "CREDENTIAL_MISSING" not in alerts


def test_dashboard_and_sources_endpoint_agree(
    client: TestClient, admin: dict[str, str], seeded: None
) -> None:
    _save(client, admin, "tmdb", TMDB_SECRET)

    dashboard = _sources_by_key(_dashboard(client, admin))
    response = client.get("/api/sources", headers=admin)
    assert response.status_code == 200, response.text
    sources = {row["key"]: row for row in response.json()["items"]}

    assert sources["tmdb"]["status"] == dashboard["tmdb"]["status"] == "OK"
    assert sources["tmdb"]["credential_configured"] is True


def test_deleted_credential_restores_the_unconfigured_status(
    client: TestClient, admin: dict[str, str], seeded: None
) -> None:
    _save(client, admin, "tmdb", TMDB_SECRET)
    assert _sources_by_key(_dashboard(client, admin))["tmdb"]["status"] == "OK"

    deleted = client.delete("/api/credentials/tmdb", headers=admin)
    assert deleted.status_code == 204, deleted.text

    payload = _dashboard(client, admin)
    assert _sources_by_key(payload)["tmdb"]["status"] == "UNCONFIGURED"
    assert "SOURCE_UNCONFIGURED" in _alert_codes(payload)


def test_disabled_source_keeps_its_status_with_credentials(
    client: TestClient, admin: dict[str, str], seeded: None
) -> None:
    payload = _dashboard(client, admin)
    sources = _sources_by_key(payload)
    disabled = {key for key, row in sources.items() if row["status"] == "DISABLED"}

    assert "justwatch" not in disabled
    assert sources["justwatch"]["status"] == "OK"
