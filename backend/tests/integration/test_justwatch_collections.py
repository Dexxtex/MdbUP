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
    {
        "shortName": "nfx",
        "technicalName": "netflix",
        "clearName": "Netflix",
        "monetizationTypes": ["FLATRATE"],
    },
    {
        "shortName": "prv",
        "technicalName": "amazonprimevideo",
        "clearName": "Amazon Prime Video",
        "monetizationTypes": ["FLATRATE", "FREE"],
    },
    {
        "shortName": "dnp",
        "technicalName": "disneyplus",
        "clearName": "Disney Plus",
        "monetizationTypes": ["FLATRATE"],
    },
    # Verified, but without FLATRATE: reported, never given a catalog.
    {
        "shortName": "wki",
        "technicalName": "wuaki",
        "clearName": "Rakuten TV",
        "monetizationTypes": ["ADS", "BUY", "RENT"],
    },
    # Unmapped on purpose: must be reported, never guessed.
    {"shortName": "zzz", "technicalName": "zzz", "clearName": "Unknown", "monetizationTypes": []},
]


def _mock_packages() -> None:
    respx.post(BASE).mock(return_value=httpx.Response(200, json={"data": {"packages": _PACKAGES}}))


@respx.mock
def test_sync_creates_mappings_and_collections(db, seeded, app_settings) -> None:
    _mock_packages()
    with session_scope() as session:
        outcome = justwatch_collections.sync_collections(session, app_settings)

    # Four packages verify (shortName + technicalName) in this mock: three with
    # FLATRATE plus Rakuten, which is reported but gets no collections.
    assert outcome.mappings == 4
    assert outcome.collections_created == 3 * 8
    assert outcome.collections_updated == 0
    assert outcome.skipped_providers == ("wki",)
    assert "zzz" in outcome.unmapped_packages

    with session_scope() as session:
        source = session.scalar(select(Collection.source_id).limit(1))
        assert source is not None
        mappings = session.scalar(
            select(func.count())
            .select_from(ProviderMapping)
            .where(ProviderMapping.external_provider_id.in_(["nfx", "prv", "dnp"]))
        )
        assert mappings == 3
        netflix_mapping = session.scalar(
            select(ProviderMapping).where(ProviderMapping.external_provider_id == "nfx")
        )
        assert netflix_mapping is not None
        assert netflix_mapping.is_verified is True
        metadata = netflix_mapping.metadata_json
        assert metadata["technical_name"] == "netflix"
        assert metadata["clear_name"] == "Netflix"
        assert metadata["monetization_types"] == ["FLATRATE"]
        assert metadata["verified_at"]
        assert metadata["movie_external_id"] == "nfx"
        assert metadata["tv_external_id"] == "nfx"
        assert metadata["movie_verified"] is True
        assert metadata["tv_verified"] is True
        # One row per external id: the per-type ids live in metadata.
        nfx_rows = session.scalar(
            select(func.count())
            .select_from(ProviderMapping)
            .where(ProviderMapping.external_provider_id == "nfx")
        )
        assert nfx_rows == 1
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


@respx.mock
def test_sync_skips_packages_whose_technical_name_does_not_match(db, seeded, app_settings) -> None:
    """shortName alone is not enough: atp must be appletvplus, not a store."""
    respx.post(BASE).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "packages": [
                        {
                            "shortName": "nfx",
                            "technicalName": "apple-tv-store",
                            "clearName": "Netflix?",
                            "monetizationTypes": ["FLATRATE"],
                        }
                    ]
                }
            },
        )
    )
    with session_scope() as session:
        outcome = justwatch_collections.sync_collections(
            session, app_settings, provider_slugs=["netflix"]
        )

    assert outcome.mappings == 0
    assert outcome.unverified_providers == ("nfx",)
    assert outcome.collections_created == 0
    with session_scope() as session:
        justwatch = session.scalars(
            select(Collection).where(Collection.slug.like("%-justwatch%"))
        ).all()
        assert justwatch == []
        mapping = session.scalar(
            select(ProviderMapping).where(ProviderMapping.external_provider_id == "nfx")
        )
        assert mapping is None


@respx.mock
def test_sync_keeps_existing_snapshots_and_last_valid_pointer(db, seeded, app_settings) -> None:
    from app.db.models import CollectionSnapshot

    _mock_packages()
    with session_scope() as session:
        justwatch_collections.sync_collections(session, app_settings)
    with session_scope() as session:
        netflix = session.scalar(
            select(Collection).where(Collection.slug == "netflix-movie-justwatch")
        )
        assert netflix is not None
        snapshot = CollectionSnapshot(
            collection_id=netflix.id,
            status="COMPLETE",
            quality="CLEAN",
            is_valid=True,
            items_count=1,
            resolved_count=1,
            unresolved_count=0,
            duplicate_count=0,
            error_count=0,
            checksum="keep-me",
        )
        session.add(snapshot)
        session.flush()
        netflix.last_valid_snapshot_id = snapshot.id
        snapshot_id = snapshot.id

    with session_scope() as session:
        outcome = justwatch_collections.sync_collections(session, app_settings)

    assert outcome.collections_updated == 24
    with session_scope() as session:
        netflix = session.scalar(
            select(Collection).where(Collection.slug == "netflix-movie-justwatch")
        )
        assert netflix is not None
        assert netflix.last_valid_snapshot_id == snapshot_id
        assert netflix.name == "Netflix — Film — Catalogo JustWatch"
        assert netflix.offer_types == ["FLATRATE"]
        count = session.scalar(
            select(func.count())
            .select_from(CollectionSnapshot)
            .where(CollectionSnapshot.collection_id == netflix.id)
        )
        assert count == 1
