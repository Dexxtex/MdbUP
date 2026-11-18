"""Notification channels, delivery and run-event scanning."""

from __future__ import annotations

import httpx
import pytest
import respx
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.db.models import CollectionSnapshot, SnapshotItem
from app.db.session import get_session_factory
from app.domain.enums import SyncRunStatus
from app.repositories import bindings as bindings_repo
from app.repositories import collections as collections_repo
from app.repositories import media as media_repo
from app.repositories import runs as runs_repo
from app.repositories import targets as targets_repo
from app.services import notifications


@pytest.fixture()
def session(db) -> Session:
    factory = get_session_factory()
    db_session = factory()
    try:
        yield db_session
    finally:
        db_session.close()


def _snapshot(db: Session, collection, tmdb_ids: list[int]) -> CollectionSnapshot:
    media_ids = []
    for tmdb_id in tmdb_ids:
        media = media_repo.resolve_media(
            db,
            media_type=collection.media_type,
            tmdb_id=tmdb_id,
            imdb_id=None,
            title=f"Media {tmdb_id}",
            year=2020,
        )
        assert media is not None
        media_ids.append(media.id)
    snapshot = CollectionSnapshot(
        collection_id=collection.id,
        status="COMPLETE",
        quality="CLEAN",
        is_valid=True,
        items_count=len(media_ids),
        resolved_count=len(media_ids),
        unresolved_count=0,
        duplicate_count=0,
        error_count=0,
        checksum="checksum",
    )
    db.add(snapshot)
    db.flush()
    for position, media_id in enumerate(media_ids):
        db.add(
            SnapshotItem(
                snapshot_id=snapshot.id,
                media_id=media_id,
                position=position,
                date_basis="UNKNOWN",
                resolution_status="RESOLVED",
            )
        )
    collection.last_valid_snapshot_id = snapshot.id
    db.commit()
    return snapshot


def _binding(db: Session, collection):
    target = targets_repo.create_target(
        db, remote_list_id=9001, name="Lista notifiche", mediatype="MOVIE"
    )
    binding = bindings_repo.create_binding(
        db,
        collection_id=collection.id,
        target_id=target.id,
        media_type=collection.media_type,
        mode="MIRROR",
        schedule_cron="",
        timezone="Europe/Rome",
        is_enabled=True,
        policy_version="v1",
        policy_accepted_at=utcnow(),
        policy_accepted_by=None,
        max_removal_absolute=50,
        max_removal_percent=10.0,
        max_addition_percent=50.0,
        preserve_order=False,
        reorder_enabled=True,
        require_manual_review=True,
        schedule_policy="ALWAYS_APPROVE",
        auto_apply_max_removals=5,
        auto_apply_max_removal_ratio=2.0,
        max_plan_age_minutes=60,
        next_run_at=None,
    )
    db.commit()
    return binding


