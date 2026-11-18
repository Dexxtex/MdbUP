"""Create/refresh JustWatch collections for the providers mapped to the source.

The JustWatch endpoint identifies providers by a short code (``nfx``, ``prv``),
while the app uses canonical slugs (``netflix``, ``prime-video``). The mapping
below was verified against the live provider list for Italy; it is explicit on
purpose, because name matching is ambiguous (``Apple TV`` vs ``Apple TV Store``,
``Amazon Prime Video`` vs ``Amazon Prime Video with Ads``).

Collections are created per provider and per kind, so every collection has a
provider as the schema requires. Nothing is created for a provider without a
mapping: those are counted and reported, never guessed.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.api.errors import ValidationError
from app.connectors.base import SourceCollection
from app.connectors.justwatch.connector import JustWatchConnector
from app.connectors.registry import create_connector
from app.core.config import Settings
from app.db.models import Provider
from app.domain.enums import CollectionKind, CollectionOrigin, DateBasis, OfferType
from app.repositories import collections as collections_repo
from app.repositories import providers as providers_repo
from app.repositories import sources as sources_repo

JUSTWATCH_SOURCE_KEY = "justwatch"

# Canonical provider slug -> JustWatch package short code, verified for IT.
PROVIDER_SHORT_NAMES: dict[str, str] = {
    "netflix": "nfx",
    "prime-video": "prv",
    "disney-plus": "dnp",
    "now": "ntv",
    "timvision": "tvi",
    "infinity-plus": "inf",
    "rakuten-tv": "wki",
    "mubi": "mbi",
    "apple-tv-plus": "atp",
    "paramount-plus": "pmp",
    "raiplay": "rai",
    "mediaset-infinity": "msp",
}

_SLUG_SUFFIX = {
    CollectionKind.CATALOG: "",
    CollectionKind.CHART: "-chart",
    CollectionKind.RECENTLY_ADDED: "-new",
    CollectionKind.UPCOMING: "-upcoming",
}

_DESCRIPTION = {
    CollectionKind.CATALOG: "Catalogo JustWatch per il provider in Italia.",
    CollectionKind.CHART: "Classifica streaming JustWatch (rank giornaliero).",
    CollectionKind.RECENTLY_ADDED: "Novità JustWatch (etichette relative, nessuna data).",
    CollectionKind.UPCOMING: "In arrivo su JustWatch (etichette relative, nessuna data).",
}

_ALL_OFFER_TYPES = (
    OfferType.FLATRATE.value,
    OfferType.RENT.value,
    OfferType.BUY.value,
    OfferType.ADS.value,
    OfferType.FREE.value,
)


@dataclass(frozen=True)
class JustWatchSyncOutcome:
    mappings: int
    collections_created: int
    collections_updated: int
    skipped_providers: tuple[str, ...]


def sync_collections(
    db: Session,
    settings: Settings,
    *,
    country_code: str = "IT",
    provider_slugs: list[str] | None = None,
) -> JustWatchSyncOutcome:
    """Upsert provider mappings and collections for the JustWatch source."""
    source = sources_repo.get_source_by_key(db, JUSTWATCH_SOURCE_KEY)
    if source is None:
        raise ValidationError(
            "Fonte JustWatch non trovata: eseguire prima 'seed-providers'.",
            code="SOURCE_MISSING",
        )

    wanted = provider_slugs or list(PROVIDER_SHORT_NAMES)
    mappings = _upsert_mappings(db, source.id, country_code, wanted)
    by_external = _providers_by_external_id(db, source.id, country_code)

    connector = create_connector(db, settings, JUSTWATCH_SOURCE_KEY)
    if not isinstance(connector, JustWatchConnector):
        raise ValidationError(
            "Il connettore JustWatch non è disponibile.", code="CONNECTOR_MISSING"
        )
    try:
        monetization = connector.provider_monetization_types(country_code)
        planned = connector.list_collections(country_code)
    finally:
        connector.close()

    created = 0
    updated = 0
    skipped: list[str] = []
    for collection in planned:
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
            offer_types=_offer_types(monetization.get(collection.provider_external_id)),
            filters=dict(collection.metadata),
            is_active=True,
        )
        if existed:
            updated += 1
        else:
            created += 1
    return JustWatchSyncOutcome(
        mappings=mappings,
        collections_created=created,
        collections_updated=updated,
        skipped_providers=tuple(skipped),
    )


def _upsert_mappings(
    db: Session,
    source_id: uuid.UUID,
    country_code: str,
    provider_slugs: list[str],
) -> int:
    count = 0
    for slug in provider_slugs:
        external_id = PROVIDER_SHORT_NAMES.get(slug)
        if external_id is None:
            continue
        provider = providers_repo.get_provider_by_slug(db, slug)
        if provider is None:
            continue
        providers_repo.upsert_mapping(
            db,
            provider_id=provider.id,
            source_id=source_id,
            country_code=country_code,
            external_provider_id=external_id,
            external_name=provider.name,
            is_primary=True,
            is_verified=False,
            metadata={"seed": "app/services/justwatch_collections.py"},
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


def _offer_types(monetization: tuple[str, ...] | None) -> list[str]:
    if not monetization:
        return list(_ALL_OFFER_TYPES)
    known = [value for value in monetization if value in _ALL_OFFER_TYPES]
    return known or list(_ALL_OFFER_TYPES)
