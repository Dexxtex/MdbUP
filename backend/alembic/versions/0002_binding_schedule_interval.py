"""binding schedule interval

Revision ID: 0002_binding_schedule_interval
Revises: 0001_initial
Create Date: 2026-11-17 00:00:00

The first revision uses ``Base.metadata.create_all`` with the *current* models,
so a fresh database already contains this column. The migration is therefore
idempotent: it adds the column only when an existing database (created before
this model change) does not have it yet.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_binding_schedule_interval"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

COLUMN = "schedule_interval_hours"
TABLE = "sync_binding"
# (logical name passed to Alembic, actual name after the metadata naming
# convention, SQL condition). Alembic applies ``ck_<table>_<name>`` itself.
CHECKS = (
    (
        "schedule_interval_positive",
        "ck_sync_binding_schedule_interval_positive",
        "schedule_interval_hours IS NULL OR schedule_interval_hours > 0",
    ),
    (
        "schedule_one_kind",
        "ck_sync_binding_schedule_one_kind",
        "schedule_cron = '' OR schedule_interval_hours IS NULL",
    ),
)


def _column_exists(bind: sa.engine.Connection) -> bool:
    inspector = sa.inspect(bind)
    return COLUMN in {column["name"] for column in inspector.get_columns(TABLE)}


def _check_exists(bind: sa.engine.Connection, name: str) -> bool:
    inspector = sa.inspect(bind)
    try:
        constraints = inspector.get_check_constraints(TABLE)
    except NotImplementedError:  # pragma: no cover - dialect without introspection
        return False
    return name in {constraint.get("name") for constraint in constraints}


def upgrade() -> None:
    bind = op.get_bind()
    if not _column_exists(bind):
        op.add_column(TABLE, sa.Column(COLUMN, sa.Integer(), nullable=True))
    # SQLite cannot add table constraints with ALTER TABLE; fresh test databases
    # get them from the SQLAlchemy model via 0001_initial.
    if bind.dialect.name == "postgresql":
        for logical_name, actual_name, condition in CHECKS:
            if not _check_exists(bind, actual_name):
                op.create_check_constraint(logical_name, TABLE, condition)


def downgrade() -> None:
    bind = op.get_bind()
    # SQLite cannot drop a column referenced by a CHECK constraint. The
    # SQLite database is a test/development artefact and ``0001_initial``
    # drops the whole table on ``downgrade base``; leaving the column here is
    # safer than rewriting the table with PRAGMA writable_schema.
    if bind.dialect.name != "postgresql":
        return
    for logical_name, actual_name, _condition in CHECKS:
        if _check_exists(bind, actual_name):
            op.drop_constraint(logical_name, TABLE, type_="check")
    if _column_exists(bind):
        op.drop_column(TABLE, COLUMN)