def _channel(db: Session, settings, kind: str = "WEBHOOK", secret: str | None = None):
    return notifications.create_channel(
        db,
        settings,
        name=f"Test {kind}",
        kind=kind,
        secret=secret
        or (
            "https://hooks.example.test/mdbup"
            if kind != "TELEGRAM"
            else "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        ),
        events=list(notifications.NOTIFICATION_EVENTS),
        config={"chat_id": "42"} if kind == "TELEGRAM" else {},
        is_enabled=True,
    )


@respx.mock
def test_webhook_test_message_and_secret_is_encrypted(session, seeded, app_settings) -> None:
    channel = _channel(session, app_settings)
    route = respx.post("https://hooks.example.test/mdbup").mock(return_value=httpx.Response(200))
    result = notifications.send_test(session, app_settings, channel.id)
    assert result.ok is True
    assert route.called
    assert channel.secret_ciphertext is not None
    assert channel.secret_masked_hint is not None
    assert "hooks.example.test" not in channel.secret_masked_hint


@respx.mock
def test_telegram_and_discord_payloads(session, seeded, app_settings) -> None:
    telegram = _channel(session, app_settings, kind="TELEGRAM")
    telegram_route = respx.post(
        "https://api.telegram.org/bot123456:ABCDEFGHIJKLMNOPQRSTUVWXYZ/sendMessage"
    ).mock(return_value=httpx.Response(200))
    assert notifications.send_test(session, app_settings, telegram.id).ok is True
    assert telegram_route.calls.last.request.content
    assert b'"chat_id":"42"' in telegram_route.calls.last.request.content

    discord = _channel(
        session,
        app_settings,
        kind="DISCORD",
        secret="https://discord.com/api/webhooks/123/token",
    )
    discord_route = respx.post("https://discord.com/api/webhooks/123/token").mock(
        return_value=httpx.Response(200)
    )
    assert notifications.send_test(session, app_settings, discord.id).ok is True
    assert b'"content"' in discord_route.calls.last.request.content


@respx.mock
def test_pending_approval_and_failed_run_alerts_are_sent_once(
    session, seeded, app_settings
) -> None:
    collection = collections_repo.get_collection_by_slug(session, "netflix-movie")
    assert collection is not None
    snapshot = _snapshot(session, collection, [1])
    binding = _binding(session, collection)
    channel = _channel(session, app_settings)
    route = respx.post("https://hooks.example.test/mdbup").mock(return_value=httpx.Response(200))

    pending = runs_repo.create_run(
        session,
        binding_id=binding.id,
        target_id=binding.target_id,
        media_type=binding.media_type,
        snapshot_id=snapshot.id,
        mode="MIRROR",
        trigger_type="MANUAL",
        is_dry_run=False,
    )
    runs_repo.transition_run(session, pending, SyncRunStatus.PREFLIGHT)
    runs_repo.transition_run(session, pending, SyncRunStatus.PLANNING)
    runs_repo.transition_run(session, pending, SyncRunStatus.AWAITING_APPROVAL, message="threshold")
    pending.to_add_count = 3
    pending.to_remove_count = 2
    pending.abort_reason = "REMOVAL_ABSOLUTE_EXCEEDED"
    session.commit()

    first = notifications.scan_run_notifications(session, app_settings)
    assert first["sent"] == 1
    assert route.call_count == 1
    body = route.calls.last.request.content.decode()
    assert "attesa di approvazione" in body
    assert "Aggiunte previste: 3" in body
    assert "Rimozioni previste: 2" in body
    assert f"/app/runs/{pending.id}" in body

    second = notifications.scan_run_notifications(session, app_settings)
    assert second["scanned"] == 0
    assert route.call_count == 1

    runs_repo.finish_run(session, pending, SyncRunStatus.CANCELLED)
    session.commit()
    failed = runs_repo.create_run(
        session,
        binding_id=binding.id,
        target_id=binding.target_id,
        media_type=binding.media_type,
        snapshot_id=snapshot.id,
        mode="MIRROR",
        trigger_type="MANUAL",
        is_dry_run=False,
    )
    runs_repo.finish_run(
        session,
        failed,
        SyncRunStatus.FAILED,
        error_code="MDBLIST_AUTH_FAILED",
        error_message="credential rejected",
    )
    session.commit()
    third = notifications.scan_run_notifications(session, app_settings)
    assert third["sent"] == 1
    assert route.call_count == 2
    assert "run fallito" in route.calls.last.request.content.decode()
    assert channel.last_status == "SENT"


@respx.mock
def test_auth_error_is_deduplicated(session, seeded, app_settings) -> None:
    _channel(session, app_settings)
    route = respx.post("https://hooks.example.test/mdbup").mock(return_value=httpx.Response(200))
    first = notifications.notify_auth_error(session, app_settings, service="TMDb", status_code=401)
    second = notifications.notify_auth_error(session, app_settings, service="TMDb", status_code=401)
    assert first.sent == 1
    assert second.attempted == 0
    assert route.call_count == 1
