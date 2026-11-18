"""Migration 0005: snapshot item availability is added once and stays nullable."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "0005_snapshot_item_availability.py"
)
LEGACY_DDL = """
CREATE TABLE snapshot_item (
    id CHAR(32) PRIMARY KEY,
    snapshot_id CHAR(32) NOT NULL,
    media_id CHAR(32),
    position INTEGER NOT NULL,
    date_basis VARCHAR(32) NOT NULL,
    resolution_status VARCHAR(16) NOT NULL
)
"""


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("migration_0005", MIGRATION_PATH)
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
    assert module.revision == "0005_snapshot_item_availability"
    assert len(module.revision) <= 32
    assert module.down_revision == "0004_notification_retry"


def test_upgrade_adds_a_nullable_column_idempotently(tmp_path) -> None:
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as connection:
        connection.execute(sa.text(LEGACY_DDL))
    module = _load_migration()

    _upgrade(engine, module)
    _upgrade(engine, module)

    columns = {column["name"]: column for column in sa.inspect(engine).get_columns("snapshot_item")}
    assert "availability_status" in columns
    assert columns["availability_status"]["nullable"] is True
