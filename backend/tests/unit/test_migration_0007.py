"""Migration 0007: remove only unused demo collections."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

MIGRATION_PATH = (
    Path(__file__).resolve().parents[2] / "alembic" / "versions" / "0007_remove_seed_collections.py"
)
DDL = """
CREATE TABLE collection (
    id VARCHAR(32) PRIMARY KEY,
    quality_flags TEXT NOT NULL,
    source_collection_key VARCHAR(200)
);
CREATE TABLE sync_binding (
    id VARCHAR(32) PRIMARY KEY,
    collection_id VARCHAR(32) NOT NULL
);
CREATE TABLE collection_snapshot (
    id VARCHAR(32) PRIMARY KEY,
    collection_id VARCHAR(32) NOT NULL
);
"""


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("migration_0007", MIGRATION_PATH)
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
    assert module.revision == "0007_remove_seed_collections"
    assert len(module.revision) <= 32
    assert module.down_revision == "0006_snapshot_dedup"


def test_upgrade_removes_only_unbound_seed_collections(tmp_path) -> None:
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    seed_flags = '{"unverified_provider_mapping": true, "added_date_missing": true}'
    with engine.begin() as connection:
        for statement in DDL.split(";"):
            if statement.strip():
                connection.execute(sa.text(statement))
        connection.execute(
            sa.text(
                "INSERT INTO collection (id, quality_flags, source_collection_key) VALUES "
                "('seed-unbound', :flags, '8:MOVIE'), "
                "('seed-bound', :flags, '119:MOVIE'), "
                "('user-custom', :flags, 'custom:my-list'), "
                "('user-normal', '{}', '8:MOVIE')"
            ),
            {"flags": seed_flags},
        )
        connection.execute(
            sa.text("INSERT INTO sync_binding (id, collection_id) VALUES ('b1', 'seed-bound')")
        )
        connection.execute(
            sa.text(
                "INSERT INTO collection_snapshot (id, collection_id) VALUES ('s1', 'seed-unbound')"
            )
        )
    module = _load_migration()

    _upgrade(engine, module)
    _upgrade(engine, module)

    with engine.connect() as connection:
        ids = {row[0] for row in connection.execute(sa.text("SELECT id FROM collection")).all()}
    assert ids == {"seed-bound", "user-custom", "user-normal"}
