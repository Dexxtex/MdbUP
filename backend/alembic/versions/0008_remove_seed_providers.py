"""remove unused demo providers

Revision ID: 0008_remove_seed_providers
Revises: 0007_remove_seed_collections
Create Date: 2026-11-20

Existing installations still contain the twelve demo providers inserted by the
old bootstrap. They are removed only when no collection references them:
a provider may still be needed by an operator-created collection, and the
database must never lose that relation silently.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa

from alembic import op

revision = "0008_remove_seed_providers"
down_revision = "0007_remove_seed_collections"
branch_labels = None
depends_on = None

PROVIDER = "provider"
MAPPING = "provider_mapping"
COLLECTION = "collection"
SEED_SLUGS = (
    "netflix",
    "prime-video",
    "disney-plus",
    "now",
    "timvision",
    "infinity-plus",
    "rakuten-tv",
    "mubi",
    "apple-tv-plus",
    "paramount-plus",
    "raiplay",
    "mediaset-infinity",
)


def _has_table(bind: sa.engine.Connection, name: str) -> bool:
    return sa.inspect(bind).has_table(name)


def _has_collection(bind: sa.engine.Connection, provider_id: Any) -> bool:
    if not _has_table(bind, COLLECTION):
        return False
    return (
        bind.execute(
            sa.text(f"SELECT 1 FROM {COLLECTION} WHERE provider_id = :provider_id LIMIT 1"),
            {"provider_id": provider_id},
        ).first()
        is not None
    )


def _delete_provider(bind: sa.engine.Connection, provider_id: Any) -> None:
    if _has_table(bind, MAPPING):
        bind.execute(
            sa.text(f"DELETE FROM {MAPPING} WHERE provider_id = :provider_id"),
            {"provider_id": provider_id},
        )
    bind.execute(
        sa.text(f"DELETE FROM {PROVIDER} WHERE id = :provider_id"),
        {"provider_id": provider_id},
    )


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_table(bind, PROVIDER):
        return
    placeholders = ", ".join(f":slug_{index}" for index in range(len(SEED_SLUGS)))
    params = {f"slug_{index}": slug for index, slug in enumerate(SEED_SLUGS)}
    rows = list(
        bind.execute(
            sa.text(f"SELECT id, slug FROM {PROVIDER} WHERE slug IN ({placeholders})"),
            params,
        ).mappings()
    )
    for row in rows:
        if _has_collection(bind, row.id):
            continue
        _delete_provider(bind, row.id)


def downgrade() -> None:
    # Demo providers are intentionally not recreated.
    return
