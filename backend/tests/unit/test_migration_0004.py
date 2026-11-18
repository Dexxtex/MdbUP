"""Migration 0004: retry columns are added once and the revision id fits."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

MIGRATION_PATH = (
    Path(__file__).resolve().parents[2] / "alembic" / "versions" / "0004_notification_retry.py"
)
LEGACY_DDL = """
CREATE TABLE notification_channel (
    id CHAR(32) PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    kind VARCHAR(16) NOT NULL,
    last_status VARCHAR(16),
    last_error VARCHAR(1000)
)
"""


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("migration_0004", MIGRATION_PATH)
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
    assert module.revision == "0004_notification_retry"
    assert len(module.revision) <= 32
    assert module.down_revision == "0003_notifications"


def test_upgrade_adds_the_retry_columns_idempotently(tmp_path) -> None:
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as connection:
        connection.execute(sa.text(LEGACY_DDL))
    module = _load_migration()

    _upgrade(engine, module)
    _upgrade(engine, module)

    columns = {column["name"] for column in sa.inspect(engine).get_columns("notification_channel")}
    assert {"retry_count", "next_retry_at", "last_event", "last_payload"} <= columns
    indexes = {index["name"] for index in sa.inspect(engine).get_indexes("notification_channel")}
    assert "notification_retry_idx" in indexes
    engine.dispose()


def test_upgrade_without_the_table_is_a_noop(tmp_path) -> None:
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'empty.db'}")
    module = _load_migration()

    _upgrade(engine, module)

    assert sa.inspect(engine).has_table("notification_channel") is False
    engine.dispose()
