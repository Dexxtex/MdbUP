"""Reference data seed: providers, sources, TMDb mappings and collections.

TMDb provider ids are the Italian watch-provider ids recorded in the Phase 2
brief. They are seeded as *unverified* mappings: without a live API key the
``/watch/providers`` response has not been re-checked, so the UI must not claim
the mapping is verified.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.db.models import (
    Availability,
    Collection,
    CollectionSnapshot,
    EpisodeEvent,
    Provider,
    Source,
    SyncBinding,
)
from app.db.session import session_scope
from app.domain.enums import (
    COMBINED_SOURCE_KEY,
    CollectionKind,
    CollectionOrigin,
    DateBasis,
    MediaType,
    OfferType,
    SourceStatus,
    SourceType,
)
from app.domain.justwatch import MAPPING_VERIFIED_AT, PROVIDER_MAPPINGS
from app.repositories import collections as collections_repo
from app.repositories import providers as providers_repo

DEFAULT_COUNTRY_CODE = "IT"
TMDB_SOURCE_KEY = "tmdb"
JUSTWATCH_SOURCE_KEY = "justwatch_partner"
# Public, non-contracted GraphQL endpoint. Distinct from the Partner API above:
# no credentials, no contract, opt-in via JUSTWATCH_PUBLIC_ENABLED.
JUSTWATCH_PUBLIC_SOURCE_KEY = "justwatch"


@dataclass(frozen=True)
class ProviderSeed:
    slug: str
    name: str
    kind: str = "SVOD"


@dataclass(frozen=True)
class TmdbProviderSeed:
    slug: str
    external_id: str
    tv_external_id: str | None = None


@dataclass(frozen=True)
class SourceSeed:
    key: str
    name: str
    type: SourceType
    base_url: str | None
    origin_default: CollectionOrigin
    status: SourceStatus
    capabilities: dict[str, object]
    requires_contract: bool = False
    is_official: bool = False


# Canonical Italian providers. External ids are resolved per source at sync time
# and stored in provider_mapping, never hardcoded in the acquisition code.
PROVIDER_SEED: tuple[ProviderSeed, ...] = (
    ProviderSeed(slug="netflix", name="Netflix"),
    ProviderSeed(slug="prime-video", name="Prime Video"),
    ProviderSeed(slug="disney-plus", name="Disney+"),
    ProviderSeed(slug="now", name="NOW"),
    ProviderSeed(slug="timvision", name="Timvision"),
    ProviderSeed(slug="infinity-plus", name="Infinity+"),
    ProviderSeed(slug="rakuten-tv", name="Rakuten TV", kind="TVOD"),
    ProviderSeed(slug="mubi", name="MUBI"),
    ProviderSeed(slug="apple-tv-plus", name="Apple TV+"),
    ProviderSeed(slug="paramount-plus", name="Paramount+"),
    ProviderSeed(slug="raiplay", name="RaiPlay"),
    ProviderSeed(slug="mediaset-infinity", name="Mediaset Infinity"),
)

# Italian TMDb watch-provider ids from docs/phases/phase-02.md (Lane B).
TMDB_PROVIDER_SEED: tuple[TmdbProviderSeed, ...] = (
    TmdbProviderSeed(slug="netflix", external_id="8", tv_external_id="8"),
    TmdbProviderSeed(slug="prime-video", external_id="119", tv_external_id="119"),
    TmdbProviderSeed(slug="disney-plus", external_id="337", tv_external_id="337"),
    TmdbProviderSeed(slug="now", external_id="39", tv_external_id="39"),
    TmdbProviderSeed(slug="timvision", external_id="109", tv_external_id="109"),
    TmdbProviderSeed(slug="infinity-plus", external_id="110", tv_external_id=None),
    TmdbProviderSeed(slug="rakuten-tv", external_id="35", tv_external_id="35"),
    TmdbProviderSeed(slug="mubi", external_id="11", tv_external_id="11"),
    # Verificati live con /watch/providers (movie + tv, IT) il 2026-11-17.
    TmdbProviderSeed(slug="apple-tv-plus", external_id="350", tv_external_id="350"),
    TmdbProviderSeed(slug="paramount-plus", external_id="531", tv_external_id="531"),
    TmdbProviderSeed(slug="raiplay", external_id="222", tv_external_id="222"),
    TmdbProviderSeed(slug="mediaset-infinity", external_id="359", tv_external_id="359"),
)

SOURCE_SEED: tuple[SourceSeed, ...] = (
    SourceSeed(
        key=TMDB_SOURCE_KEY,
        name="TMDb",
        type=SourceType.API,
        base_url="https://api.themoviedb.org/3",
        origin_default=CollectionOrigin.AGGREGATOR,
        status=SourceStatus.UNCONFIGURED,
        capabilities={
            "catalog": True,
            "recently_added": False,
            "upcoming": False,
            "charts": False,
            "ordering": False,
            "added_dates": False,
            "seasons_episodes": True,
            "full_pagination": False,
            "data_export": False,
            "requires_credentials": True,
            "requires_contract": False,
            "max_page_size": 20,
            "notes": "Aggregatore: nessuna data di aggiunta, cap 500 pagine.",
        },
    ),
    SourceSeed(
        key=JUSTWATCH_SOURCE_KEY,
        name="JustWatch Partner",
        type=SourceType.API,
        base_url="https://apis.justwatch.com/contentpartner/v2/content",
        origin_default=CollectionOrigin.AGGREGATOR,
        status=SourceStatus.DISABLED,
        capabilities={
            "catalog": True,
            "recently_added": True,
            "upcoming": True,
            "charts": True,
            "ordering": False,
            "added_dates": True,
            "seasons_episodes": True,
            "full_pagination": False,
            "data_export": True,
            "requires_credentials": True,
            "requires_contract": True,
            "notes": "Richiede contratto Partner: disabilitata in questa fase.",
        },
        requires_contract=True,
    ),
    SourceSeed(
        key=JUSTWATCH_PUBLIC_SOURCE_KEY,
        name="JustWatch (endpoint pubblico)",
        type=SourceType.API,
        base_url="https://apis.justwatch.com/graphql",
        origin_default=CollectionOrigin.AGGREGATOR,
        status=SourceStatus.OK,
        capabilities={
            "catalog": True,
            "recently_added": True,
            "upcoming": True,
            "charts": True,
            "ordering": True,
            "added_dates": False,
            "seasons_episodes": True,
            "full_pagination": True,
            "partial_on_error": True,
            "data_export": False,
            "requires_credentials": False,
            "requires_contract": False,
            "max_page_size": 100,
            "notes": (
                "AGGREGATOR: nessuna data di aggiunta, quindi date_basis=UNKNOWN. "
                "Paginazione completa via partizioni releaseYear (tetto 1999 per "
                "query), 100 elementi per pagina. Stagioni ed episodi con offerte. "
                "Throttle locale obbligatorio (1 req/s): nessun rate limit esposto e "
                "nessun avviso prima di un blocco. Un errore, un 429 o uno schema "
                "drift rende lo snapshot INCOMPLETE/ANOMALY: mai valido, mai MIRROR."
            ),
        },
    ),
    SourceSeed(
        key="tvdb",
        name="TheTVDB",
        type=SourceType.API,
        base_url="https://api4.thetvdb.com/v4",
        origin_default=CollectionOrigin.AGGREGATOR,
        status=SourceStatus.UNCONFIGURED,
        capabilities={
            "catalog": False,
            "recently_added": False,
            "upcoming": False,
            "charts": False,
            "ordering": False,
            "added_dates": False,
            "seasons_episodes": True,
            "full_pagination": False,
            "data_export": False,
            "requires_credentials": True,
            "requires_contract": False,
            "provider_catalog": True,
            "country_availability": False,
            "notes": (
                "Metadati e company ID. TheTVDB non dichiara la disponibilità "
                "per paese: non è una fonte di offerte per l'Italia."
            ),
        },
    ),
    SourceSeed(
        key="manual_csv",
        name="CSV manuale",
        type=SourceType.MANUAL_CSV,
        base_url=None,
        origin_default=CollectionOrigin.CUSTOM,
        status=SourceStatus.OK,
        capabilities={
            "catalog": True,
            "recently_added": False,
            "upcoming": False,
            "charts": False,
            "ordering": True,
            "added_dates": False,
            "seasons_episodes": False,
            "full_pagination": True,
            "data_export": False,
            "requires_credentials": False,
            "requires_contract": False,
            "max_page_size": 1000,
            "notes": "Import manuale: nessuna data dichiarata dalla fonte.",
        },
    ),
    # Local pseudo-source: combined collections read valid snapshots of the
    # JustWatch and TMDb collections already in the database. It has no
    # connector on purpose: acquisition is entirely local.
    SourceSeed(
        key=COMBINED_SOURCE_KEY,
        name="Combinata locale",
        type=SourceType.MANUAL_CSV,
        base_url=None,
        origin_default=CollectionOrigin.CUSTOM,
        status=SourceStatus.OK,
        capabilities={
            "catalog": True,
            "recently_added": False,
            "upcoming": False,
            "charts": False,
            "ordering": True,
            "added_dates": False,
            "seasons_episodes": False,
            "full_pagination": True,
            "data_export": False,
            "requires_credentials": False,
            "requires_contract": False,
            "combined_local": True,
            "notes": "Unione/intersezione locale di snapshot JustWatch e TMDb.",
        },
    ),
)


def seed_sources() -> int:
    """Create/update only the source registry, without demo providers/collections."""
    with session_scope() as db:
        sources, created = _upsert_sources(db)
    print(f"fonti create: {created}/{len(SOURCE_SEED)}")
    return 0


def _demo_collection_slugs() -> set[str]:
    slugs: set[str] = set()
    for provider in TMDB_PROVIDER_SEED:
        slugs.add(f"{provider.slug}-movie")
        if provider.tv_external_id is not None:
            slugs.add(f"{provider.slug}-show")
    return slugs


def _demo_collections(db: Session) -> list[Collection]:
    allowed = _demo_collection_slugs()
    return [
        collection
        for collection in db.scalars(select(Collection)).all()
        if collection.slug in allowed
        and (collection.quality_flags or {}).get("unverified_provider_mapping")
        and collection.source_collection_key
        and not str(collection.source_collection_key).startswith("custom:")
    ]


def remove_demo_providers(*, apply: bool = False) -> int:
    """Remove seed providers that no collection references.

    A provider used by an operator-created collection is protected: deleting it
    would leave a dangling catalog. The operator must remove those collections
    explicitly first.
    """
    slugs = tuple(seed.slug for seed in PROVIDER_SEED)
    with session_scope() as db:
        providers = list(db.scalars(select(Provider).where(Provider.slug.in_(slugs))))
        referenced = {
            row.provider_id
            for row in db.scalars(select(Collection)).all()
            if row.provider_id is not None
        }
        removable = [item for item in providers if item.id not in referenced]
        blocked = [item for item in providers if item.id in referenced]
        print(
            f"provider demo trovati: {len(providers)}, "
            f"senza collezioni: {len(removable)}, con collezioni: {len(blocked)}"
        )
        if not apply:
            print("dry-run: usa --apply per rimuovere quelli senza collezioni")
            return 0
        for provider in removable:
            # FKs without ON DELETE: clear observations before the provider.
            db.execute(delete(Availability).where(Availability.provider_id == provider.id))
            db.execute(delete(EpisodeEvent).where(EpisodeEvent.provider_id == provider.id))
            db.delete(provider)
        print(
            f"provider demo rimossi: {len(removable)}"
            + (f", protetti perché usati da collezioni: {len(blocked)}" if blocked else "")
        )
    return 0


def remove_demo_collections(*, apply: bool = False, force: bool = False) -> int:
    """Remove demo TMDb collections, guarding bound collections unless forced.

    Without ``apply`` this is a dry-run. ``force`` also removes collections
    referenced by a binding (and therefore its bindings/snapshots); use it only
    after checking that the operator does not need those lists anymore.
    """
    with session_scope() as db:
        collections = _demo_collections(db)
        bound_ids = {
            row.collection_id
            for row in db.scalars(select(SyncBinding)).all()
            if row.collection_id is not None
        }
        removable = [item for item in collections if item.id not in bound_ids]
        blocked = [item for item in collections if item.id in bound_ids]
        print(
            f"collezioni demo trovate: {len(collections)}, "
            f"senza binding: {len(removable)}, con binding: {len(blocked)}"
        )
        if not apply:
            print(
                "dry-run: usa --apply per rimuovere quelle senza binding"
                + (" e --force per tutte" if blocked else "")
            )
            return 0
        targets = removable + (blocked if force else [])
        for collection in targets:
            # Episode events point at snapshots without ON DELETE: clear the
            # nullable reference before the collection cascade removes them.
            snapshot_ids = select(CollectionSnapshot.id).where(
                CollectionSnapshot.collection_id == collection.id
            )
            db.execute(
                update(EpisodeEvent)
                .where(EpisodeEvent.snapshot_id.in_(snapshot_ids))
                .values(snapshot_id=None)
            )
            db.delete(collection)
        print(
            f"collezioni demo rimosse: {len(targets)}"
            + (f", protette perché con binding: {len(blocked)}" if blocked and not force else "")
        )
    return 0


def seed_reference_data(*, include_collections: bool = False) -> int:
    """Upsert demo providers, sources and mappings; collections are opt-in.

    The normal ``seed-providers`` CLI path must not recreate the demo TMDb
    collections. Tests may request them explicitly to exercise the catalogue.
    """
    with session_scope() as db:
        providers, providers_created = _upsert_providers(db)
        sources, sources_created = _upsert_sources(db)
        mappings_created = _upsert_tmdb_mappings(db, providers, sources[TMDB_SOURCE_KEY])
        justwatch_mappings_created = _upsert_justwatch_mappings(
            db, providers, sources[JUSTWATCH_PUBLIC_SOURCE_KEY]
        )
        collections_created = 0
        if include_collections:
            collections_created = _upsert_tmdb_collections(db, providers, sources[TMDB_SOURCE_KEY])
    collection_total = sum(
        2 if seed.tv_external_id is not None else 1 for seed in TMDB_PROVIDER_SEED
    )
    print(
        f"provider creati: {providers_created}/{len(PROVIDER_SEED)}, "
        f"fonti create: {sources_created}/{len(SOURCE_SEED)}, "
        f"mapping TMDb creati: {mappings_created}/{len(TMDB_PROVIDER_SEED)}, "
        f"mapping JustWatch creati: {justwatch_mappings_created}/{len(PROVIDER_MAPPINGS)}, "
        "collezioni demo create: "
        f"{collections_created}/{collection_total if include_collections else 0}"
    )
    return 0


def _upsert_providers(db: Session) -> tuple[dict[str, Provider], int]:
    providers: dict[str, Provider] = {}
    created = 0
    for seed in PROVIDER_SEED:
        provider = db.scalar(select(Provider).where(Provider.slug == seed.slug))
        if provider is None:
            provider = Provider(slug=seed.slug, name=seed.name, kind=seed.kind)
            db.add(provider)
            db.flush()
            created += 1
        else:
            provider.name = seed.name
            provider.kind = seed.kind
        providers[seed.slug] = provider
    return providers, created


def _upsert_sources(db: Session) -> tuple[dict[str, Source], int]:
    sources: dict[str, Source] = {}
    created = 0
    for seed in SOURCE_SEED:
        source = db.scalar(select(Source).where(Source.key == seed.key))
        if source is None:
            source = Source(
                key=seed.key,
                name=seed.name,
                type=seed.type.value,
                base_url=seed.base_url,
                origin_default=seed.origin_default.value,
                status=seed.status.value,
                capabilities=seed.capabilities,
                requires_contract=seed.requires_contract,
                is_official=seed.is_official,
            )
            db.add(source)
            db.flush()
            created += 1
        else:
            source.name = seed.name
            source.type = seed.type.value
            source.base_url = seed.base_url
            source.origin_default = seed.origin_default.value
            source.capabilities = seed.capabilities
            source.requires_contract = seed.requires_contract
            source.is_official = seed.is_official
        sources[seed.key] = source
    return sources, created


def _upsert_tmdb_mappings(
    db: Session,
    providers: dict[str, Provider],
    tmdb_source: Source,
) -> int:
    created = 0
    for seed in TMDB_PROVIDER_SEED:
        provider = providers[seed.slug]
        metadata = {
            "seed": "docs/phases/phase-02.md",
            "note": "ID TMDb IT: eseguire verify-providers per la conferma live.",
            "movie_provider_id": seed.external_id,
            "tv_provider_id": seed.tv_external_id,
            "movie_verified": False,
            "tv_verified": False,
        }
        existing = providers_repo.get_mapping(
            db,
            provider_id=provider.id,
            source_id=tmdb_source.id,
            country_code=DEFAULT_COUNTRY_CODE,
        )
        if existing is None:
            created += 1
            providers_repo.upsert_mapping(
                db,
                provider_id=provider.id,
                source_id=tmdb_source.id,
                country_code=DEFAULT_COUNTRY_CODE,
                external_provider_id=seed.external_id,
                external_name=provider.name,
                is_primary=True,
                is_verified=False,
                metadata=metadata,
            )
            continue
        # Never downgrade a live-verified mapping back to the seed placeholder.
        if existing.is_verified:
            merged = dict(existing.metadata_json or {})
            merged.update(
                {
                    "movie_provider_id": merged.get("movie_provider_id", seed.external_id),
                    "tv_provider_id": merged.get("tv_provider_id", seed.tv_external_id),
                }
            )
            existing.external_name = existing.external_name or provider.name
            existing.metadata_json = merged
            continue
        # Update in place: creating a second primary mapping would violate the
        # one-primary-per-provider unique index.
        existing.external_provider_id = seed.external_id
        existing.external_name = provider.name
        existing.is_primary = True
        existing.is_verified = False
        existing.metadata_json = metadata
    return created


def _upsert_justwatch_mappings(
    db: Session,
    providers: dict[str, Provider],
    justwatch_source: Source,
) -> int:
    """Install the live-verified IT package mappings on a fresh database.

    ``justwatch-collections`` remains the source of truth: this seed only
    creates missing rows and never overwrites a live verification result. It
    makes the JustWatch provider picker usable immediately after bootstrap,
    instead of requiring a separate CLI run.
    """
    created = 0
    for seed in PROVIDER_MAPPINGS:
        provider = providers[seed.slug]
        existing = providers_repo.get_mapping(
            db,
            provider_id=provider.id,
            source_id=justwatch_source.id,
            country_code=DEFAULT_COUNTRY_CODE,
        )
        if existing is not None:
            continue
        created += 1
        providers_repo.upsert_mapping(
            db,
            provider_id=provider.id,
            source_id=justwatch_source.id,
            country_code=DEFAULT_COUNTRY_CODE,
            external_provider_id=seed.short_name,
            external_name=provider.name,
            is_primary=True,
            is_verified=True,
            metadata={
                "seed": "app/domain/justwatch.py",
                "provider_slug": seed.slug,
                "technical_name": seed.technical_name,
                "clear_name": provider.name,
                "monetization_types": list(seed.monetization_types),
                "verified_at": MAPPING_VERIFIED_AT,
                "verified_on": MAPPING_VERIFIED_AT,
                "movie_external_id": seed.short_name,
                "tv_external_id": seed.short_name,
                "movie_verified": True,
                "tv_verified": True,
            },
        )
    return created


def _upsert_tmdb_collections(
    db: Session,
    providers: dict[str, Provider],
    tmdb_source: Source,
) -> int:
    created = 0
    for seed in TMDB_PROVIDER_SEED:
        provider = providers[seed.slug]
        for media_type in (MediaType.MOVIE, MediaType.SHOW):
            if media_type is MediaType.SHOW and seed.tv_external_id is None:
                continue
            slug = f"{provider.slug}-{media_type.value.lower()}"
            existing = collections_repo.get_collection_by_slug(db, slug)
            if existing is None:
                created += 1
            label = "Film" if media_type is MediaType.MOVIE else "Serie"
            collections_repo.upsert_collection(
                db,
                slug=slug,
                source_id=tmdb_source.id,
                provider_id=provider.id,
                country_code=DEFAULT_COUNTRY_CODE,
                media_type=media_type.value,
                kind=CollectionKind.CATALOG.value,
                origin=CollectionOrigin.AGGREGATOR.value,
                date_basis=DateBasis.UNKNOWN.value,
                name=f"{provider.name} — {label}",
                description=(
                    "Catalogo TMDb per il provider in Italia (disponibilità corrente, "
                    "solo flatrate)."
                ),
                source_collection_key=(
                    f"{seed.tv_external_id if media_type is MediaType.SHOW else seed.external_id}"
                    f":{media_type.value}"
                ),
                source_url=None,
                offer_types=[OfferType.FLATRATE.value],
                filters={
                    "provider_id": (
                        seed.tv_external_id if media_type is MediaType.SHOW else seed.external_id
                    ),
                    "watch_region": DEFAULT_COUNTRY_CODE,
                    "with_watch_monetization_types": "flatrate",
                    "sort_by": "popularity.desc",
                },
                quality_flags={
                    "unverified_provider_mapping": True,
                    "added_date_missing": True,
                },
                sort_mode="POPULARITY",
                is_active=True,
            )
    return created
