"""notification retry state

Revision ID: 0004_notification_retry
Revises: 0003_notifications
Create Date: 2026-11-18 12:00:00

``0001_initial`` uses ``Base.metadata.create_all`` with the current models, so a
fresh database already contains these columns and the retry index. This
revision is idempotent for databases created before the model change: it only
adds what is missing.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_notification_retry"
down_revision = "0003_notifications"
branch_labels = None
depends_on = None

TABLE = "notification_channel"
INDEX = "notification_retry_idx"
COLUMNS = (
    ("retry_count", sa.Integer(), False, "0"),
    ("next_retry_at", sa.DateTime(timezone=True), True, None),
    ("last_event", sa.String(length=32), True, None),
    ("last_payload", sa.JSON(), True, None),
)


def _has_table(bind: sa.engine.Connection, name: str) -> bool:
    return sa.inspect(bind).has_table(name)


def _has_column(bind: sa.engine.Connection, table: str, name: str) -> bool:
    return name in {column["name"] for column in sa.inspect(bind).get_columns(table)}


def _has_index(bind: sa.engine.Connection, table: str, name: str) -> bool:
    return name in {index["name"] for index in sa.inspect(bind).get_indexes(table)}


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_table(bind, TABLE):
        # A database without the notification table is created by 0001_initial.
        return
    for name, type_, nullable, server_default in COLUMNS:
        if _has_column(bind, TABLE, name):
            continue
        op.add_column(
            TABLE,
            sa.Column(name, type_, nullable=nullable, server_default=server_default),
        )
    if not _has_index(bind, TABLE, INDEX):
        op.create_index(INDEX, TABLE, ["last_status", "next_retry_at"])


def downgrade() -> None:
    bind = op.get_bind()
    if not _has_table(bind, TABLE):
        return
    if _has_index(bind, TABLE, INDEX):
        op.drop_index(INDEX, table_name=TABLE)
    # SQLite cannot drop a column referenced by an index or a CHECK constraint;
    # its schema is a test artefact recreated by ``0001_initial`` on downgrade.
    if bind.dialect.name != "postgresql":
        return
    for name, _type, _nullable, _server_default in reversed(COLUMNS):
        if _has_column(bind, TABLE, name):
            op.drop_column(TABLE, name)
