"""Celery task wrapper for the staggered JustWatch catalog acquisitions."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from sqlalchemy import select

from app.db.models import JobExecution
from app.db.session import get_session_factory
from app.jobs import tasks
from app.repositories import collections as collections_repo
from app.repositories import providers as providers_repo
from app.repositories import settings as settings_repo
from app.repositories import sources as sources_repo
from app.services import catalog_schedule

DAY = date(2026, 5, 4)
SLUG = "netflix-movie-justwatch-task"


def _justwatch_collection() -> uuid.UUID:
    session = get_session_factory()()
    try:
        source = sources_repo.get_source_by_key(session, "justwatch")
        provider = providers_repo.get_provider_by_slug(session, "netflix")
        assert source is not None and provider is not None
        collection = collections_repo.upsert_collection(
            session,
            slug=SLUG,
            source_id=source.id,
            provider_id=provider.id,
            country_code="IT",
            media_type="MOVIE",
            kind="CATALOG",
            origin="AGGREGATOR",
            date_basis="UNKNOWN",
            name="Netflix — Film — Catalogo JustWatch",
            description=None,
            source_collection_key="nfx:MOVIE",
            source_url=None,
            offer_types=["FLATRATE"],
            filters={},
            quality_flags={},
            sort_mode="POPULARITY",
            is_active=True,
        )
        session.commit()
        return collection.id
    finally:
        session.close()


def _moment_after_the_slot() -> str:
    slot = catalog_schedule.slot_start(SLUG, DAY)
    return (slot + timedelta(minutes=1)).isoformat()


def test_task_reports_a_disabled_schedule(db, seeded, app_settings) -> None:
    session = get_session_factory()()
    try:
        settings_repo.set_value(session, "catalog_schedule_enabled", False)
        session.commit()
    finally:
        session.close()

    result = tasks.enqueue_scheduled_catalog_acquisitions(now=_moment_after_the_slot())

    assert result == {
        "due": 0,
        "enqueued": 0,
        "collection_id": None,
        "job_id": None,
        "reason": "DISABLED",
    }


def test_task_enqueues_one_acquisition_job(db, seeded, app_settings, monkeypatch) -> None:
    collection_id = _justwatch_collection()
    dispatched: list[tuple[str, str | None]] = []
    monkeypatch.setattr(
        tasks,
        "acquire_collection_task",
        lambda collection_id, job_id=None: dispatched.append((str(collection_id), job_id)),
    )
    moment = _moment_after_the_slot()

    result = tasks.enqueue_scheduled_catalog_acquisitions(now=moment)

    assert result["enqueued"] == 1
    assert result["due"] == 1
    assert result["collection_id"] == str(collection_id)
    assert result["job_id"] is not None
    assert dispatched == [(str(collection_id), result["job_id"])]
    session = get_session_factory()()
    try:
        job = session.get(JobExecution, uuid.UUID(str(result["job_id"])))
        assert job is not None
        assert job.task_name == tasks.ACQUIRE_COLLECTION_TASK
        assert job.payload["collection_id"] == str(collection_id)
    finally:
        session.close()

    # The queued job keeps the collection out of the next tick.
    second = tasks.enqueue_scheduled_catalog_acquisitions(now=moment)

    assert second["enqueued"] == 0
    assert second["reason"] == "NOTHING_DUE"
    session = get_session_factory()()
    try:
        jobs = session.scalars(
            select(JobExecution).where(JobExecution.task_name == tasks.ACQUIRE_COLLECTION_TASK)
        ).all()
        assert len(jobs) == 1
    finally:
        session.close()
