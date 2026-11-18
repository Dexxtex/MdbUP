"""Target lock tests: in-process on SQLite, advisory lock on PostgreSQL."""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest


def test_sqlite_lock_is_exclusive(db) -> None:
    from app.db.session import get_session_factory
    from app.services.sync import TargetLock

    session = get_session_factory()()
    target_id = uuid.uuid4()
    first = TargetLock(session, target_id)
    second = TargetLock(session, target_id)
    try:
        assert first.acquire() is True
        try:
            assert second.acquire() is False
        finally:
            first.release()
        assert second.acquire() is True
        second.release()
    finally:
        session.close()


@pytest.fixture()
def postgres_engine(tmp_path) -> Iterator[object]:
    """Start a throwaway PostgreSQL with pgserver, or skip when unavailable."""
    try:
        from pgserver import PostgresServer
    except ImportError:  # pragma: no cover - dev extra always installed here
        pytest.skip("pgserver non installato")
    try:
        server = PostgresServer(tmp_path / "pgdata")
        uri = server.get_uri()
    except Exception as exc:  # pragma: no cover - platform dependent
        pytest.skip(f"pgserver non disponibile su questa piattaforma: {exc}")
    from sqlalchemy import create_engine

    from app.db import models  # noqa: F401  (registers the tables)
    from app.db.base import Base

    engine = create_engine(uri.replace("postgresql://", "postgresql+psycopg://", 1))
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()
        server.cleanup()


def test_postgres_advisory_lock_is_exclusive(postgres_engine) -> None:
    from sqlalchemy.orm import Session

    from app.services.sync import TargetLock

    target_id = uuid.uuid4()
    first_session = Session(postgres_engine)
    second_session = Session(postgres_engine)
    first = TargetLock(first_session, target_id)
    second = TargetLock(second_session, target_id)
    try:
        assert first.acquire() is True
        try:
            assert second.acquire() is False
        finally:
            first.release()
        assert second.acquire() is True
        second.release()
    finally:
        first_session.close()
        second_session.close()
