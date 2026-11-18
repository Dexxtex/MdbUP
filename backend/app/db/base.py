"""Declarative base, naming conventions and shared column mixins.

Schema types are deliberately generic so the same metadata works on SQLite
(tests) and PostgreSQL (production):

* ``Uuid`` primary keys with a Python-side ``uuid4`` default;
* ``JSON`` instead of ``JSONB``;
* ``String`` instead of ``CITEXT``/``INET``/arrays;
* ``DateTime(timezone=True)`` for timestamps;
* ``String`` + ``CheckConstraint`` instead of native enums.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, MetaData, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.time import utcnow

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s",
    "pk": "pk_%(table_name)s",
}


def enum_check(column: str, values: Iterable[str]) -> str:
    """Render a ``CHECK`` expression for a string enum column."""
    rendered = ", ".join(f"'{str(value)}'" for value in values)
    return f"{column} IN ({rendered})"


def sqlite_integer_pk() -> BigInteger:
    """A BIGINT identity column that still autoincrements on SQLite."""
    return BigInteger().with_variant(Integer, "sqlite")


class Base(DeclarativeBase):
    """Declarative base shared by every model."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UuidPrimaryKeyMixin:
    """UUID primary key generated in Python (portable across dialects)."""

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)


class BigIntPrimaryKeyMixin:
    """BIGINT identity primary key for append-only log tables."""

    id: Mapped[int] = mapped_column(sqlite_integer_pk(), primary_key=True, autoincrement=True)


class TimestampMixin:
    """``created_at``/``updated_at`` maintained by the ORM (no DB triggers)."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
        server_default=func.now(),
    )
