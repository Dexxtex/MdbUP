"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-01-01 00:00:00

Scelta di implementazione
-------------------------
Lo schema è definito una sola volta, nei modelli SQLAlchemy di ``app/db/models``.
Questa revisione usa ``Base.metadata.create_all`` / ``drop_all`` invece di
centinaia di righe di ``op.create_table``: così SQLite (test) e PostgreSQL
(produzione) producono esattamente lo stesso schema e non possono divergere dai
modelli. Le revisioni successive devono usare operazioni Alembic esplicite.

Differenze note rispetto a ``docs/phase1/schema.sql`` (DDL di riferimento):

* niente estensioni ``pgcrypto``/``citext``: le PK UUID sono generate in Python
  (``uuid4``) e le email sono normalizzate in minuscolo dal repository;
* ``offer_types`` è ``JSON`` invece di ``TEXT[]`` per portabilità;
* ``metadata`` JSONB è ``JSON``;
* i due riferimenti differibili ``collection.last_valid_snapshot_id`` e
  ``sync_binding.last_run_id`` sono colonne senza FK, perché la FK incrociata
  crea un ciclo di tabelle che ``create_all`` non può ordinare su SQLite. Sono
  mantenuti dal servizio applicativo;
* i trigger ``*_touch`` sono sostituiti da ``updated_at`` gestito dall'ORM;
  ``audit_log`` resta append-only a livello applicativo;
* la tabella ``session`` si chiama ``user_session`` e la colonna
  ``sync_run.trigger`` si chiama ``trigger_type`` (parole riservate SQL).
"""

from __future__ import annotations

from alembic import op

from app.db import models  # noqa: F401  (registers every table on Base.metadata)
from app.db.base import Base

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
