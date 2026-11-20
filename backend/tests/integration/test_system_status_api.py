"""System status endpoint: admin session and the documented JSON shape."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient


def _status_file(tmp_path, *, status: str = "OK", hours_ago: int = 3):
    moment = datetime.now(UTC) - timedelta(hours=hours_ago)
    path = tmp_path / "last_backup.json"
    path.write_text(
        json.dumps(
            {
                "timestamp": moment.isoformat().replace("+00:00", "Z"),
                "file": "mdbup-20261118T100000Z.dump.age",
                "size": 2048,
                "sha256": "c" * 64,
                "status": status,
                "error": None,
            }
        ),
        encoding="utf-8",
    )
    return path


def test_system_status_requires_an_admin_session(client: TestClient, seeded) -> None:
    response = client.get("/api/system/status")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_UNAUTHENTICATED"


def test_system_status_shape(client: TestClient, admin, seeded, app_settings, tmp_path) -> None:
    status_file = _status_file(tmp_path)
    app_settings.backup_dir = str(tmp_path)
    app_settings.backup_status_file = str(status_file)

    response = client.get("/api/system/status")

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {
        "health",
        "queues",
        "runs",
        "api_usage",
        "backup",
        "pending_approvals",
        "upcoming",
        "catalog_acquisitions",
        "storage",
    }
    assert set(body["storage"]) == {
        "snapshot_bytes",
        "run_bytes",
        "total_bytes",
        "database_bytes",
        "snapshot_rows",
        "snapshot_item_rows",
        "run_rows",
        "size_supported",
    }
    assert body["health"] == {
        "api": True,
        "database": True,
        "redis": False,
        "worker": False,
        "tmdb": "MISSING_CREDENTIAL",
        "mdblist": "MISSING_CREDENTIAL",
        "tvdb": "MISSING_CREDENTIAL",
    }
    assert body["queues"] == {"celery": 0, "maintenance": 0, "sync": 0, "acquisitions": 0}
    for status in ("SUCCEEDED", "FAILED", "AWAITING_APPROVAL", "PARTIAL"):
        assert body["runs"][status] == 0
    assert body["api_usage"] == {
        "tmdb": {"hour": 0, "today": 0},
        "mdblist": {"hour": 0, "today": 0},
        "justwatch": {"hour": 0, "today": 0, "cache_hits": 0, "cache_misses": 0},
    }
    assert body["backup"]["file"] == "mdbup-20261118T100000Z.dump.age"
    assert body["backup"]["status"] == "OK"
    assert body["backup"]["last_valid_at"] is not None
    assert 2.5 <= body["backup"]["age_hours"] <= 3.5
    assert body["pending_approvals"] == 0
    assert body["upcoming"] == []
    assert body["catalog_acquisitions"] == []


def test_system_status_without_a_backup_file(
    client: TestClient, admin, seeded, app_settings, tmp_path
) -> None:
    app_settings.backup_dir = str(tmp_path)
    app_settings.backup_status_file = str(tmp_path / "absent.json")

    body = client.get("/api/system/status").json()

    assert body["backup"] == {
        "last_valid_at": None,
        "file": None,
        "status": "MISSING",
        "age_hours": None,
    }


def test_system_status_lists_upcoming_bindings(
    client: TestClient, admin, seeded, app_settings, tmp_path
) -> None:
    from app.core.time import utcnow
    from app.db.session import get_session_factory
    from app.repositories import bindings as bindings_repo
    from app.repositories import collections as collections_repo
    from app.repositories import targets as targets_repo

    app_settings.backup_status_file = str(tmp_path / "absent.json")
    session = get_session_factory()()
    try:
        collection = collections_repo.get_collection_by_slug(session, "netflix-movie")
        assert collection is not None
        target = targets_repo.create_target(
            session, remote_list_id=4242, name="Lista topbar", mediatype="MOVIE"
        )
        binding = bindings_repo.create_binding(
            session,
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
            next_run_at=utcnow() + timedelta(hours=1),
        )
        session.commit()
        binding_id = str(binding.id)
        collection_name = collection.name
    finally:
        session.close()

    body = client.get("/api/system/status").json()

    assert len(body["upcoming"]) == 1
    item = body["upcoming"][0]
    assert item["binding_id"] == binding_id
    assert item["collection_name"] == collection_name
    assert item["target_name"] == "Lista topbar"
    assert item["next_run_at"] is not None


def test_system_status_lists_staggered_catalog_acquisitions(
    client: TestClient, admin, seeded, app_settings, tmp_path
) -> None:
    from app.db.session import get_session_factory
    from app.repositories import collections as collections_repo
    from app.repositories import providers as providers_repo
    from app.repositories import sources as sources_repo

    app_settings.backup_status_file = str(tmp_path / "absent.json")
    session = get_session_factory()()
    try:
        source = sources_repo.get_source_by_key(session, "justwatch")
        provider = providers_repo.get_provider_by_slug(session, "netflix")
        assert source is not None and provider is not None
        collections_repo.upsert_collection(
            session,
            slug="netflix-movie-justwatch-status",
            source_id=source.id,
            provider_id=provider.id,
            country_code="IT",
            media_type="MOVIE",
            kind="CATALOG",
            origin="AGGREGATOR",
            date_basis="UNKNOWN",
            name="Netflix — Film — Catalogo JustWatch",
            description=None,
            source_collection_key="nfx:MOVIE",
            source_url=None,
            offer_types=["FLATRATE"],
            filters={},
            quality_flags={},
            sort_mode="POPULARITY",
            is_active=True,
        )
        session.commit()
    finally:
        session.close()

    body = client.get("/api/system/status").json()

    assert len(body["catalog_acquisitions"]) == 1
    item = body["catalog_acquisitions"][0]
    assert item["collection_name"] == "Netflix — Film — Catalogo JustWatch"
    assert item["provider_name"] == "Netflix"
    assert item["collection_id"] is not None
    assert item["next_acquire_at"] is not None
