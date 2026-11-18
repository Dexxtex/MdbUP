"""Notification channel API: masked secrets, CRUD and test delivery."""

from __future__ import annotations

import httpx
import respx


@respx.mock
def test_notification_channel_crud_and_test(client, admin, seeded) -> None:
    route = respx.post("https://hooks.example.test/mdbup").mock(return_value=httpx.Response(200))
    created = client.post(
        "/api/notifications/channels",
        json={
            "name": "Webhook test",
            "kind": "WEBHOOK",
            "secret": "https://hooks.example.test/mdbup",
            "events": ["RUN_PENDING_APPROVAL", "RUN_FAILED"],
            "config": {},
            "enabled": True,
        },
        headers=admin,
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["secret_configured"] is True
    assert "secret" not in body
    assert body["masked_hint"].startswith("••••")
    # Retry state is part of the channel contract (Phase 7).
    assert body["retry_count"] == 0
    assert body["next_retry_at"] is None
    channel_id = body["id"]

    listing = client.get("/api/notifications/channels")
    assert listing.status_code == 200
    assert len(listing.json()["items"]) == 1

    tested = client.post(f"/api/notifications/channels/{channel_id}/test", headers=admin)
    assert tested.status_code == 200, tested.text
    assert tested.json()["ok"] is True
    assert route.called

    updated = client.patch(
        f"/api/notifications/channels/{channel_id}",
        json={"enabled": False, "events": ["RUN_UNCERTAIN"]},
        headers=admin,
    )
    assert updated.status_code == 200
    assert updated.json()["enabled"] is False
    assert updated.json()["events"] == ["RUN_UNCERTAIN"]

    deleted = client.delete(f"/api/notifications/channels/{channel_id}", headers=admin)
    assert deleted.status_code == 204
    assert client.get("/api/notifications/channels").json()["items"] == []


def test_telegram_requires_chat_id(client, admin, seeded) -> None:
    response = client.post(
        "/api/notifications/channels",
        json={
            "name": "Telegram senza chat",
            "kind": "TELEGRAM",
            "secret": "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZ",
            "events": [],
            "config": {},
        },
        headers=admin,
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "NOTIFICATION_CONFIG_INVALID"
