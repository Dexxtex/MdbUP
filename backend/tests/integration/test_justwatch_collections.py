"""JustWatch collection sync: mappings, per-provider collections, idempotency."""

from __future__ import annotations

import httpx
import respx
from sqlalchemy import func, select

from app.db.models import Collection, ProviderMapping
from app.db.session import session_scope
from app.services import justwatch_collections

BASE = "https://apis.justwatch.com/graphql"

_PACKAGES = [
    {"shortName": "nfx", "clearName": "Netflix", "monetizationTypes": ["FLATRATE"]},
    {"shortName": "prv", "clearName": "Amazon Prime Video", "monetizationTypes": ["FLATRATE"]},
    {"shortName": "dnp", "clearName": "Disney Plus", "monetizationTypes": ["FLATRATE"]},
    # Unmapped on purpose: must be reported, never guessed.
    {"shortName": "zzz", "clearName": "Unknown Service", "monetizationTypes": ["FLATRATE"]},
]


def _mock_packages() -> None:
    respx.post(BASE).mock(return_value=httpx.Response(200, json={"data": {"packages": _PACKAGES}}))


@respx.mock
def test_sync_creates_mappings_and_collections(db, seeded, app_settings) -> None:
    _mock_packages()
    with session_scope() as session:
        outcome = justwatch_collections.sync_collections(session, app_settings)

    # 12 curated providers are mapped, but collections are only built for the
    # providers the source actually reports (3 in this mock): 4 kinds x 2 media.
    assert outcome.mappings == 12
    assert outcome.collections_created == 3 * 8
    assert outcome.collections_updated == 0
    assert "zzz" in outcome.skipped_providers

    with session_scope() as session:
        source = session.scalar(select(Collection.source_id).limit(1))
        assert source is not None
        mappings = session.scalar(
            select(func.count())
            .select_from(ProviderMapping)
            .where(ProviderMapping.external_provider_id.in_(["nfx", "prv", "dnp"]))
        )
        assert mappings == 3
        justwatch = session.scalars(
            select(Collection).where(Collection.slug.like("%-justwatch%"))
        ).all()
        assert len(justwatch) == 3 * 8
        netflix = next(c for c in justwatch if c.slug == "netflix-movie-justwatch")
        assert netflix.source_collection_key == "nfx:MOVIE"
        assert netflix.filters["packages"] == ["nfx"]
        assert netflix.origin == "AGGREGATOR"
        assert netflix.date_basis == "UNKNOWN"
        assert netflix.kind == "CATALOG"
        chart = next(c for c in justwatch if c.slug == "netflix-movie-justwatch-chart")
        assert chart.kind == "CHART"
        assert chart.source_collection_key == "chart:nfx:MOVIE"


@respx.mock
def test_sync_is_idempotent(db, seeded, app_settings) -> None:
    _mock_packages()
    with session_scope() as session:
        first = justwatch_collections.sync_collections(session, app_settings)
    with session_scope() as session:
        second = justwatch_collections.sync_collections(session, app_settings)

    assert first.collections_created == 24
    assert second.collections_created == 0
    assert second.collections_updated == 24
    with session_scope() as session:
        total = session.scalar(
            select(func.count()).select_from(Collection).where(Collection.slug.like("%-justwatch%"))
        )
        assert total == 24


@respx.mock
def test_sync_can_be_limited_to_one_provider(db, seeded, app_settings) -> None:
    _mock_packages()
    with session_scope() as session:
        outcome = justwatch_collections.sync_collections(
            session, app_settings, provider_slugs=["netflix"]
        )
    assert outcome.mappings == 1
    assert outcome.collections_created == 8
