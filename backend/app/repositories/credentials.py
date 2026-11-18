"""Encrypted credential persistence. Only ciphertext is ever stored."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.db.models import Credential, Source


def get_credential(
    db: Session, *, scope: str, source_id: uuid.UUID | None, key: str
) -> Credential | None:
    """Find a credential by its unique (scope, source_id, key) identity."""
    stmt = select(Credential).where(Credential.scope == scope, Credential.key == key)
    stmt = stmt.where(
        Credential.source_id.is_(None) if source_id is None else Credential.source_id == source_id
    )
    return db.scalar(stmt)


def list_credentials(db: Session) -> list[Credential]:
    return list(db.scalars(select(Credential).order_by(Credential.scope, Credential.key)).all())


def upsert_credential(
    db: Session,
    *,
    scope: str,
    source_id: uuid.UUID | None,
    key: str,
    ciphertext: bytes,
    nonce: bytes,
    algorithm: str,
    key_version: int,
    masked_hint: str,
) -> Credential:
    """Insert or replace the encrypted material of a credential."""
    credential = get_credential(db, scope=scope, source_id=source_id, key=key)
    if credential is None:
        credential = Credential(scope=scope, source_id=source_id, key=key)
        db.add(credential)
    credential.ciphertext = ciphertext
    credential.nonce = nonce
    credential.algorithm = algorithm
    credential.key_version = key_version
    credential.masked_hint = masked_hint
    credential.last_verified_at = None
    db.flush()
    return credential


def delete_credential(db: Session, credential: Credential) -> None:
    db.delete(credential)
    db.flush()


def mark_verified(db: Session, credential: Credential, *, at: datetime | None = None) -> None:
    credential.last_verified_at = at or utcnow()
    db.flush()


def mark_used(db: Session, credential: Credential, *, at: datetime | None = None) -> None:
    credential.last_used_at = at or utcnow()
    db.flush()


def get_source_id_by_key(db: Session, source_key: str) -> uuid.UUID | None:
    """Resolve a source id by key.

    Lane B moves source lookups to ``app/repositories/sources.py``; the
    foundation needs this to attach SOURCE-scoped credentials.
    """
    return db.scalar(select(Source.id).where(Source.key == source_key))
