"""Live provider verification: per-media-type ids and coverage."""

from __future__ import annotations

import httpx
import pytest
import respx
from sqlalchemy.orm import Session

from app.db.session import get_session_factory
from app.repositories import collections as collections_repo
from app.repositories import providers as providers_repo
from app.repositories import sources as sources_repo
from app.services import credentials as credentials_service
from app.services.credentials import CredentialKind
from app.services.provider_verification import verify_tmdb_providers
from app.services.providers import list_providers

BASE = "https://api.themoviedb.org/3"


@pytest.fixture()
def session(db) -> Session:
    factory = get_session_factory()
    db_session = factory()
    try:
        yield db_session
    finally:
        db_session.close()


@respx.mock
def test_verify_providers_stores_movie_and_tv_ids_separately(
    session: Session, seeded, app_settings
) -> None:
    credentials_service.set_secret(session, app_settings, CredentialKind.TMDB, "test-token")
    session.commit()
    respx.get(f"{BASE}/watch/providers/movie").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {"provider_id": 8, "provider_name": "Netflix", "display_priority": 1},
                    {"provider_id": 110, "provider_name": "Infinity+", "display_priority": 9},
                ]
            },
        )
    )
    respx.get(f"{BASE}/watch/providers/tv").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    # Different id on purpose: the mapper must not assume equality.
                    {"provider_id": 80, "provider_name": "Netflix", "display_priority": 1},
                ]
            },
        )
    )

    infinity = providers_repo.get_provider_by_slug(session, "infinity-plus")
    assert infinity is not None
    tmdb = sources_repo.get_source_by_key(session, "tmdb")
    assert tmdb is not None
    collections_repo.upsert_collection(
        session,
        slug="infinity-plus-show",
        source_id=tmdb.id,
        provider_id=infinity.id,
        country_code="IT",
        media_type="SHOW",
        kind="CATALOG",
        origin="AGGREGATOR",
        date_basis="UNKNOWN",
        name="Infinity+ — Serie",
        description="Obsolete test collection",
        source_collection_key="110:SHOW",
        offer_types=["FLATRATE"],
        filters={"provider_id": "110", "watch_region": "IT"},
        quality_flags={},
        sort_mode="POPULARITY",
        is_active=True,
    )
    session.commit()

    results = verify_tmdb_providers(session, app_settings, country_code="IT")
    netflix = next(item for item in results if item.slug == "netflix")
    assert netflix.movie_provider_id == "8"
    assert netflix.tv_provider_id == "80"
    assert netflix.movie_verified is True
    assert netflix.tv_verified is True

    provider = providers_repo.get_provider_by_slug(session, "netflix")
    assert provider is not None
    mapping = providers_repo.get_mapping(
        session,
        provider_id=provider.id,
        source_id=collections_repo.get_collection_by_slug(session, "netflix-movie").source_id,
        country_code="IT",
    )
    assert mapping is not None
    assert mapping.is_verified is True
    assert mapping.external_provider_id == "8"
    assert mapping.metadata_json["movie_provider_id"] == "8"
    assert mapping.metadata_json["tv_provider_id"] == "80"

    summaries = {item.slug: item for item in list_providers(session, country_code="IT")}
    assert summaries["netflix"].tmdb_provider_id_movie == "8"
    assert summaries["netflix"].tmdb_provider_id_tv == "80"
    assert summaries["netflix"].mapping_verified_movie is True
    assert summaries["netflix"].mapping_verified_tv is True

    infinity_show = collections_repo.get_collection_by_slug(session, "infinity-plus-show")
    assert infinity_show is not None
    assert infinity_show.is_active is False
