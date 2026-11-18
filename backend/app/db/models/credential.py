"""Encrypted integration credentials (table ``credential``)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    LargeBinary,
    SmallInteger,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UuidPrimaryKeyMixin, enum_check
from app.domain.enums import CredentialScope


class Credential(UuidPrimaryKeyMixin, TimestampMixin, Base):
    """An AES-256-GCM encrypted secret. The plaintext is never persisted."""

    __tablename__ = "credential"
    __table_args__ = (
        CheckConstraint(enum_check("scope", CredentialScope), name="scope_valid"),
        CheckConstraint(
            "scope <> 'SOURCE' OR source_id IS NOT NULL", name="source_scope_requires_source"
        ),
        CheckConstraint(
            "scope = 'SOURCE' OR source_id IS NULL", name="non_source_scope_has_no_source"
        ),
        UniqueConstraint(
            "scope",
            "source_id",
            "key",
            name="uq_credential_scope_source_key",
            postgresql_nulls_not_distinct=True,
        ),
        # SQLite treats NULLs as distinct, so enforce the NULL-source case explicitly.
        Index(
            "credential_scope_null_source_uq",
            "scope",
            "key",
            unique=True,
            sqlite_where=text("source_id IS NULL"),
            postgresql_where=text("source_id IS NULL"),
        ),
    )

    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("source.id", ondelete="CASCADE"), nullable=True
    )
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    nonce: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    algorithm: Mapped[str] = mapped_column(String(32), nullable=False, default="AES-256-GCM")
    key_version: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    masked_hint: Mapped[str] = mapped_column(String(32), nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Credential(scope={self.scope!r}, key={self.key!r}, hint={self.masked_hint!r})"
