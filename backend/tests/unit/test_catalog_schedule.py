"""Staggered JustWatch catalog scheduling: slots, due selection, one per tick."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.orm import Session

from app.db.models import CollectionSnapshot
from app.db.session import get_session_factory
from app.jobs import tasks
from app.repositories import collections as collections_repo
from app.repositories import providers as providers_repo
from app.repositories import settings as settings_repo
from app.repositories import sources as sources_repo
from app.services import catalog_schedule

ROME = ZoneInfo("Europe/Rome")
# A day without a DST transition, so 15-minute slots map to fixed instants.
DAY = date(2026, 5, 4)


@pytest.fixture()
def session(db) -> Session:
    factory = get_session_factory()
    db_session = factory()
    try:
        yield db_session
    finally:
        db_session.close()


def _collection(session: Session, slug: str, *, is_active: bool = True):
    source = sources_repo.get_source_by_key(session, "justwatch")
    provider = providers_repo.get_provider_by_slug(session, "netflix")
    assert source is not None and provider is not None
    collection = collections_repo.upsert_collection(
        session,
        slug=slug,
        source_id=source.id,
        provider_id=provider.id,
        country_code="IT",
        media_type="MOVIE",
        kind="CATALOG",
        origin="AGGREGATOR",
        date_basis="UNKNOWN",
        name=f"Netflix — {slug}",
        description=None,
        source_collection_key=f"{slug}:MOVIE",
        source_url=None,
        offer_types=["FLATRATE"],
        filters={},
        quality_flags={},
        sort_mode="POPULARITY",
        is_active=is_active,
    )
    session.commit()
    return collection


def _snapshot(
    session: Session,
    collection,
    *,
    status: str,
    started_at: datetime,
    items_count: int = 1,
) -> CollectionSnapshot:
    snapshot = CollectionSnapshot(
        collection_id=collection.id,
        status=status,
        quality="CLEAN",
        is_valid=status == "COMPLETE",
        started_at=started_at,
        finished_at=started_at,
        items_count=items_count,
        resolved_count=items_count,
        unresolved_count=0,
        duplicate_count=0,
        error_count=0,
        checksum="checksum",
    )
    session.add(snapshot)
    session.commit()
    return snapshot


def _after_every_slot(slugs: list[str]) -> datetime:
    """An instant on ``DAY`` after every collection slot already started."""
    return max(catalog_schedule.slot_start(slug, DAY) for slug in slugs) + timedelta(minutes=1)


def _spy(seen: list[uuid.UUID]):
    def enqueue(_db: Session, _settings, collection_id: uuid.UUID):
        seen.append(collection_id)
        return SimpleNamespace(id=uuid.uuid4())

    return enqueue


def test_slot_index_is_deterministic_and_inside_the_day() -> None:
    assert catalog_schedule.SLOT_COUNT == 96
    assert catalog_schedule.slot_index("netflix-movie-justwatch") == 22
    assert catalog_schedule.slot_index("netflix-movie-justwatch") == catalog_schedule.slot_index(
        "netflix-movie-justwatch"
    )
    indices = {
        catalog_schedule.slot_index(slug)
        for slug in (
            "netflix-movie-justwatch",
            "prime-video-movie-justwatch",
            "disney-plus-movie-justwatch",
            "now-show-justwatch",
        )
    }
    assert len(indices) > 1
    assert all(0 <= index < catalog_schedule.SLOT_COUNT for index in indices)


def test_next_acquire_at_is_the_next_local_slot() -> None:
    slug = "netflix-movie-justwatch"
    index = catalog_schedule.slot_index(slug)
    now = datetime(2026, 5, 4, 0, 0, tzinfo=UTC)

    moment = catalog_schedule.next_acquire_at(slug, now)

    local = moment.astimezone(ROME)
    assert (local.hour, local.minute) == (index * 15 // 60, index * 15 % 60)
    assert moment > now
    assert moment - now <= timedelta(days=1)
    # A slot already started belongs to the next day.
    following = catalog_schedule.next_acquire_at(slug, moment)
    assert (following.astimezone(ROME).date() - local.date()).days == 1
    assert following.astimezone(ROME).time() == local.time()


def test_tick_enqueues_one_collection_in_slot_order(session: Session, seeded, app_settings) -> None:
    slugs = ["gamma-movie-justwatch", "alpha-movie-justwatch", "beta-movie-justwatch"]
    for slug in slugs:
        _collection(session, slug)
    now = _after_every_slot(slugs)
    seen: list[uuid.UUID] = []

    outcome = catalog_schedule.enqueue_due_catalog_acquisitions(
        session, app_settings, now=now, enqueue=_spy(seen)
    )

    expected_slug = min(slugs, key=lambda slug: (catalog_schedule.slot_index(slug), slug))
    expected = collections_repo.get_collection_by_slug(session, expected_slug)
    assert expected is not None
    assert outcome.due == 3
    assert outcome.enqueued == 1
    assert outcome.collection_id == expected.id
    assert outcome.job_id is not None
    assert seen == [expected.id]


def test_repeated_ticks_never_duplicate_a_collection(
    session: Session, seeded, app_settings
) -> None:
    slugs = ["delta-movie-justwatch", "epsilon-movie-justwatch"]
    for slug in slugs:
        _collection(session, slug)
    now = _after_every_slot(slugs)
    first_slug = min(slugs, key=lambda slug: (catalog_schedule.slot_index(slug), slug))
    second_slug = next(slug for slug in slugs if slug != first_slug)
    first = collections_repo.get_collection_by_slug(session, first_slug)
    second = collections_repo.get_collection_by_slug(session, second_slug)
    assert first is not None and second is not None
    seen: list[uuid.UUID] = []

    catalog_schedule.enqueue_due_catalog_acquisitions(
        session, app_settings, now=now, enqueue=_spy(seen)
    )
    _snapshot(session, first, status="RUNNING", started_at=now, items_count=0)

    second_tick = catalog_schedule.enqueue_due_catalog_acquisitions(
        session, app_settings, now=now + timedelta(minutes=5), enqueue=_spy(seen)
    )
    _snapshot(session, second, status="RUNNING", started_at=now, items_count=0)

    third_tick = catalog_schedule.enqueue_due_catalog_acquisitions(
        session, app_settings, now=now + timedelta(minutes=10), enqueue=_spy(seen)
    )

    assert seen == [first.id, second.id]
    assert second_tick.collection_id == second.id
    assert third_tick.enqueued == 0
    assert third_tick.reason == "NOTHING_DUE"
    assert len(set(seen)) == len(seen)


def test_recent_complete_snapshot_is_not_due(session: Session, seeded, app_settings) -> None:
    slugs = ["zeta-movie-justwatch"]
    collection = _collection(session, slugs[0])
    now = _after_every_slot(slugs)
    _snapshot(session, collection, status="COMPLETE", started_at=now - timedelta(hours=2))
    seen: list[uuid.UUID] = []

    outcome = catalog_schedule.enqueue_due_catalog_acquisitions(
        session, app_settings, now=now, enqueue=_spy(seen)
    )

    assert outcome.enqueued == 0
    assert outcome.reason == "NOTHING_DUE"
    assert seen == []


def test_stale_complete_snapshot_is_due(session: Session, seeded, app_settings) -> None:
    slugs = ["eta-movie-justwatch"]
    collection = _collection(session, slugs[0])
    now = _after_every_slot(slugs)
    _snapshot(session, collection, status="COMPLETE", started_at=now - timedelta(hours=21))
    seen: list[uuid.UUID] = []

    outcome = catalog_schedule.enqueue_due_catalog_acquisitions(
        session, app_settings, now=now, enqueue=_spy(seen)
    )

    assert outcome.enqueued == 1
    assert seen == [collection.id]


def test_failed_attempt_backs_off_before_the_next_retry(
    session: Session, seeded, app_settings
) -> None:
    slugs = ["theta-movie-justwatch"]
    collection = _collection(session, slugs[0])
    now = _after_every_slot(slugs)
    _snapshot(session, collection, status="FAILED", started_at=now - timedelta(minutes=10))
    seen: list[uuid.UUID] = []

    outcome = catalog_schedule.enqueue_due_catalog_acquisitions(
        session, app_settings, now=now, enqueue=_spy(seen)
    )

    assert outcome.enqueued == 0
    assert seen == []


def test_slot_not_reached_yet_keeps_the_collection_out(
    session: Session, seeded, app_settings
) -> None:
    slugs = ["iota-movie-justwatch"]
    _collection(session, slugs[0])
    slot = catalog_schedule.slot_start(slugs[0], DAY)
    seen: list[uuid.UUID] = []

    outcome = catalog_schedule.enqueue_due_catalog_acquisitions(
        session, app_settings, now=slot - timedelta(minutes=5), enqueue=_spy(seen)
    )

    assert outcome.enqueued == 0
    assert seen == []


def test_inactive_collection_is_never_scheduled(session: Session, seeded, app_settings) -> None:
    slugs = ["kappa-movie-justwatch"]
    _collection(session, slugs[0], is_active=False)
    now = _after_every_slot(slugs)
    seen: list[uuid.UUID] = []

    outcome = catalog_schedule.enqueue_due_catalog_acquisitions(
        session, app_settings, now=now, enqueue=_spy(seen)
    )

    assert outcome.enqueued == 0
    assert seen == []
    assert catalog_schedule.upcoming_acquisitions(session, now=now) == []


def test_a_queued_job_blocks_a_second_enqueue(session: Session, seeded, app_settings) -> None:
    slugs = ["nu-movie-justwatch"]
    collection = _collection(session, slugs[0])
    now = _after_every_slot(slugs)
    tasks.create_job_execution(
        session,
        task_name=tasks.ACQUIRE_COLLECTION_TASK,
        payload={"collection_id": str(collection.id)},
    )
    session.commit()
    seen: list[uuid.UUID] = []

    outcome = catalog_schedule.enqueue_due_catalog_acquisitions(
        session, app_settings, now=now, enqueue=_spy(seen)
    )

    assert outcome.enqueued == 0
    assert seen == []


def test_disabled_setting_stops_the_tick(session: Session, seeded, app_settings) -> None:
    slugs = ["lambda-movie-justwatch"]
    _collection(session, slugs[0])
    settings_repo.set_value(session, "catalog_schedule_enabled", False)
    session.commit()
    now = _after_every_slot(slugs)
    seen: list[uuid.UUID] = []

    outcome = catalog_schedule.enqueue_due_catalog_acquisitions(
        session, app_settings, now=now, enqueue=_spy(seen)
    )

    assert outcome.enqueued == 0
    assert outcome.reason == "DISABLED"
    assert seen == []


def test_upcoming_lists_the_next_slot_within_24_hours(
    session: Session, seeded, app_settings
) -> None:
    collection = _collection(session, "mu-movie-justwatch")
    now = datetime(2026, 5, 4, 0, 0, tzinfo=UTC)

    upcoming = catalog_schedule.upcoming_acquisitions(session, now=now)

    assert len(upcoming) == 1
    item = upcoming[0]
    assert item.collection_id == collection.id
    assert item.collection_name == "Netflix — mu-movie-justwatch"
    assert item.provider_name == "Netflix"
    assert now < item.next_acquire_at <= now + timedelta(hours=24)
