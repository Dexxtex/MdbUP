"""Create/refresh JustWatch collections for the providers mapped to the source.

The JustWatch endpoint identifies providers by a short code (``nfx``, ``prv``),
while the app uses canonical slugs (``netflix``, ``prime-video``). The mapping
below was verified against the live ``packages(country: IT, platform: WEB)``
answer on 2026-11-18: a mapping counts as verified only when **both** the
``shortName`` and the ``technicalName`` match, because name matching is
ambiguous (``Apple TV`` is ``atp``/``appletvplus``, not the Apple TV Store
``itu``; ``Amazon Prime Video`` is not ``Amazon Prime Video with Ads``).

The mapping row stays unique per ``(source, country, external id)``: the
per-media-type ids and flags live in ``metadata`` (``movie_external_id``,
``tv_external_id``, ``movie_verified``, ``tv_verified``), mirroring the TMDb
mapping. JustWatch verifies one package for both types, so the two flags always
agree today; keeping them separate lets a future package split without a
schema change.

One live package request feeds the whole sync: mappings, verification, the
``FLATRATE`` check and the collection plan all read the same payload. Providers
without ``FLATRATE`` (Rakuten TV, ``wki``) are verified and reported but get no
collections; providers whose package does not match are reported as unverified
and skipped, never guessed. Collections default to ``offer_types=["FLATRATE"]``.

Upserting a collection only refreshes its metadata and filters: the existing
snapshot chain and ``last_valid_snapshot_id`` are never touched.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.api.errors import ValidationError
from app.connectors.base import SourceCollection
from app.connectors.justwatch.connector import JustWatchConnector
from app.connectors.registry import create_connector
from app.core.config import Settings
from app.db.models import Provider
from app.domain.enums import CollectionKind, CollectionOrigin, DateBasis, OfferType
from app.integrations.justwatch.models import JustWatchPackage
from app.repositories import collections as collections_repo
from app.repositories import providers as providers_repo
from app.repositories import sources as sources_repo

JUSTWATCH_SOURCE_KEY = "justwatch"

# Verified live on 2026-11-18 with one packages(country: IT, platform: WEB) call.
MAPPING_VERIFIED_AT = "2026-11-18"


@dataclass(frozen=True)
class JustWatchProviderMapping:
    slug: str
    short_name: str
    technical_name: str


PROVIDER_MAPPINGS: tuple[JustWatchProviderMapping, ...] = (
    JustWatchProviderMapping("netflix", "nfx", "netflix"),
    JustWatchProviderMapping("prime-video", "prv", "amazonprimevideo"),
    JustWatchProviderMapping("disney-plus", "dnp", "disneyplus"),
    JustWatchProviderMapping("apple-tv-plus", "atp", "appletvplus"),
    JustWatchProviderMapping("now", "ntv", "nowtv"),
    JustWatchProviderMapping("paramount-plus", "pmp", "paramountplus"),
    JustWatchProviderMapping("raiplay", "rai", "raiplay"),
    JustWatchProviderMapping("mediaset-infinity", "msp", "mediasetplay"),
    JustWatchProviderMapping("infinity-plus", "inf", "infinity"),
    JustWatchProviderMapping("timvision", "tvi", "timvision"),
    JustWatchProviderMapping("rakuten-tv", "wki", "wuaki"),
    JustWatchProviderMapping("mubi", "mbi", "mubi"),
)

MAPPING_BY_SLUG = {mapping.slug: mapping for mapping in PROVIDER_MAPPINGS}

DEFAULT_OFFER_TYPES = (OfferType.FLATRATE.value,)

_SLUG_SUFFIX = {
    CollectionKind.CATALOG: "",
    CollectionKind.CHART: "-chart",
    CollectionKind.RECENTLY_ADDED: "-new",
    CollectionKind.UPCOMING: "-upcoming",
}

_DESCRIPTION = {
    CollectionKind.CATALOG: "Catalogo JustWatch per il provider in Italia (solo flatrate).",
    CollectionKind.CHART: "Classifica JustWatch (rank dell'aggregatore, non Top 10 ufficiale).",
    CollectionKind.RECENTLY_ADDED: "Novità JustWatch (etichette relative, nessuna data).",
    CollectionKind.UPCOMING: "In arrivo su JustWatch (non disponibili, fuori dal catalogo).",
}


@dataclass(frozen=True)
class JustWatchSyncOutcome:
    mappings: int
    collections_created: int
    collections_updated: int
    skipped_providers: tuple[str, ...] = ()
    unverified_providers: tuple[str, ...] = ()
    unmapped_packages: tuple[str, ...] = ()


def sync_collections(
    db: Session,
    settings: Settings,
    *,
    country_code: str = "IT",
    provider_slugs: list[str] | None = None,
) -> JustWatchSyncOutcome:
    """Verify the provider mappings and upsert their collections."""
    source = sources_repo.get_source_by_key(db, JUSTWATCH_SOURCE_KEY)
    if source is None:
        raise ValidationError(
            "Fonte JustWatch non trovata: eseguire prima 'seed-providers'.",
            code="SOURCE_MISSING",
        )

    wanted = provider_slugs or list(MAPPING_BY_SLUG)
    connector = create_connector(db, settings, JUSTWATCH_SOURCE_KEY)
    if not isinstance(connector, JustWatchConnector):
        raise ValidationError(
            "Il connettore JustWatch non è disponibile.", code="CONNECTOR_MISSING"
        )
    try:
        # One live request for the whole sync: every check below reads it.
        packages = list(connector.list_packages(country_code))
        by_short = {package.short_name: package for package in packages}
        verified_slugs: list[str] = []
        unverified: list[str] = []
        no_flatrate: list[str] = []
        verified_external_ids: set[str] = set()
        for slug in wanted:
            mapping = MAPPING_BY_SLUG.get(slug)
            if mapping is None:
                unverified.append(slug)
                continue
            package = by_short.get(mapping.short_name)
            if not _matches(package, mapping):
                unverified.append(mapping.short_name)
                continue
            verified_slugs.append(slug)
            if "FLATRATE" not in {value.upper() for value in package.monetization_types}:
                # Verified, but a catalog built on it would be empty by definition.
                no_flatrate.append(mapping.short_name)
                continue
            verified_external_ids.add(mapping.short_name)
        _upsert_mappings(db, source.id, country_code, verified_slugs, by_short)
        planned = connector.list_collections(
            country_code,
            [package for package in packages if package.short_name in verified_external_ids],
        )
    finally:
        connector.close()

    by_external = _providers_by_external_id(db, source.id, country_code)
    created = 0
    updated = 0
    skipped: list[str] = []
    for collection in planned:
        if collection.provider_external_id not in verified_external_ids:
            continue
        provider = by_external.get(collection.provider_external_id)
        if provider is None:
            if collection.provider_external_id not in skipped:
                skipped.append(collection.provider_external_id)
            continue
        slug = _collection_slug(provider.slug, collection)
        existed = collections_repo.get_collection_by_slug(db, slug) is not None
        collections_repo.upsert_collection(
            db,
            slug=slug,
            source_id=source.id,
            provider_id=provider.id,
            country_code=country_code,
            media_type=collection.media_type.value,
            kind=collection.kind.value,
            origin=CollectionOrigin.AGGREGATOR.value,
            date_basis=DateBasis.UNKNOWN.value,
            name=collection.name,
            description=_DESCRIPTION[collection.kind],
            source_collection_key=collection.key,
            source_url=None,
            offer_types=list(DEFAULT_OFFER_TYPES),
            filters=dict(collection.metadata),
            is_active=True,
        )
        if existed:
            updated += 1
        else:
            created += 1
    curated_short_names = {mapping.short_name for mapping in PROVIDER_MAPPINGS}
    return JustWatchSyncOutcome(
        mappings=len(verified_slugs),
        collections_created=created,
        collections_updated=updated,
        skipped_providers=tuple(no_flatrate + skipped),
        unverified_providers=tuple(unverified),
        unmapped_packages=tuple(
            sorted(
                package.short_name
                for package in packages
                if package.short_name not in curated_short_names
            )
        ),
    )


def _matches(package: JustWatchPackage | None, mapping: JustWatchProviderMapping) -> bool:
    """A mapping is verified only when shortName and technicalName both match."""
    if package is None:
        return False
    return (
        package.short_name == mapping.short_name
        and (package.technical_name or "").strip().lower() == mapping.technical_name
    )


def _upsert_mappings(
    db: Session,
    source_id: uuid.UUID,
    country_code: str,
    provider_slugs: list[str],
    packages: dict[str, JustWatchPackage],
) -> int:
    verified_at = datetime.now(UTC).isoformat()
    count = 0
    for slug in provider_slugs:
        mapping = MAPPING_BY_SLUG[slug]
        package = packages[mapping.short_name]
        provider = providers_repo.get_provider_by_slug(db, slug)
        if provider is None:
            continue
        verified = _matches(package, mapping)
        providers_repo.upsert_mapping(
            db,
            provider_id=provider.id,
            source_id=source_id,
            country_code=country_code,
            external_provider_id=mapping.short_name,
            external_name=package.name,
            is_primary=True,
            is_verified=verified,
            metadata={
                "seed": "app/services/justwatch_collections.py",
                "provider_slug": slug,
                "technical_name": package.technical_name,
                "clear_name": package.name,
                "monetization_types": list(package.monetization_types),
                "verified_at": verified_at,
                "verified_on": MAPPING_VERIFIED_AT,
                # Stesso shortName per entrambi i tipi, ma salvato separatamente
                # come per i mapping TMDb: una riga sola, nessun duplicato.
                "movie_external_id": mapping.short_name,
                "tv_external_id": mapping.short_name,
                "movie_verified": verified,
                "tv_verified": verified,
            },
        )
        count += 1
    return count


def _providers_by_external_id(
    db: Session,
    source_id: uuid.UUID,
    country_code: str,
) -> dict[str, Provider]:
    result: dict[str, Provider] = {}
    for mapping in providers_repo.list_mappings(db, source_id=source_id, country_code=country_code):
        provider = providers_repo.get_provider(db, mapping.provider_id)
        if provider is not None:
            result.setdefault(mapping.external_provider_id, provider)
    return result


def _collection_slug(provider_slug: str, collection: SourceCollection) -> str:
    suffix = _SLUG_SUFFIX.get(collection.kind, "")
    return f"{provider_slug}-{collection.media_type.value.lower()}-justwatch{suffix}"
