"""Migration 0008: remove only seed providers without collections."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

MIGRATION_PATH = (
    Path(__file__).resolve().parents[2] / "alembic" / "versions" / "0008_remove_seed_providers.py"
)
DDL = """
CREATE TABLE provider (id VARCHAR(32) PRIMARY KEY, slug VARCHAR(64) NOT NULL);
CREATE TABLE collection (id VARCHAR(32) PRIMARY KEY, provider_id VARCHAR(32));
CREATE TABLE provider_mapping (
    id VARCHAR(32) PRIMARY KEY,
    provider_id VARCHAR(32) NOT NULL
);
"""


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("migration_0008", MIGRATION_PATH)
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
    assert module.revision == "0008_remove_seed_providers"
    assert module.down_revision == "0007_remove_seed_collections"


def test_upgrade_removes_only_unreferenced_seed_providers(tmp_path) -> None:
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as connection:
        for statement in DDL.split(";"):
            if statement.strip():
                connection.execute(sa.text(statement))
        connection.execute(
            sa.text(
                "INSERT INTO provider (id, slug) VALUES "
                "('p-unused', 'netflix'), ('p-used', 'mubi'), ('p-custom', 'my-service')"
            )
        )
        connection.execute(
            sa.text("INSERT INTO collection (id, provider_id) VALUES ('c1', 'p-used')")
        )
        connection.execute(
            sa.text("INSERT INTO provider_mapping (id, provider_id) VALUES ('m1', 'p-unused')")
        )
    module = _load_migration()

    _upgrade(engine, module)
    _upgrade(engine, module)

    with engine.connect() as connection:
        ids = {row[0] for row in connection.execute(sa.text("SELECT id FROM provider"))}
    assert ids == {"p-used", "p-custom"}
