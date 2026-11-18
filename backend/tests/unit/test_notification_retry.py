"""Notification retry: backoff, resend and the retry budget."""

from __future__ import annotations

from datetime import timedelta

import httpx
import pytest
import respx
from sqlalchemy.orm import Session

from app.core.time import ensure_utc, utcnow
from app.db.session import get_session_factory
from app.services import notifications

WEBHOOK = "https://hooks.example.test/mdbup"


@pytest.fixture()
def session(db) -> Session:
    factory = get_session_factory()
    db_session = factory()
    try:
        yield db_session
    finally:
        db_session.close()


def _channel(db: Session, settings):
    return notifications.create_channel(
        db,
        settings,
        name="Webhook retry",
        kind="WEBHOOK",
        secret=WEBHOOK,
        events=list(notifications.NOTIFICATION_EVENTS),
        config={},
        is_enabled=True,
    )


def test_backoff_schedule_is_one_five_and_fifteen_minutes() -> None:
    assert notifications.retry_delay_seconds(1) == 60
    assert notifications.retry_delay_seconds(2) == 300
    assert notifications.retry_delay_seconds(3) == 900
    assert notifications.retry_delay_seconds(0) is None
    assert notifications.retry_delay_seconds(4) is None
    assert notifications.MAX_RETRY_ATTEMPTS == 3


@respx.mock
def test_failed_delivery_schedules_a_retry(session, seeded, app_settings) -> None:
    channel = _channel(session, app_settings)
    respx.post(WEBHOOK).mock(return_value=httpx.Response(500))

    result = notifications.send_test(session, app_settings, channel.id)

    assert result.ok is False
    assert channel.last_status == "FAILED"
    assert channel.retry_count == 1
    assert channel.next_retry_at is not None
    delay = (ensure_utc(channel.next_retry_at) - utcnow()).total_seconds()
    assert 50 <= delay <= 70
    # The failed event is persisted so the retry does not rebuild it.
    assert channel.last_event == "TEST"
    assert channel.last_payload["message"].startswith("MdbUP")
    assert channel.last_payload["payload"] == {"test": True}


@respx.mock
def test_retry_waits_for_the_backoff_window(session, seeded, app_settings) -> None:
    channel = _channel(session, app_settings)
    respx.post(WEBHOOK).mock(return_value=httpx.Response(500))
    notifications.send_test(session, app_settings, channel.id)

    early = notifications.retry_due_notifications(session, app_settings, now=utcnow())
    assert early == {"due": 0, "sent": 0, "failed": 0, "skipped": 0}

    due = notifications.retry_due_notifications(
        session, app_settings, now=utcnow() + timedelta(minutes=2)
    )
    assert due["due"] == 1


@respx.mock
def test_second_attempt_succeeds_and_resets_the_state(session, seeded, app_settings) -> None:
    channel = _channel(session, app_settings)
    route = respx.post(WEBHOOK).mock(return_value=httpx.Response(500))
    notifications.send_test(session, app_settings, channel.id)
    assert channel.retry_count == 1

    route.mock(return_value=httpx.Response(200))
    outcome = notifications.retry_due_notifications(
        session, app_settings, now=utcnow() + timedelta(minutes=2)
    )

    assert outcome == {"due": 1, "sent": 1, "failed": 0, "skipped": 0}
    assert channel.last_status == "SENT"
    assert channel.retry_count == 0
    assert channel.next_retry_at is None
    assert channel.last_sent_at is not None
    assert channel.last_error is None
    assert route.call_count == 2

    again = notifications.retry_due_notifications(
        session, app_settings, now=utcnow() + timedelta(days=1)
    )
    assert again["due"] == 0


@respx.mock
def test_retry_stops_after_three_attempts(session, seeded, app_settings) -> None:
    channel = _channel(session, app_settings)
    respx.post(WEBHOOK).mock(return_value=httpx.Response(503))
    notifications.send_test(session, app_settings, channel.id)

    delays: list[float] = []
    for _ in range(notifications.MAX_RETRY_ATTEMPTS):
        delays.append(
            (ensure_utc(channel.next_retry_at) - utcnow()).total_seconds()
            if channel.next_retry_at is not None
            else -1
        )
        notifications.retry_due_notifications(
            session, app_settings, now=ensure_utc(channel.next_retry_at) + timedelta(seconds=1)
        )

    # 1m, 5m, 15m: the budget shrinks exactly as documented.
    assert [round(delay / 60) for delay in delays] == [1, 5, 15]
    assert channel.retry_count == notifications.MAX_RETRY_ATTEMPTS + 1
    assert channel.next_retry_at is None
    assert channel.last_status == "FAILED"

    stopped = notifications.retry_due_notifications(
        session, app_settings, now=utcnow() + timedelta(days=7)
    )
    assert stopped["due"] == 0


@respx.mock
def test_success_after_a_failure_clears_the_retry_budget(session, seeded, app_settings) -> None:
    channel = _channel(session, app_settings)
    route = respx.post(WEBHOOK).mock(return_value=httpx.Response(500))
    notifications.send_test(session, app_settings, channel.id)
    notifications.retry_due_notifications(
        session, app_settings, now=utcnow() + timedelta(minutes=2)
    )
    assert channel.retry_count == 2

    route.mock(return_value=httpx.Response(200))
    notifications.retry_due_notifications(
        session, app_settings, now=utcnow() + timedelta(minutes=10)
    )
    assert channel.retry_count == 0
    assert channel.next_retry_at is None

    # A new failure restarts from the first backoff step.
    route.mock(return_value=httpx.Response(500))
    notifications.send_test(session, app_settings, channel.id)
    assert channel.retry_count == 1
    delay = (ensure_utc(channel.next_retry_at) - utcnow()).total_seconds()
    assert 50 <= delay <= 70


def test_retry_task_is_scheduled_every_minute() -> None:
    from app.jobs import tasks
    from app.jobs.celery_app import celery_app

    entry = celery_app.conf.beat_schedule["retry-failed-notifications"]
    assert entry["task"] == tasks.RETRY_FAILED_NOTIFICATIONS_TASK
    assert entry["schedule"] == 60.0
    assert entry["options"]["queue"] == "maintenance"
