"""Sync API integration tests: targets, bindings, previews and runs.

The MDBList API is always mocked with respx; these tests never touch a real
list. Celery runs inline because ``APP_ENV=test``.
"""

from __future__ import annotations

import uuid

import httpx
import respx

BASE = "https://api.mdblist.com"


def _set_mdblist_credential(app_settings) -> None:
    from app.db.session import get_session_factory
    from app.services import credentials as credentials_service
    from app.services.credentials import CredentialKind

    session = get_session_factory()()
    try:
        credentials_service.set_secret(
            session, app_settings, CredentialKind.MDBLIST, "test-mdblist-key"
        )
    finally:
        session.close()


def _collection(client, slug: str) -> dict:
    items = client.get("/api/collections").json()["items"]
    return next(item for item in items if item["slug"] == slug)


def _create_snapshot(collection_id: str, tmdb_ids: list[int]) -> str:
    from app.db.models import Collection, CollectionSnapshot, SnapshotItem
    from app.db.session import get_session_factory
    from app.repositories import media as media_repo

    session = get_session_factory()()
    try:
        collection = session.get(Collection, uuid.UUID(collection_id))
        assert collection is not None
        media_ids = []
        for tmdb_id in tmdb_ids:
            media = media_repo.resolve_media(
                session,
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
        session.add(snapshot)
        session.flush()
        for position, media_id in enumerate(media_ids):
            session.add(
                SnapshotItem(
                    snapshot_id=snapshot.id,
                    media_id=media_id,
                    position=position,
                    date_basis="UNKNOWN",
                    resolution_status="RESOLVED",
                )
            )
        collection.last_valid_snapshot_id = snapshot.id
        session.commit()
        return str(snapshot.id)
    finally:
        session.close()


def _create_target(mediatype: str = "MOVIE", remote_list_id: int = 42) -> str:
    from app.db.session import get_session_factory
    from app.repositories import targets as targets_repo

    session = get_session_factory()()
    try:
        target = targets_repo.create_target(
            session,
            remote_list_id=remote_list_id,
            name="Test list",
            mediatype=mediatype,
        )
        session.commit()
        return str(target.id)
    finally:
        session.close()


def _create_binding(
    client, admin: dict[str, str], collection_id: str, target_id: str, **overrides: object
) -> dict:
    payload: dict[str, object] = {
        "collection_id": collection_id,
        "target_id": target_id,
        "mode": "MIRROR",
        "schedule": "MANUAL",
        "thresholds": {
            "max_removal_pct": 100,
            "max_removal_abs": 100,
            "max_addition_pct": 100,
        },
        "preserve_order": False,
        "reorder_enabled": True,
        "schedule_policy": "AUTO_APPLY_IF_SAFE",
        "require_review": True,
        "enabled": True,
        "policy_version": "v1",
        "auto_apply_max_removals": 100,
        "auto_apply_max_removal_ratio": 100,
    }
    payload.update(overrides)
    response = client.post("/api/bindings", json=payload, headers=admin)
    assert response.status_code == 201, response.text
    return response.json()


def _mock_list_metadata(list_id: int = 42, user_id: int = 5) -> None:
    respx.get(f"{BASE}/lists/{list_id}").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": list_id,
                "name": "Test list",
                "slug": "test-list",
                "private": False,
                "mediatype": "movie",
                "user_id": user_id,
                "user_name": "owner",
                "items": 0,
            },
        )
    )
    respx.get(f"{BASE}/user").mock(
        return_value=httpx.Response(200, json={"id": user_id, "user_name": "owner"})
    )


def _items_response(tmdb_ids: list[int]) -> httpx.Response:
    return httpx.Response(
        200,
        headers={"X-Has-More": "false"},
        json={
            "movies": [
                {"ids": {"tmdb": tmdb_id}, "title": f"Media {tmdb_id}"} for tmdb_id in tmdb_ids
            ],
            "shows": [],
            "pagination": {},
        },
    )


