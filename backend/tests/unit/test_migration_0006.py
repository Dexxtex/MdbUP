"""Migration 0006: snapshot dedup columns are additive and idempotent."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

MIGRATION_PATH = (
    Path(__file__).resolve().parents[2] / "alembic" / "versions" / "0006_snapshot_dedup.py"
)
LEGACY_DDL = """
CREATE TABLE collection_snapshot (
    id CHAR(32) PRIMARY KEY,
    collection_id CHAR(32) NOT NULL,
    status VARCHAR(16) NOT NULL,
    quality VARCHAR(16) NOT NULL,
    is_valid BOOLEAN NOT NULL,
    started_at DATETIME NOT NULL,
    finished_at DATETIME,
    checksum VARCHAR(128)
)
"""


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("migration_0006", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _upgrade(engine: sa.Engine, module: ModuleType) -> None:
    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            module.upgrade()
        connection.commit()


def test_revision_id_and_chain() -> None:
    module = _load_migration()
    assert module.revision == "0006_snapshot_dedup"
    assert len(module.revision) <= 32
    assert module.down_revision == "0005_snapshot_item_availability"


def test_upgrade_adds_columns_and_index_idempotently(tmp_path) -> None:
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as connection:
        connection.execute(sa.text(LEGACY_DDL))
        connection.execute(
            sa.text(
                "INSERT INTO collection_snapshot "
                "(id, collection_id, status, quality, is_valid, started_at, finished_at) "
                "VALUES ('s1', 'c1', 'COMPLETE', 'CLEAN', 1, "
                "'2026-01-01 00:00:00', '2026-01-01 00:01:00')"
            )
        )
    module = _load_migration()

    _upgrade(engine, module)
    _upgrade(engine, module)

    columns = {
        column["name"]: column for column in sa.inspect(engine).get_columns("collection_snapshot")
    }
    assert columns["items_from_snapshot_id"]["nullable"] is True
    assert columns["last_verified_at"]["nullable"] is True
    indexes = {index["name"] for index in sa.inspect(engine).get_indexes("collection_snapshot")}
    assert "snapshot_items_source_idx" in indexes
    with engine.connect() as connection:
        value = connection.execute(
            sa.text("SELECT last_verified_at FROM collection_snapshot WHERE id='s1'")
        ).scalar()
    assert value is not None
