"""notifications and run notification marker

Revision ID: 0003_notifications
Revises: 0002_binding_schedule_interval
Create Date: 2026-11-18 00:00:00

``0001_initial`` uses ``Base.metadata.create_all`` with the current models, so a
fresh database already contains the notification table and the
``sync_run.notified_at`` column. This revision is idempotent for existing
databases created before the model change.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_notifications"
down_revision = "0002_binding_schedule_interval"
branch_labels = None
depends_on = None

TABLE = "notification_channel"
RUN_TABLE = "sync_run"
COLUMN = "notified_at"
INDEX = "run_notification_idx"


def _has_table(bind: sa.engine.Connection, name: str) -> bool:
    return sa.inspect(bind).has_table(name)


def _has_column(bind: sa.engine.Connection, table: str, name: str) -> bool:
    return name in {column["name"] for column in sa.inspect(bind).get_columns(table)}


def _has_index(bind: sa.engine.Connection, table: str, name: str) -> bool:
    return name in {index["name"] for index in sa.inspect(bind).get_indexes(table)}


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_table(bind, TABLE):
        op.create_table(
            TABLE,
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("kind", sa.String(length=16), nullable=False),
            sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("events", sa.JSON(), nullable=False),
            sa.Column("config", sa.JSON(), nullable=False),
            sa.Column("secret_ciphertext", sa.LargeBinary(), nullable=True),
            sa.Column("secret_nonce", sa.LargeBinary(), nullable=True),
            sa.Column("secret_algorithm", sa.String(length=32), nullable=False),
            sa.Column("secret_key_version", sa.SmallInteger(), nullable=True),
            sa.Column("secret_masked_hint", sa.String(length=32), nullable=True),
            sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_status", sa.String(length=16), nullable=True),
            sa.Column("last_error", sa.String(length=1000), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.CheckConstraint(
                "kind IN ('WEBHOOK', 'TELEGRAM', 'DISCORD')",
                name="ck_notification_channel_kind_valid",
            ),
            sa.CheckConstraint(
                "last_status IS NULL OR last_status IN ('SENT', 'FAILED')",
                name="ck_notification_channel_last_status_valid",
            ),
            sa.UniqueConstraint("name", name="uq_notification_channel_name"),
        )
    if not _has_column(bind, RUN_TABLE, COLUMN):
        op.add_column(RUN_TABLE, sa.Column(COLUMN, sa.DateTime(timezone=True), nullable=True))
    if not _has_index(bind, RUN_TABLE, INDEX):
        op.create_index(INDEX, RUN_TABLE, ["status", COLUMN])
    # Do not replay the whole run history when the first channel is created.
    op.execute(
        sa.text(
            f"UPDATE {RUN_TABLE} SET {COLUMN} = updated_at WHERE {COLUMN} IS NULL"
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    if _has_index(bind, RUN_TABLE, INDEX):
        op.drop_index(INDEX, table_name=RUN_TABLE)
    if bind.dialect.name == "postgresql" and _has_column(bind, RUN_TABLE, COLUMN):
        op.drop_column(RUN_TABLE, COLUMN)
    if _has_table(bind, TABLE):
        op.drop_table(TABLE)