def test_target_creation_requires_mdblist_credential(client, admin, seeded) -> None:
    collection = _collection(client, "netflix-movie")
    response = client.post(
        "/api/targets",
        json={
            "mode": "new",
            "name": "Netflix IT",
            "private": True,
            "media_type": collection["media_type"],
        },
        headers=admin,
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CREDENTIAL_MISSING"


@respx.mock
def test_create_and_list_target(client, admin, seeded, app_settings) -> None:
    _set_mdblist_credential(app_settings)
    respx.post(f"{BASE}/lists/user/add").mock(
        return_value=httpx.Response(
            200, json={"id": 42, "name": "Netflix IT", "slug": "netflix-it"}
        )
    )
    response = client.post(
        "/api/targets",
        json={
            "mode": "new",
            "name": "Netflix IT",
            "private": True,
            "media_type": "MOVIE",
        },
        headers=admin,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["remote_list_id"] == "42"
    assert body["private"] is True
    assert body["mediatype"] == "MOVIE"

    listing = client.get("/api/targets?media_type=MOVIE").json()
    assert listing["total"] == 1
    assert listing["items"][0]["remote_list_id"] == "42"

    duplicate = client.post(
        "/api/targets",
        json={
            "mode": "new",
            "name": "Netflix IT again",
            "private": False,
            "media_type": "MOVIE",
        },
        headers=admin,
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "TARGET_ALREADY_LINKED"


@respx.mock
def test_preview_counts_and_no_writes(client, admin, seeded, app_settings) -> None:
    _set_mdblist_credential(app_settings)
    collection = _collection(client, "netflix-movie")
    _create_snapshot(collection["id"], [1, 2])
    target_id = _create_target()
    _mock_list_metadata()
    items_route = respx.get(f"{BASE}/lists/42/items").mock(return_value=_items_response([2, 3]))
    add_route = respx.post(f"{BASE}/lists/42/items/add").mock(
        return_value=httpx.Response(200, json={"added": {"movies": 1}})
    )

    response = client.post(
        "/api/previews",
        json={
            "collection_id": collection["id"],
            "target_id": target_id,
            "mode": "MIRROR",
            "thresholds": {
                "max_removal_pct": 100,
                "max_removal_abs": 100,
                "max_addition_pct": 100,
            },
        },
        headers=admin,
    )
    assert response.status_code == 202, response.text
    preview_id = response.json()["preview_id"]

    preview = client.get(f"/api/previews/{preview_id}").json()
    assert preview["state"] == "READY"
    assert preview["counts"] == {
        "to_add": 1,
        "to_remove": 1,
        "unchanged": 1,
        "unresolved": 0,
        "unmapped_remote": 0,
        "remote_duplicates": 0,
    }
    assert preview["plan_hash"]
    assert preview["snapshot_hash"]
    assert items_route.called
    assert not add_route.called


def test_preview_without_target_is_source_only(client, admin, seeded) -> None:
    collection = _collection(client, "netflix-movie")
    _create_snapshot(collection["id"], [1, 2])
    response = client.post(
        "/api/previews",
        json={
            "collection_id": collection["id"],
            "thresholds": {
                "max_removal_pct": 100,
                "max_removal_abs": 100,
                "max_addition_pct": 100,
            },
        },
        headers=admin,
    )
    assert response.status_code == 202, response.text
    preview = client.get(f"/api/previews/{response.json()['preview_id']}").json()
    assert preview["state"] == "READY"
    assert preview["counts"]["to_add"] == 2
    assert preview["plan_hash"] is None


def test_binding_rejects_media_type_mismatch(client, admin, seeded) -> None:
    collection = _collection(client, "netflix-movie")
    _create_snapshot(collection["id"], [1])
    target_id = _create_target(mediatype="SHOW")
    response = client.post(
        "/api/bindings",
        json={
            "collection_id": collection["id"],
            "target_id": target_id,
            "mode": "MIRROR",
            "schedule": "MANUAL",
            "thresholds": {
                "max_removal_pct": 10,
                "max_removal_abs": 10,
                "max_addition_pct": 50,
            },
            "enabled": False,
        },
        headers=admin,
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "MEDIA_TYPE_MISMATCH"


def test_run_without_valid_snapshot_returns_409(client, admin, seeded, app_settings) -> None:
    _set_mdblist_credential(app_settings)
    collection = _collection(client, "netflix-movie")
    target_id = _create_target()
    binding = _create_binding(client, admin, collection["id"], target_id, enabled=False)
    response = client.post(
        f"/api/bindings/{binding['id']}/runs",
        json={"dry_run": True},
        headers=admin,
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SNAPSHOT_INVALID"


@respx.mock
def test_dry_run_then_real_run(client, admin, seeded, app_settings) -> None:
    _set_mdblist_credential(app_settings)
    collection = _collection(client, "netflix-movie")
    _create_snapshot(collection["id"], [1, 2])
    target_id = _create_target()
    binding = _create_binding(client, admin, collection["id"], target_id)
    _mock_list_metadata()
    respx.get(f"{BASE}/lists/42/items").mock(
        side_effect=[
            _items_response([2, 3]),
            _items_response([2, 3]),
            _items_response([2, 1]),
        ]
    )
    add_route = respx.post(f"{BASE}/lists/42/items/add").mock(
        return_value=httpx.Response(200, json={"added": {"movies": 1}})
    )
    remove_route = respx.post(f"{BASE}/lists/42/items/remove").mock(
        return_value=httpx.Response(200, json={"removed": {"movies": 1}})
    )

    dry = client.post(
        f"/api/bindings/{binding['id']}/runs",
        json={"dry_run": True},
        headers=admin,
    )
    assert dry.status_code == 202, dry.text
    dry_run = client.get(f"/api/runs/{dry.json()['run_id']}").json()
    assert dry_run["status"] == "SUCCEEDED"
    assert dry_run["is_dry_run"] is True
    assert dry_run["to_add_count"] == 1
    assert dry_run["to_remove_count"] == 1
    assert not add_route.called
    assert not remove_route.called

    real = client.post(
        f"/api/bindings/{binding['id']}/runs",
        json={"dry_run": False},
        headers=admin,
    )
    assert real.status_code == 202, real.text
    run = client.get(f"/api/runs/{real.json()['run_id']}").json()
    assert run["status"] == "SUCCEEDED", run
    assert run["added_count"] == 1
    assert run["removed_count"] == 1
    assert run["counters"]["applied"] == 2
    assert add_route.called
    assert remove_route.called

    operations = client.get(f"/api/runs/{run['id']}/operations").json()
    assert operations["total"] == 2
    assert {item["action"] for item in operations["items"]} == {"ADD", "REMOVE"}
    assert {item["status"] for item in operations["items"]} == {"SUCCEEDED"}


@respx.mock
def test_threshold_requires_approval_and_approve_plan_hash(
    client, admin, seeded, app_settings
) -> None:
    _set_mdblist_credential(app_settings)
    collection = _collection(client, "netflix-movie")
    _create_snapshot(collection["id"], [1, 2])
    target_id = _create_target()
    binding = _create_binding(
        client,
        admin,
        collection["id"],
        target_id,
        thresholds={"max_removal_pct": 100, "max_removal_abs": 100, "max_addition_pct": 10},
    )
    _mock_list_metadata()
    respx.get(f"{BASE}/lists/42/items").mock(
        side_effect=[
            _items_response([1]),
            _items_response([1]),
            _items_response([1, 2]),
        ]
    )
    respx.post(f"{BASE}/lists/42/items/add").mock(
        return_value=httpx.Response(200, json={"added": {"movies": 1}})
    )

    started = client.post(
        f"/api/bindings/{binding['id']}/runs",
        json={"dry_run": False},
        headers=admin,
    )
    assert started.status_code == 202, started.text
    run_id = started.json()["run_id"]
    run = client.get(f"/api/runs/{run_id}").json()
    assert run["status"] == "AWAITING_APPROVAL"
    assert run["requires_approval"] is True
    assert run["plan_hash"]

    stale = client.post(
        f"/api/runs/{run_id}/approve",
        json={"plan_hash": "0" * 64},
        headers=admin,
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "STALE_PLAN"

    approved = client.post(
        f"/api/runs/{run_id}/approve",
        json={"plan_hash": run["plan_hash"]},
        headers=admin,
    )
    assert approved.status_code == 202, approved.text
    final = client.get(f"/api/runs/{run_id}").json()
    assert final["status"] == "SUCCEEDED", final
    assert final["approved_at"] is not None


@respx.mock
def test_cancel_awaiting_approval(client, admin, seeded, app_settings) -> None:
    _set_mdblist_credential(app_settings)
    collection = _collection(client, "netflix-movie")
    _create_snapshot(collection["id"], [1, 2])
    target_id = _create_target()
    binding = _create_binding(
        client,
        admin,
        collection["id"],
        target_id,
        thresholds={"max_removal_pct": 100, "max_removal_abs": 100, "max_addition_pct": 10},
    )
    _mock_list_metadata()
    respx.get(f"{BASE}/lists/42/items").mock(return_value=_items_response([1]))

    started = client.post(
        f"/api/bindings/{binding['id']}/runs",
        json={"dry_run": False},
        headers=admin,
    )
    run_id = started.json()["run_id"]
    assert client.get(f"/api/runs/{run_id}").json()["status"] == "AWAITING_APPROVAL"

    cancelled = client.post(f"/api/runs/{run_id}/cancel", headers=admin)
    assert cancelled.status_code == 202, cancelled.text
    assert client.get(f"/api/runs/{run_id}").json()["status"] == "CANCELLED"


def _create_partial_run(collection_id: str, target_id: str, tmdb_ids: list[int]) -> str:
    from app.db.models import Collection
    from app.db.session import get_session_factory
    from app.domain.enums import SyncRunStatus
    from app.repositories import bindings as bindings_repo
    from app.repositories import media as media_repo
    from app.repositories import runs as runs_repo

    session = get_session_factory()()
    try:
        collection = session.get(Collection, uuid.UUID(collection_id))
        assert collection is not None
        assert collection.last_valid_snapshot_id is not None
        binding = bindings_repo.get_by_collection_target(
            session,
            collection_id=collection.id,
            target_id=uuid.UUID(target_id),
        )
        assert binding is not None
        run = runs_repo.create_run(
            session,
            binding_id=binding.id,
            target_id=binding.target_id,
            media_type=binding.media_type,
            snapshot_id=collection.last_valid_snapshot_id,
            mode=binding.mode,
            trigger_type="MANUAL",
            is_dry_run=False,
        )
        runs_repo.transition_run(session, run, SyncRunStatus.PREFLIGHT)
        runs_repo.transition_run(session, run, SyncRunStatus.PLANNING)
        runs_repo.transition_run(session, run, SyncRunStatus.APPLYING)
        runs_repo.finish_run(session, run, SyncRunStatus.PARTIAL)
        run.uncertain_count = 1
        media = media_repo.find_by_tmdb(session, "MOVIE", tmdb_ids[0])
        assert media is not None
        runs_repo.create_operation(
            session,
            run_id=run.id,
            action="ADD",
            media_id=media.id,
            remote_id=f"MOVIE:tmdb:{tmdb_ids[0]}",
            idempotency_key=f"{run.id}-op",
        )
        session.commit()
        return str(run.id)
    finally:
        session.close()


@respx.mock
def test_reconcile_partial_run(client, admin, seeded, app_settings) -> None:
    _set_mdblist_credential(app_settings)
    collection = _collection(client, "netflix-movie")
    _create_snapshot(collection["id"], [1])
    target_id = _create_target()
    _create_binding(client, admin, collection["id"], target_id)
    run_id = _create_partial_run(collection["id"], target_id, [1])
    respx.get(f"{BASE}/lists/42/items").mock(return_value=_items_response([1]))

    response = client.post(f"/api/runs/{run_id}/reconcile", headers=admin)
    assert response.status_code == 202, response.text
    run = client.get(f"/api/runs/{run_id}").json()
    assert run["status"] == "SUCCEEDED", run
    assert run["added_count"] == 1
    operations = client.get(f"/api/runs/{run_id}/operations").json()
    assert operations["items"][0]["status"] == "SUCCEEDED"


@respx.mock
def test_resume_partial_run_creates_a_child_run(client, admin, seeded, app_settings) -> None:
    _set_mdblist_credential(app_settings)
    collection = _collection(client, "netflix-movie")
    _create_snapshot(collection["id"], [1])
    target_id = _create_target()
    _create_binding(client, admin, collection["id"], target_id)
    run_id = _create_partial_run(collection["id"], target_id, [1])
    _mock_list_metadata()
    respx.get(f"{BASE}/lists/42/items").mock(return_value=_items_response([1]))

    response = client.post(f"/api/runs/{run_id}/resume", headers=admin)
    assert response.status_code == 202, response.text
    new_run_id = response.json()["run_id"]
    assert new_run_id != run_id
    new_run = client.get(f"/api/runs/{new_run_id}").json()
    assert new_run["status"] == "SUCCEEDED", new_run
    assert new_run["parent_run_id"] == run_id


def test_binding_and_run_lists_and_missing_preview(client, admin, seeded, app_settings) -> None:
    _set_mdblist_credential(app_settings)
    collection = _collection(client, "netflix-movie")
    _create_snapshot(collection["id"], [1])
    target_id = _create_target()
    binding = _create_binding(client, admin, collection["id"], target_id)

    bindings = client.get("/api/bindings").json()
    assert bindings["total"] == 1
    assert bindings["items"][0]["collection"]["id"] == collection["id"]
    assert bindings["items"][0]["target"]["remote_list_id"] == "42"

    detail = client.get(f"/api/bindings/{binding['id']}").json()
    assert detail["mode"] == "MIRROR"
    assert detail["thresholds"]["max_removal_abs"] == 100

    runs = client.get("/api/runs").json()
    assert runs["total"] == 0
    assert runs["items"] == []

    missing = client.get(f"/api/previews/{uuid.uuid4()}")
    assert missing.status_code == 404


@respx.mock
def test_patch_binding_updates_schedule_thresholds_and_visibility(
    client, admin, seeded, app_settings
) -> None:
    _set_mdblist_credential(app_settings)
    collection = _collection(client, "netflix-movie")
    _create_snapshot(collection["id"], [1, 2])
    target_id = _create_target()
    binding = _create_binding(client, admin, collection["id"], target_id)
    respx.put(f"{BASE}/lists/42").mock(
        return_value=httpx.Response(
            200,
            json={"success": True, "id": 42, "name": "Test list", "private": True},
        )
    )

    response = client.patch(
        f"/api/bindings/{binding['id']}",
        json={
            "mode": "APPEND_ONLY",
            "schedule": "INTERVAL",
            "schedule_interval_hours": 6,
            "max_remove_count": 3,
            "max_remove_percent": 5,
            "target_private": True,
        },
        headers=admin,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["mode"] == "APPEND_ONLY"
    assert body["schedule"] == "INTERVAL"
    assert body["schedule_interval_hours"] == 6
    assert body["max_remove_count"] == 3
    assert body["max_remove_percent"] == 5
    assert body["target"]["private"] is True
    assert body["next_run_at"] is not None


@respx.mock
def test_patch_binding_rejects_invalid_cron_and_zero_mirror_thresholds(
    client, admin, seeded, app_settings
) -> None:
    _set_mdblist_credential(app_settings)
    collection = _collection(client, "netflix-movie")
    _create_snapshot(collection["id"], [1])
    target_id = _create_target()
    binding = _create_binding(client, admin, collection["id"], target_id)

    invalid_cron = client.patch(
        f"/api/bindings/{binding['id']}",
        json={"schedule": "CRON", "schedule_cron": "not a cron"},
        headers=admin,
    )
    assert invalid_cron.status_code == 422
    assert invalid_cron.json()["error"]["code"] == "INVALID_CRON"

    zero_thresholds = client.patch(
        f"/api/bindings/{binding['id']}",
        json={"mode": "MIRROR", "max_remove_count": 0, "max_remove_percent": 0},
        headers=admin,
    )
    assert zero_thresholds.status_code == 422
    assert zero_thresholds.json()["error"]["code"] == "THRESHOLDS_REQUIRED"


@respx.mock
def test_patch_binding_enable_requires_policy(client, admin, seeded, app_settings) -> None:
    _set_mdblist_credential(app_settings)
    collection = _collection(client, "netflix-movie")
    _create_snapshot(collection["id"], [1])
    target_id = _create_target()
    binding = _create_binding(
        client,
        admin,
        collection["id"],
        target_id,
        enabled=False,
        policy_version=None,
    )

    response = client.patch(
        f"/api/bindings/{binding['id']}",
        json={"enabled": True},
        headers=admin,
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "POLICY_NOT_ACCEPTED"


@respx.mock
def test_mirror_removal_threshold_blocks_before_any_remove(
    client, admin, seeded, app_settings
) -> None:
    _set_mdblist_credential(app_settings)
    collection = _collection(client, "netflix-movie")
    _create_snapshot(collection["id"], [1, 2, 3])
    target_id = _create_target()
    binding = _create_binding(
        client,
        admin,
        collection["id"],
        target_id,
        thresholds={
            "max_removal_pct": 100,
            "max_removal_abs": 1,
            "max_addition_pct": 100,
        },
    )
    _mock_list_metadata()
    respx.get(f"{BASE}/lists/42/items").mock(
        side_effect=[
            _items_response([1, 2, 3, 4, 5]),
            _items_response([1, 2, 3, 4, 5]),
            _items_response([1, 2, 3, 4, 5]),
            _items_response([1, 2, 3]),
        ]
    )
    remove_route = respx.post(f"{BASE}/lists/42/items/remove").mock(
        return_value=httpx.Response(200, json={"removed": {"movies": 2}})
    )

    started = client.post(
        f"/api/bindings/{binding['id']}/runs",
        json={"dry_run": False},
        headers=admin,
    )
    assert started.status_code == 202, started.text
    run_id = started.json()["run_id"]
    run = client.get(f"/api/runs/{run_id}").json()
    assert run["status"] == "AWAITING_APPROVAL"
    assert run["to_remove_count"] == 2
    assert run["threshold_breached"] is True
    assert remove_route.called is False

    approved = client.post(
        f"/api/runs/{run_id}/approve",
        json={"plan_hash": run["plan_hash"]},
        headers=admin,
    )
    assert approved.status_code == 202, approved.text
    final = client.get(f"/api/runs/{run_id}").json()
    assert final["status"] == "SUCCEEDED", final
    assert final["removed_count"] == 2
    assert remove_route.called


@respx.mock
def test_runs_filter_by_provider_status_and_media_type(client, admin, seeded, app_settings) -> None:
    _set_mdblist_credential(app_settings)
    collection = _collection(client, "netflix-movie")
    _create_snapshot(collection["id"], [1])
    target_id = _create_target()
    binding = _create_binding(client, admin, collection["id"], target_id)
    _mock_list_metadata()
    respx.get(f"{BASE}/lists/42/items").mock(return_value=_items_response([1]))

    started = client.post(
        f"/api/bindings/{binding['id']}/runs",
        json={"dry_run": True},
        headers=admin,
    )
    assert started.status_code == 202, started.text
    run_id = started.json()["run_id"]
    assert client.get(f"/api/runs/{run_id}").json()["status"] == "SUCCEEDED"

    by_provider = client.get(
        f"/api/runs?provider_id={collection['provider_id']}", headers=admin
    ).json()
    assert by_provider["total"] == 1
    assert by_provider["items"][0]["provider_name"] == "Netflix"

    by_media = client.get("/api/runs?media_type=SHOW", headers=admin).json()
    assert by_media["total"] == 0

    by_status = client.get("/api/runs?status=SUCCEEDED", headers=admin).json()
    assert by_status["total"] >= 1
