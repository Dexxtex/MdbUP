"""Provider seed: the Italian providers and their movie/TV TMDb mapping metadata."""

from __future__ import annotations

from app.domain.enums import SourceStatus
from app.seed import PROVIDER_SEED, SOURCE_SEED, TMDB_PROVIDER_SEED

# Providers requested for the Phase 7 expansion; they must already be seeded
# with verified TMDb ids (no invented identifiers).
EXPECTED_PROVIDERS = {
    "prime-video": ("119", "119"),
    "disney-plus": ("337", "337"),
    "now": ("39", "39"),
    "paramount-plus": ("531", "531"),
    "raiplay": ("222", "222"),
}

# Infinity+ has no TV coverage in Italy: the movie id is the only mapping.
MOVIE_ONLY_PROVIDERS = {"infinity-plus"}


def test_seed_contains_the_phase7_providers() -> None:
    slugs = {seed.slug for seed in PROVIDER_SEED}
    assert set(EXPECTED_PROVIDERS) <= slugs


def test_expected_providers_keep_their_tmdb_ids() -> None:
    mappings = {seed.slug: seed for seed in TMDB_PROVIDER_SEED}
    for slug, (movie_id, tv_id) in EXPECTED_PROVIDERS.items():
        assert mappings[slug].external_id == movie_id
        assert mappings[slug].tv_external_id == tv_id


def test_seed_contains_the_combined_local_source() -> None:
    sources = {seed.key: seed for seed in SOURCE_SEED}
    combined = sources["combined"]
    assert combined.name == "Combinata locale"
    assert combined.status is SourceStatus.OK
    assert combined.origin_default.value == "CUSTOM"
    assert combined.capabilities["catalog"] is True
    assert combined.capabilities["combined_local"] is True
    assert combined.requires_contract is False


def test_every_provider_has_movie_and_tv_mapping_metadata() -> None:
    providers = {seed.slug for seed in PROVIDER_SEED}
    mappings = {seed.slug: seed for seed in TMDB_PROVIDER_SEED}

    assert set(mappings) == providers
    for slug in sorted(providers):
        mapping = mappings[slug]
        assert mapping.external_id.isdigit(), f"{slug}: id film TMDb mancante"
        if slug in MOVIE_ONLY_PROVIDERS:
            assert mapping.tv_external_id is None, f"{slug}: nessuna copertura TV attesa"
        else:
            assert mapping.tv_external_id is not None, f"{slug}: id serie TMDb mancante"
            assert mapping.tv_external_id.isdigit(), f"{slug}: id serie TMDb non numerico"


def test_seed_installs_the_verified_justwatch_mappings(db, seeded) -> None:
    from sqlalchemy import select

    from app.db.models import ProviderMapping
    from app.db.session import get_session_factory
    from app.repositories import sources as sources_repo

    session = get_session_factory()()
    try:
        source = sources_repo.get_source_by_key(session, "justwatch")
        assert source is not None
        mappings = session.scalars(
            select(ProviderMapping).where(ProviderMapping.source_id == source.id)
        ).all()
        assert len(mappings) == 12
        assert all(mapping.is_verified for mapping in mappings)
        assert {mapping.external_provider_id for mapping in mappings} >= {"nfx", "prv", "dnp"}
    finally:
        session.close()
