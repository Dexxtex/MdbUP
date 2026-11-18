"""snapshot item availability status

Revision ID: 0005_snapshot_item_availability
Revises: 0004_notification_retry
Create Date: 2026-11-18 12:00:00

``snapshot_item.availability_status`` is nullable: TMDb and manual CSV declare no
availability state, so only sources that publish one (JustWatch) fill it with
``CURRENT``/``UPCOMING``/``LEAVING``.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005_snapshot_item_availability"
down_revision = "0004_notification_retry"
branch_labels = None
depends_on = None

TABLE = "snapshot_item"
COLUMN = "availability_status"
CHECK = "snapshot_item_availability_status_valid"


def _has_table(bind: sa.engine.Connection, name: str) -> bool:
    return sa.inspect(bind).has_table(name)


def _has_column(bind: sa.engine.Connection, table: str, name: str) -> bool:
    return name in {column["name"] for column in sa.inspect(bind).get_columns(table)}


def _has_check(bind: sa.engine.Connection, table: str, name: str) -> bool:
    return name in {
        constraint["name"] for constraint in sa.inspect(bind).get_check_constraints(table)
    }


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_table(bind, TABLE):
        # A database without the table is created by 0001_initial from the models.
        return
    if not _has_column(bind, TABLE, COLUMN):
        op.add_column(TABLE, sa.Column(COLUMN, sa.String(length=16), nullable=True))
    # SQLite cannot add a table constraint after creation; on PostgreSQL the
    # constraint is added so the column keeps the same domain as the model.
    if bind.dialect.name == "postgresql" and not _has_check(bind, TABLE, CHECK):
        op.create_check_constraint(
            CHECK,
            TABLE,
            f"{COLUMN} IS NULL OR {COLUMN} IN ('CURRENT', 'UPCOMING', 'LEAVING')",
        )


def downgrade() -> None:
    bind = op.get_bind()
    if not _has_table(bind, TABLE):
        return
    if bind.dialect.name == "postgresql" and _has_check(bind, TABLE, CHECK):
        op.drop_constraint(CHECK, TABLE, type_="check")
    # SQLite cannot drop a column in place: its schema is recreated by
    # ``0001_initial`` from the models.
    if bind.dialect.name != "postgresql":
        return
    if _has_column(bind, TABLE, COLUMN):
        op.drop_column(TABLE, COLUMN)
