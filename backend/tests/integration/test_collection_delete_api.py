"""Delete one collection without touching its provider or remote MDBList lists."""

from __future__ import annotations

import uuid

from app.core.time import utcnow
from app.db.models import SyncRun
from app.db.session import get_session_factory
from app.services.seed import seed_sources
from tests.integration.factories import (
    assert_episode_events_detached,
    assert_local_history_deleted,
    attach_local_history,
    provider_with_collection,
)


def test_delete_collection_removes_local_history_but_keeps_provider(client, admin) -> None:
    assert seed_sources() == 0
    provider, collection = provider_with_collection(client, admin)
    ids = attach_local_history(provider["id"], collection["id"], run_status="SUCCEEDED")

    response = client.delete(f"/api/collections/{collection['id']}", headers=admin)

    assert response.status_code == 204, response.text
    assert client.get(f"/api/collections/{collection['id']}").status_code == 404
    assert client.get("/api/collections").json()["total"] == 0
    assert client.get(f"/api/providers/{provider['id']}").json()["collections_count"] == 0
    assert_local_history_deleted(ids)
    assert_episode_events_detached()


def test_delete_collection_is_blocked_while_a_run_is_active(client, admin) -> None:
    assert seed_sources() == 0
    provider, collection = provider_with_collection(client, admin)
    ids = attach_local_history(provider["id"], collection["id"], run_status="APPLYING")

    response = client.delete(f"/api/collections/{collection['id']}", headers=admin)

    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "COLLECTION_RUN_ACTIVE"
    assert client.get(f"/api/collections/{collection['id']}").status_code == 200

    session = get_session_factory()()
    try:
        run = session.get(SyncRun, uuid.UUID(ids["run"]))
        assert run is not None
        run.status = "CANCELLED"
        run.finished_at = utcnow()
        session.commit()
    finally:
        session.close()

    deleted = client.delete(f"/api/collections/{collection['id']}", headers=admin)
    assert deleted.status_code == 204, deleted.text
    assert client.get(f"/api/collections/{collection['id']}").status_code == 404
