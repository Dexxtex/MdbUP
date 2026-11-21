"""remove unused demo collections

Revision ID: 0007_remove_seed_collections
Revises: 0006_snapshot_dedup
Create Date: 2026-11-20

The first bootstrap seeded 23 TMDb catalog collections as demo data. They are
not created by the current startup path anymore, but existing databases keep
them. This migration removes only demo collections that no binding uses:
bound collections are left untouched because deleting them would cascade into
active scheduling/run history.

The predicate is intentionally narrow: the collection must carry the seed's
``unverified_provider_mapping`` quality flag and a real (non-``custom:``)
source key. A user-created collection never has that combination.
"""

from __future__ import annotations

import json
from typing import Any

import sqlalchemy as sa

from alembic import op

revision = "0007_remove_seed_collections"
down_revision = "0006_snapshot_dedup"
branch_labels = None
depends_on = None

COLLECTION = "collection"
SNAPSHOT = "collection_snapshot"
BINDING = "sync_binding"
EPISODE_EVENT = "episode_event"


def _has_table(bind: sa.engine.Connection, name: str) -> bool:
    return sa.inspect(bind).has_table(name)


def _as_flags(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except ValueError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _is_seed_collection(row: Any) -> bool:
    flags = _as_flags(row.quality_flags)
    source_key = row.source_collection_key
    return bool(
        flags.get("unverified_provider_mapping")
        and source_key
        and not str(source_key).startswith("custom:")
    )


def _is_bound(bind: sa.engine.Connection, collection_id: Any) -> bool:
    if not _has_table(bind, BINDING):
        return False
    return (
        bind.execute(
            sa.text(f"SELECT 1 FROM {BINDING} WHERE collection_id = :collection_id LIMIT 1"),
            {"collection_id": collection_id},
        ).first()
        is not None
    )


def _delete_collection(bind: sa.engine.Connection, collection_id: Any) -> None:
    # PostgreSQL cascades snapshots; delete them explicitly too so the same
    # migration is deterministic on SQLite test databases.
    if _has_table(bind, SNAPSHOT):
        if _has_table(bind, EPISODE_EVENT):
            bind.execute(
                sa.text(
                    f"UPDATE {EPISODE_EVENT} SET snapshot_id = NULL "
                    f"WHERE snapshot_id IN (SELECT id FROM {SNAPSHOT} "
                    "WHERE collection_id = :collection_id)"
                ),
                {"collection_id": collection_id},
            )
        bind.execute(
            sa.text(f"DELETE FROM {SNAPSHOT} WHERE collection_id = :collection_id"),
            {"collection_id": collection_id},
        )
    bind.execute(
        sa.text(f"DELETE FROM {COLLECTION} WHERE id = :collection_id"),
        {"collection_id": collection_id},
    )


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_table(bind, COLLECTION):
        return
    rows = list(
        bind.execute(
            sa.text(f"SELECT id, quality_flags, source_collection_key FROM {COLLECTION}")
        ).mappings()
    )
    for row in rows:
        if not _is_seed_collection(row):
            continue
        # A bound collection is still attached to an operator-owned list: never
        # remove it implicitly. The operator can delete it explicitly.
        if _is_bound(bind, row.id):
            continue
        _delete_collection(bind, row.id)


def downgrade() -> None:
    # The removed demo rows are not needed to roll back schema changes.
    return
