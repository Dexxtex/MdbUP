"""snapshot item reuse and verification timestamp

Revision ID: 0006_snapshot_dedup
Revises: 0005_snapshot_item_availability
Create Date: 2026-11-18 12:30:00

A daily acquisition that produces the same normalized title set reuses the
previous snapshot items. ``items_from_snapshot_id`` points at the owning rows
and ``last_verified_at`` keeps every verification in the snapshot history
without duplicating thousands of ``snapshot_item`` rows.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_snapshot_dedup"
down_revision = "0005_snapshot_item_availability"
branch_labels = None
depends_on = None

TABLE = "collection_snapshot"
ITEMS_COLUMN = "items_from_snapshot_id"
VERIFIED_COLUMN = "last_verified_at"
INDEX = "snapshot_items_source_idx"
FK = "fk_collection_snapshot_items_source"


def _has_table(bind: sa.engine.Connection, name: str) -> bool:
    return sa.inspect(bind).has_table(name)


def _has_column(bind: sa.engine.Connection, table: str, name: str) -> bool:
    return name in {column["name"] for column in sa.inspect(bind).get_columns(table)}


def _has_index(bind: sa.engine.Connection, table: str, name: str) -> bool:
    return name in {index["name"] for index in sa.inspect(bind).get_indexes(table)}


def _has_fk(bind: sa.engine.Connection, table: str, name: str) -> bool:
    for fk in sa.inspect(bind).get_foreign_keys(table):
        if fk.get("name") == name or fk.get("constrained_columns") == [ITEMS_COLUMN]:
            return True
    return False


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_table(bind, TABLE):
        return
    if not _has_column(bind, TABLE, ITEMS_COLUMN):
        op.add_column(TABLE, sa.Column(ITEMS_COLUMN, sa.Uuid(), nullable=True))
    if not _has_column(bind, TABLE, VERIFIED_COLUMN):
        op.add_column(
            TABLE,
            sa.Column(VERIFIED_COLUMN, sa.DateTime(timezone=True), nullable=True),
        )
        op.execute(
            sa.text(
                f"UPDATE {TABLE} SET {VERIFIED_COLUMN} = "
                "COALESCE(finished_at, started_at)"
            )
        )
    if not _has_index(bind, TABLE, INDEX):
        op.create_index(INDEX, TABLE, [ITEMS_COLUMN])
    if bind.dialect.name == "postgresql" and not _has_fk(bind, TABLE, FK):
        op.create_foreign_key(
            FK,
            TABLE,
            TABLE,
            [ITEMS_COLUMN],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    bind = op.get_bind()
    if not _has_table(bind, TABLE):
        return
    if bind.dialect.name == "postgresql" and _has_fk(bind, TABLE, FK):
        op.drop_constraint(FK, TABLE, type_="foreignkey")
    if _has_index(bind, TABLE, INDEX):
        op.drop_index(INDEX, table_name=TABLE)
    if bind.dialect.name != "postgresql":
        return
    if _has_column(bind, TABLE, ITEMS_COLUMN):
        op.drop_column(TABLE, ITEMS_COLUMN)
    if _has_column(bind, TABLE, VERIFIED_COLUMN):
        op.drop_column(TABLE, VERIFIED_COLUMN)
