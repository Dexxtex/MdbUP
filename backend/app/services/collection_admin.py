"""Create/update collections from the UI without the CLI.

CATALOG and RECENTLY_ADDED collections call TMDb. CUSTOM_FILTER collections are
computed locally from already-acquired valid snapshots: they never add external
API calls, and can union several providers (for example Netflix + Prime Video +
Disney+).
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.connectors import registry
from app.core.config import Settings
from app.db.models import Collection, ProviderMapping
from app.domain.commands import CollectionCreateIn, CollectionUpdateIn
from app.domain.enums import (
    COMBINED_DERIVATION,
    COMBINED_SOURCE_KEY,
    AuditActorType,
    CollectionKind,
    CollectionOrigin,
    DateBasis,
    MediaType,
    OfferType,
)
from app.domain.errors import ConflictError, NotFoundError, SourceUnavailableError, ValidationError
from app.domain.genres import genres_for
from app.jobs import tasks
from app.repositories import audit
from app.repositories import collections as collections_repo
from app.repositories import providers as providers_repo
from app.repositories import snapshots as snapshots_repo
from app.repositories import sources as sources_repo
from app.services import collections as collections_service
from app.services.collections import CollectionSummary

_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_LANGUAGE = re.compile(r"^[a-z]{2,3}$")
_LOCAL_SORTS = {
    "vote_average.desc",
    "vote_count.desc",
    "release_date.desc",
    "title.asc",
    "popularity.desc",
}

JUSTWATCH_SOURCE_KEY = "justwatch"
TMDB_SOURCE_KEY = "tmdb"

# Kinds JustWatch can serve. ``CUSTOM_FILTER`` stays a local, TMDb-driven concept.
_JUSTWATCH_KINDS = {
    CollectionKind.CATALOG.value,
    CollectionKind.RECENTLY_ADDED.value,
    CollectionKind.UPCOMING.value,
    CollectionKind.CHART.value,
}
_TMDB_KINDS = {
    CollectionKind.CATALOG.value,
    CollectionKind.RECENTLY_ADDED.value,
    CollectionKind.CUSTOM_FILTER.value,
}

_JUSTWATCH_DESCRIPTION = {
    CollectionKind.CATALOG.value: "Catalogo JustWatch (solo flatrate) per il provider in Italia.",
    CollectionKind.RECENTLY_ADDED.value: "Novità JustWatch: etichette relative, nessuna data.",
    CollectionKind.UPCOMING.value: "In arrivo JustWatch: non disponibili, fuori dal catalogo.",
    CollectionKind.CHART.value: (
        "Classifica JustWatch: rank dell'aggregatore, non Top 10 ufficiale."
    ),
}


def _justwatch_mapping(db: Session, provider_id: uuid.UUID) -> ProviderMapping:
    """Verified JustWatch mapping for the provider, or an explicit error."""
    source = sources_repo.get_source_by_key(db, JUSTWATCH_SOURCE_KEY)
    if source is None:
        raise ValidationError("Fonte JustWatch non trovata.", code="SOURCE_MISSING")
    mapping = providers_repo.get_mapping(
        db, provider_id=provider_id, source_id=source.id, country_code="IT"
    )
    if mapping is None or not mapping.is_verified:
        raise ValidationError(
            "Il provider non ha un mapping JustWatch verificato: eseguire 'justwatch-collections'.",
            code="PROVIDER_NOT_VERIFIED",
            details={"provider_id": str(provider_id), "source_key": JUSTWATCH_SOURCE_KEY},
        )
    return mapping


def _justwatch_offer_types(
    requested: Sequence[str] | None,
    mapping: ProviderMapping,
) -> list[str]:
    """Validate the requested offer types against the live package capabilities."""
    metadata = mapping.metadata_json or {}
    supported = {str(value).upper() for value in metadata.get("monetization_types") or []}
    values = [str(value).upper() for value in (requested or [OfferType.FLATRATE.value])]
    unsupported = [value for value in values if supported and value not in supported]
    if unsupported:
        raise ValidationError(
            "Il provider JustWatch non offre questi tipi di offerta.",
            code="JUSTWATCH_OFFER_TYPE_UNSUPPORTED",
            details={"unsupported": unsupported, "supported": sorted(supported)},
        )
    return values


def _justwatch_filters(
    *,
    external_provider_id: str,
    media_type: str,
    offer_types: list[str],
    year_from: int | None = None,
    year_to: int | None = None,
    genres: list[str] | None = None,
) -> dict[str, object]:
    """Filters the connector reads: package, region, media type, offers, years."""
    filters: dict[str, object] = {
        "packages": [external_provider_id],
        "watch_region": "IT",
        "media_type": media_type,
        "offer_types": offer_types,
    }
    if year_from is not None:
        filters["year_from"] = int(year_from)
    if year_to is not None:
        filters["year_to"] = int(year_to)
    if genres:
        filters["genres"] = list(genres)
    return filters


def _justwatch_quality_flags(kind: str) -> dict[str, object]:
    flags: dict[str, object] = {
        "aggregator": True,
        "added_date_missing": True,
        "provider_mapping_verified": True,
    }
    if kind == CollectionKind.CHART.value:
        flags["chart_label"] = "Classifica JustWatch"
    return flags


def list_genres(media_type: str) -> list[dict[str, object]]:
    return [{"id": genre_id, "name": name} for genre_id, name in genres_for(media_type)]


def _validate_slug(slug: str) -> None:
    if not _SLUG.match(slug):
        raise ValidationError(
            "Slug non valido: usare minuscole, numeri e trattini.",
            code="INVALID_SLUG",
        )


def _validate_genres(media_type: str, genre_ids: list[int]) -> list[int]:
    allowed = {genre_id for genre_id, _ in genres_for(media_type)}
    invalid = [genre_id for genre_id in genre_ids if genre_id not in allowed]
    if invalid:
        raise ValidationError(
            "Genere TMDb non valido per questo tipo media.",
            code="INVALID_GENRE",
            details={"invalid": invalid, "allowed": sorted(allowed)},
        )
    return list(dict.fromkeys(genre_ids))


def _validate_local_filters(
    *,
    media_type: str,
    genre_ids: list[int],
    exclude_genre_ids: list[int],
    original_language: str | None,
    local_sort_by: str,
) -> tuple[list[int], list[int]]:
    included = _validate_genres(media_type, genre_ids)
    excluded = _validate_genres(media_type, exclude_genre_ids)
    overlap = sorted(set(included) & set(excluded))
    if overlap:
        raise ValidationError(
            "Un genere non può essere incluso ed escluso contemporaneamente.",
            code="LOCAL_FILTER_GENRE_CONFLICT",
            details={"genres": overlap},
        )
    if original_language and not _LANGUAGE.match(original_language):
        raise ValidationError(
            "La lingua originale deve essere un codice ISO 639-1/639-2 (es. it, en).",
            code="LOCAL_FILTER_LANGUAGE_INVALID",
        )
    if local_sort_by not in _LOCAL_SORTS:
        raise ValidationError(
            "Ordinamento locale non valido.",
            code="LOCAL_FILTER_SORT_INVALID",
            details={"allowed": sorted(_LOCAL_SORTS)},
        )
    return included, excluded


def _validate_local_sources(
    db: Session, source_collection_ids: list[uuid.UUID], *, media_type: str
) -> list[Collection]:
    if not source_collection_ids:
        raise ValidationError(
            "Una raccolta combinata richiede almeno una collezione sorgente.",
            code="LOCAL_FILTER_SOURCES_MISSING",
        )
    sources: list[Collection] = []
    for source_id in source_collection_ids:
        source = collections_repo.get_collection(db, source_id)
        if source is None:
            raise ValidationError(
                "Collezione sorgente non trovata.",
                code="LOCAL_FILTER_SOURCE_MISSING",
                details={"source_collection_id": str(source_id)},
            )
        if source.media_type != media_type:
            raise ValidationError(
                "Tutte le collezioni sorgente devono avere lo stesso tipo media.",
                code="LOCAL_FILTER_SOURCE_MISMATCH",
                details={"source_collection_id": str(source_id)},
            )
        sources.append(source)
    return sources


def _validate_combined_sources(
    db: Session,
    source_collection_ids: list[uuid.UUID],
    *,
    media_type: str,
) -> list[Collection]:
    """Combined collections need at least two sources, each with a valid snapshot."""
    if len(source_collection_ids) < 2:
        raise ValidationError(
            "Una collezione combinata richiede almeno due collezioni sorgente.",
            code="COMBINED_LOCAL_SOURCES_MIN",
            details={"source_collection_ids": [str(item) for item in source_collection_ids]},
        )
    sources = _validate_local_sources(db, source_collection_ids, media_type=media_type)
    for source in sources:
        snapshot = (
            snapshots_repo.get_snapshot(db, source.last_valid_snapshot_id)
            if source.last_valid_snapshot_id is not None
            else None
        )
        if snapshot is None or not snapshot.is_valid:
            raise ValidationError(
                "Ogni collezione sorgente combinata deve avere uno snapshot valido.",
                code="COMBINED_LOCAL_SOURCE_INVALID",
                details={"source_collection_slug": source.slug},
            )
    return sources


def _provider_external_id(db: Session, provider_id: uuid.UUID, media_type: str) -> str:
    source = sources_repo.get_source_by_key(db, "tmdb")
    if source is None:
        raise ValidationError("Fonte TMDb non trovata.", code="SOURCE_MISSING")
    mapping = providers_repo.get_mapping(
        db, provider_id=provider_id, source_id=source.id, country_code="IT"
    )
    if mapping is None:
        raise ValidationError(
            "Mapping TMDb mancante per il provider.",
            code="PROVIDER_NOT_VERIFIED",
        )
    metadata = mapping.metadata_json or {}
    verified = bool(
        metadata.get("tv_verified")
        if media_type == MediaType.SHOW.value
        else metadata.get("movie_verified")
    )
    if not verified:
        raise ValidationError(
            "Il provider non è verificato live per questo tipo media: eseguire verify-providers.",
            code="PROVIDER_NOT_VERIFIED",
            details={"provider_id": str(provider_id), "media_type": media_type},
        )
    external_id = (
        metadata.get("tv_provider_id")
        if media_type == MediaType.SHOW.value
        else metadata.get("movie_provider_id")
    )
    if external_id is None:
        raise ValidationError(
            "ID TMDb mancante per questo tipo media.",
            code="PROVIDER_NOT_VERIFIED",
        )
    return str(external_id)


def _validate_source_collection(
    db: Session,
    source_collection_id: uuid.UUID,
    *,
    provider_id: uuid.UUID,
    media_type: str,
) -> Collection:
    source = collections_repo.get_collection(db, source_collection_id)
    if source is None:
        raise ValidationError(
            "Collezione sorgente non trovata.",
            code="DERIVATION_SOURCE_MISSING",
        )
    if source.provider_id != provider_id or source.media_type != media_type:
        raise ValidationError(
            "La collezione sorgente deve avere lo stesso provider e tipo media.",
            code="DERIVATION_SOURCE_MISMATCH",
        )
    if source.kind != CollectionKind.CATALOG.value:
        raise ValidationError(
            "La baseline deve essere una collezione CATALOG.",
            code="DERIVATION_SOURCE_NOT_CATALOG",
        )
    filters = source.filters or {}
    if filters.get("with_genres"):
        raise ValidationError(
            "La baseline deve essere il catalogo completo, non una collezione di genere.",
            code="DERIVATION_SOURCE_NOT_FULL_CATALOG",
        )
    return source


def _build_filters(
    *,
    provider_external_id: str,
    media_type: str,
    genre_ids: list[int],
    monetization_type: str,
    kind: str,
    source_collection_id: uuid.UUID | None,
    window_days: int | None,
    shared_snapshot_collection_id: uuid.UUID | None,
    source_collections: list[Collection] | None = None,
    exclude_genre_ids: list[int] | None = None,
    min_vote_average: float | None = None,
    min_vote_count: int | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    original_language: str | None = None,
    local_sort_by: str = "vote_average.desc",
    derivation: str = "LOCAL_FILTER",
    combine_mode: str | None = None,
) -> dict[str, object]:
    if kind == CollectionKind.CUSTOM_FILTER.value:
        filters: dict[str, object] = {
            "derivation": derivation,
            "source_collection_ids": [str(source.id) for source in source_collections or []],
            "provider_ids": [
                str(provider_id)
                for provider_id in dict.fromkeys(
                    source.provider_id for source in source_collections or []
                )
            ],
            "media_type": media_type,
            "watch_region": "IT",
            "sort_by": local_sort_by,
        }
        if combine_mode is not None:
            filters["combine_mode"] = combine_mode
        if genre_ids:
            filters["with_genres"] = ",".join(str(genre_id) for genre_id in genre_ids)
        if exclude_genre_ids:
            filters["exclude_genres"] = ",".join(str(genre_id) for genre_id in exclude_genre_ids)
        if min_vote_average is not None:
            filters["min_vote_average"] = float(min_vote_average)
        if min_vote_count is not None:
            filters["min_vote_count"] = int(min_vote_count)
        if year_from is not None:
            filters["year_from"] = int(year_from)
        if year_to is not None:
            filters["year_to"] = int(year_to)
        if original_language:
            filters["original_language"] = original_language
        return filters

    filters = {
        "provider_id": provider_external_id,
        "watch_region": "IT",
        "with_watch_monetization_types": monetization_type.lower(),
        "sort_by": "popularity.desc",
    }
    if genre_ids:
        filters["with_genres"] = ",".join(str(genre_id) for genre_id in genre_ids)
    if kind == CollectionKind.RECENTLY_ADDED.value:
        filters["derivation"] = "RECENTLY_DETECTED"
        filters["source_collection_id"] = str(source_collection_id)
        filters["window_days"] = int(window_days or 14)
    if shared_snapshot_collection_id is not None:
        filters["shared_snapshot_collection_id"] = str(shared_snapshot_collection_id)
    return filters


def _custom_quality_flags(sources: list[Collection]) -> dict[str, object]:
    return {
        "local_filter": True,
        "multi_provider": len({source.provider_id for source in sources}) > 1,
        "official_provider_list": False,
        "source_collection_slugs": [source.slug for source in sources],
    }


def create_collection(
    db: Session,
    settings: Settings,
    payload: CollectionCreateIn,
    *,
    actor_user_id: uuid.UUID | None = None,
) -> CollectionSummary:
    _validate_slug(payload.slug)
    if collections_repo.get_collection_by_slug(db, payload.slug) is not None:
        raise ConflictError(
            "Esiste già una collezione con questo slug.",
            code="COLLECTION_EXISTS",
            details={"slug": payload.slug},
        )
    if payload.source_key == COMBINED_SOURCE_KEY:
        return _create_combined_collection(db, payload, actor_user_id=actor_user_id)
    if payload.source_key == JUSTWATCH_SOURCE_KEY:
        return _create_justwatch_collection(db, payload, actor_user_id=actor_user_id)
    if payload.kind not in _TMDB_KINDS:
        raise ValidationError(
            "TMDb non supporta questo tipo di collezione: usare source_key=justwatch.",
            code="KIND_NOT_SUPPORTED",
            details={"kind": payload.kind, "source_key": TMDB_SOURCE_KEY},
        )
    source = sources_repo.get_source_by_key(db, TMDB_SOURCE_KEY)
    if source is None:
        raise ValidationError("Fonte TMDb non trovata.", code="SOURCE_MISSING")

    if payload.kind == CollectionKind.CUSTOM_FILTER.value:
        sources = _validate_local_sources(
            db, payload.source_collection_ids, media_type=payload.media_type
        )
        provider_id = payload.provider_id or sources[0].provider_id
        provider = providers_repo.get_provider(db, provider_id)
        if provider is None:
            raise NotFoundError("Provider non trovato.", details={"provider_id": str(provider_id)})
        if provider.id not in {item.provider_id for item in sources}:
            raise ValidationError(
                "Il provider principale deve essere uno dei provider delle collezioni sorgente.",
                code="LOCAL_FILTER_PROVIDER_MISMATCH",
            )
        genre_ids, exclude_genre_ids = _validate_local_filters(
            media_type=payload.media_type,
            genre_ids=payload.genre_ids,
            exclude_genre_ids=payload.exclude_genre_ids,
            original_language=payload.original_language,
            local_sort_by=payload.local_sort_by,
        )
        filters = _build_filters(
            provider_external_id="",
            media_type=payload.media_type,
            genre_ids=genre_ids,
            monetization_type=payload.monetization_type,
            kind=payload.kind,
            source_collection_id=None,
            window_days=None,
            shared_snapshot_collection_id=None,
            source_collections=sources,
            exclude_genre_ids=exclude_genre_ids,
            min_vote_average=payload.min_vote_average,
            min_vote_count=payload.min_vote_count,
            year_from=payload.year_from,
            year_to=payload.year_to,
            original_language=payload.original_language,
            local_sort_by=payload.local_sort_by,
        )
        collection = collections_repo.upsert_collection(
            db,
            slug=payload.slug,
            source_id=source.id,
            provider_id=provider.id,
            country_code="IT",
            media_type=payload.media_type,
            kind=payload.kind,
            origin=CollectionOrigin.CUSTOM.value,
            date_basis=DateBasis.UNKNOWN.value,
            name=payload.name,
            description=payload.description
            or (
                "Raccolta combinata/filtrata localmente da "
                f"{len(sources)} collezioni. Non è una lista ufficiale dei provider."
            ),
            source_collection_key=f"custom:{payload.slug}",
            source_url=None,
            offer_types=[payload.monetization_type],
            filters=filters,
            quality_flags=_custom_quality_flags(sources),
            sort_mode="CUSTOM",
            is_active=payload.is_active,
        )
        audit.record(
            db,
            action="collection_created",
            entity_type="collection",
            entity_id=collection.id,
            actor_user_id=actor_user_id,
            actor_type=AuditActorType.USER if actor_user_id else AuditActorType.SYSTEM,
            after={
                "slug": collection.slug,
                "kind": collection.kind,
                "source_collections": [str(item.id) for item in sources],
            },
        )
        db.commit()
        return collections_service.get_collection(db, collection.id)

    if payload.provider_id is None:
        raise ValidationError(
            "provider_id è obbligatorio per una collezione catalogo o 'Appena rilevati'.",
            code="PROVIDER_REQUIRED",
        )
    provider = providers_repo.get_provider(db, payload.provider_id)
    if provider is None:
        raise NotFoundError(
            "Provider non trovato.", details={"provider_id": str(payload.provider_id)}
        )
    genre_ids = _validate_genres(payload.media_type, payload.genre_ids)
    provider_external_id = _provider_external_id(db, provider.id, payload.media_type)
    if payload.kind == CollectionKind.RECENTLY_ADDED.value:
        if payload.monetization_type != OfferType.FLATRATE.value:
            raise ValidationError(
                "Le collezioni 'Appena rilevati' usano solo FLATRATE.",
                code="DERIVATION_REQUIRES_FLATRATE",
            )
        if payload.source_collection_id is None:
            raise ValidationError(
                "source_collection_id è obbligatorio per 'Appena rilevati'.",
                code="DERIVATION_SOURCE_MISSING",
            )
        _validate_source_collection(
            db,
            payload.source_collection_id,
            provider_id=provider.id,
            media_type=payload.media_type,
        )
    if payload.shared_snapshot_collection_id is not None:
        _validate_source_collection(
            db,
            payload.shared_snapshot_collection_id,
            provider_id=provider.id,
            media_type=payload.media_type,
        )
    filters = _build_filters(
        provider_external_id=provider_external_id,
        media_type=payload.media_type,
        genre_ids=genre_ids,
        monetization_type=payload.monetization_type,
        kind=payload.kind,
        source_collection_id=payload.source_collection_id,
        window_days=payload.window_days,
        shared_snapshot_collection_id=payload.shared_snapshot_collection_id,
    )
    origin = (
        CollectionOrigin.CUSTOM.value
        if payload.kind == CollectionKind.RECENTLY_ADDED.value
        else CollectionOrigin.AGGREGATOR.value
    )
    date_basis = (
        DateBasis.APP_FIRST_SEEN.value
        if payload.kind == CollectionKind.RECENTLY_ADDED.value
        else DateBasis.UNKNOWN.value
    )
    collection = collections_repo.upsert_collection(
        db,
        slug=payload.slug,
        source_id=source.id,
        provider_id=provider.id,
        country_code="IT",
        media_type=payload.media_type,
        kind=payload.kind,
        origin=origin,
        date_basis=date_basis,
        name=payload.name,
        description=payload.description,
        source_collection_key=f"custom:{payload.slug}",
        source_url=None,
        offer_types=[payload.monetization_type],
        filters=filters,
        quality_flags={
            "provider_mapping_verified": True,
            "added_date_missing": payload.monetization_type == OfferType.FLATRATE.value,
            "derivation": filters.get("derivation"),
        },
        sort_mode="POPULARITY",
        is_active=payload.is_active,
    )
    audit.record(
        db,
        action="collection_created",
        entity_type="collection",
        entity_id=collection.id,
        actor_user_id=actor_user_id,
        actor_type=AuditActorType.USER if actor_user_id else AuditActorType.SYSTEM,
        after={
            "slug": collection.slug,
            "provider_id": str(provider.id),
            "media_type": collection.media_type,
            "kind": collection.kind,
        },
    )
    db.commit()
    return collections_service.get_collection(db, collection.id)


def update_collection(
    db: Session,
    settings: Settings,
    collection_id: uuid.UUID,
    payload: CollectionUpdateIn,
    *,
    actor_user_id: uuid.UUID | None = None,
) -> CollectionSummary:
    collection = collections_repo.get_collection(db, collection_id)
    if collection is None:
        raise NotFoundError(
            "Collezione non trovata.", details={"collection_id": str(collection_id)}
        )
    if (
        payload.kind is not None
        and payload.kind != collection.kind
        and snapshots_repo.count_snapshots(db, collection.id) > 0
    ):
        raise ConflictError(
            "Non si può cambiare tipo a una collezione con snapshot esistenti.",
            code="COLLECTION_HAS_SNAPSHOTS",
        )
    kind = payload.kind or collection.kind
    media_type = collection.media_type
    existing_filters = collection.filters or {}
    current_source = sources_repo.get_source(db, collection.source_id)

    if current_source is not None and current_source.key == COMBINED_SOURCE_KEY:
        return _update_combined_collection(db, collection, payload, actor_user_id=actor_user_id)
    if current_source is not None and current_source.key == JUSTWATCH_SOURCE_KEY:
        return _update_justwatch_collection(db, collection, payload, actor_user_id=actor_user_id)
    if payload.source_key is not None and payload.source_key != TMDB_SOURCE_KEY:
        raise ValidationError(
            "La fonte di una collezione esistente non può essere cambiata.",
            code="SOURCE_KEY_IMMUTABLE",
            details={"source_key": current_source.key if current_source else None},
        )
    if kind not in _TMDB_KINDS:
        raise ValidationError(
            "TMDb non supporta questo tipo di collezione: usare source_key=justwatch.",
            code="KIND_NOT_SUPPORTED",
            details={"kind": kind, "source_key": TMDB_SOURCE_KEY},
        )

    if kind == CollectionKind.CUSTOM_FILTER.value:
        raw_ids = payload.source_collection_ids
        if raw_ids is None:
            raw_ids = [
                uuid.UUID(str(value)) for value in existing_filters.get("source_collection_ids", [])
            ]
        sources = _validate_local_sources(db, raw_ids, media_type=media_type)
        genre_ids = (
            _validate_genres(media_type, payload.genre_ids)
            if payload.genre_ids is not None
            else [
                int(value)
                for value in str(existing_filters.get("with_genres", "")).split(",")
                if value.strip().isdigit()
            ]
        )
        exclude_genre_ids = (
            _validate_genres(media_type, payload.exclude_genre_ids)
            if payload.exclude_genre_ids is not None
            else [
                int(value)
                for value in str(existing_filters.get("exclude_genres", "")).split(",")
                if value.strip().isdigit()
            ]
        )
        genre_ids, exclude_genre_ids = _validate_local_filters(
            media_type=media_type,
            genre_ids=genre_ids,
            exclude_genre_ids=exclude_genre_ids,
            original_language=payload.original_language
            if payload.original_language is not None
            else existing_filters.get("original_language"),
            local_sort_by=payload.local_sort_by
            or str(existing_filters.get("sort_by", "vote_average.desc")),
        )
        collection.provider_id = sources[0].provider_id
        collection.source_id = sources[0].source_id
        collection.kind = kind
        collection.origin = CollectionOrigin.CUSTOM.value
        collection.date_basis = DateBasis.UNKNOWN.value
        collection.name = payload.name or collection.name
        collection.description = (
            payload.description if payload.description is not None else collection.description
        )
        collection.offer_types = [
            payload.monetization_type
            or str((collection.offer_types or [OfferType.FLATRATE.value])[0])
        ]
        collection.filters = _build_filters(
            provider_external_id="",
            media_type=media_type,
            genre_ids=genre_ids,
            monetization_type=str(collection.offer_types[0]),
            kind=kind,
            source_collection_id=None,
            window_days=None,
            shared_snapshot_collection_id=None,
            source_collections=sources,
            exclude_genre_ids=exclude_genre_ids,
            min_vote_average=payload.min_vote_average
            if payload.min_vote_average is not None
            else existing_filters.get("min_vote_average"),
            min_vote_count=payload.min_vote_count
            if payload.min_vote_count is not None
            else existing_filters.get("min_vote_count"),
            year_from=payload.year_from
            if payload.year_from is not None
            else existing_filters.get("year_from"),
            year_to=payload.year_to
            if payload.year_to is not None
            else existing_filters.get("year_to"),
            original_language=payload.original_language
            if payload.original_language is not None
            else existing_filters.get("original_language"),
            local_sort_by=payload.local_sort_by
            or str(existing_filters.get("sort_by", "vote_average.desc")),
        )
        collection.quality_flags = _custom_quality_flags(sources)
        collection.sort_mode = "CUSTOM"
        if payload.is_active is not None:
            collection.is_active = payload.is_active
        db.flush()
        audit.record(
            db,
            action="collection_updated",
            entity_type="collection",
            entity_id=collection.id,
            actor_user_id=actor_user_id,
            actor_type=AuditActorType.USER if actor_user_id else AuditActorType.SYSTEM,
            after={
                "slug": collection.slug,
                "kind": collection.kind,
                "filters": collection.filters,
                "is_active": collection.is_active,
            },
        )
        db.commit()
        return collections_service.get_collection(db, collection.id)

    genre_ids = (
        _validate_genres(media_type, payload.genre_ids)
        if payload.genre_ids is not None
        else [
            int(value)
            for value in str(existing_filters.get("with_genres", "")).split(",")
            if value.strip().isdigit()
        ]
    )
    monetization_type = payload.monetization_type or str(
        (collection.offer_types or [OfferType.FLATRATE.value])[0]
    )
    source_collection_id = payload.source_collection_id
    if source_collection_id is None and existing_filters.get("source_collection_id"):
        source_collection_id = uuid.UUID(str(existing_filters["source_collection_id"]))
    window_days = payload.window_days
    if window_days is None and existing_filters.get("window_days") is not None:
        window_days = int(existing_filters["window_days"])
    shared_snapshot_collection_id = payload.shared_snapshot_collection_id
    if shared_snapshot_collection_id is None and existing_filters.get(
        "shared_snapshot_collection_id"
    ):
        shared_snapshot_collection_id = uuid.UUID(
            str(existing_filters["shared_snapshot_collection_id"])
        )
    if kind == CollectionKind.RECENTLY_ADDED.value:
        if monetization_type != OfferType.FLATRATE.value:
            raise ValidationError(
                "Le collezioni 'Appena rilevati' usano solo FLATRATE.",
                code="DERIVATION_REQUIRES_FLATRATE",
            )
        if source_collection_id is None:
            raise ValidationError(
                "source_collection_id è obbligatorio per 'Appena rilevati'.",
                code="DERIVATION_SOURCE_MISSING",
            )
        _validate_source_collection(
            db,
            source_collection_id,
            provider_id=collection.provider_id,
            media_type=media_type,
        )
    if shared_snapshot_collection_id is not None:
        _validate_source_collection(
            db,
            shared_snapshot_collection_id,
            provider_id=collection.provider_id,
            media_type=media_type,
        )
    provider_external_id = _provider_external_id(db, collection.provider_id, media_type)
    collection.name = payload.name or collection.name
    collection.description = (
        payload.description if payload.description is not None else collection.description
    )
    collection.kind = kind
    collection.origin = (
        CollectionOrigin.CUSTOM.value
        if kind == CollectionKind.RECENTLY_ADDED.value
        else CollectionOrigin.AGGREGATOR.value
    )
    collection.date_basis = (
        DateBasis.APP_FIRST_SEEN.value
        if kind == CollectionKind.RECENTLY_ADDED.value
        else DateBasis.UNKNOWN.value
    )
    collection.offer_types = [monetization_type]
    collection.filters = _build_filters(
        provider_external_id=provider_external_id,
        media_type=media_type,
        genre_ids=genre_ids,
        monetization_type=monetization_type,
        kind=kind,
        source_collection_id=source_collection_id,
        window_days=window_days,
        shared_snapshot_collection_id=shared_snapshot_collection_id,
    )
    collection.quality_flags = {
        "provider_mapping_verified": True,
        "added_date_missing": monetization_type == OfferType.FLATRATE.value,
        "derivation": collection.filters.get("derivation"),
    }
    collection.sort_mode = "POPULARITY"
    if payload.is_active is not None:
        collection.is_active = payload.is_active
    db.flush()
    audit.record(
        db,
        action="collection_updated",
        entity_type="collection",
        entity_id=collection.id,
        actor_user_id=actor_user_id,
        actor_type=AuditActorType.USER if actor_user_id else AuditActorType.SYSTEM,
        after={
            "slug": collection.slug,
            "kind": collection.kind,
            "filters": collection.filters,
            "is_active": collection.is_active,
        },
    )
    db.commit()
    return collections_service.get_collection(db, collection.id)


def _create_combined_collection(
    db: Session,
    payload: CollectionCreateIn,
    *,
    actor_user_id: uuid.UUID | None = None,
) -> CollectionSummary:
    """Create a local JustWatch + TMDb combination: no external call."""
    if payload.kind != CollectionKind.CUSTOM_FILTER.value:
        raise ValidationError(
            "Una collezione combinata deve essere di tipo CUSTOM_FILTER.",
            code="COMBINED_LOCAL_KIND",
            details={"kind": payload.kind},
        )
    source = sources_repo.get_source_by_key(db, COMBINED_SOURCE_KEY)
    if source is None:
        raise ValidationError("Fonte 'combined' non trovata.", code="SOURCE_MISSING")
    sources = _validate_combined_sources(
        db, payload.source_collection_ids, media_type=payload.media_type
    )
    provider_id = payload.provider_id or sources[0].provider_id
    provider = providers_repo.get_provider(db, provider_id)
    if provider is None:
        raise NotFoundError("Provider non trovato.", details={"provider_id": str(provider_id)})
    if provider.id not in {item.provider_id for item in sources}:
        raise ValidationError(
            "Il provider principale deve essere uno dei provider delle collezioni sorgente.",
            code="COMBINED_LOCAL_PROVIDER_MISMATCH",
        )
    genre_ids, exclude_genre_ids = _validate_local_filters(
        media_type=payload.media_type,
        genre_ids=payload.genre_ids,
        exclude_genre_ids=payload.exclude_genre_ids,
        original_language=payload.original_language,
        local_sort_by=payload.local_sort_by,
    )
    filters = _build_filters(
        provider_external_id="",
        media_type=payload.media_type,
        genre_ids=genre_ids,
        monetization_type=payload.monetization_type,
        kind=payload.kind,
        source_collection_id=None,
        window_days=None,
        shared_snapshot_collection_id=None,
        source_collections=sources,
        exclude_genre_ids=exclude_genre_ids,
        min_vote_average=payload.min_vote_average,
        min_vote_count=payload.min_vote_count,
        year_from=payload.year_from,
        year_to=payload.year_to,
        original_language=payload.original_language,
        local_sort_by=payload.local_sort_by,
        derivation=COMBINED_DERIVATION,
        combine_mode=payload.combine_mode,
    )
    quality_flags = _custom_quality_flags(sources)
    quality_flags["combine_mode"] = payload.combine_mode
    collection = collections_repo.upsert_collection(
        db,
        slug=payload.slug,
        source_id=source.id,
        provider_id=provider.id,
        country_code="IT",
        media_type=payload.media_type,
        kind=payload.kind,
        origin=CollectionOrigin.CUSTOM.value,
        date_basis=DateBasis.UNKNOWN.value,
        name=payload.name,
        description=payload.description
        or (
            "Combinata locale JustWatch + TMDb costruita da "
            f"{len(sources)} collezioni. Non è una lista ufficiale dei provider."
        ),
        source_collection_key=f"custom:{payload.slug}",
        source_url=None,
        offer_types=[payload.monetization_type],
        filters=filters,
        quality_flags=quality_flags,
        sort_mode="CUSTOM",
        is_active=payload.is_active,
    )
    audit.record(
        db,
        action="collection_created",
        entity_type="collection",
        entity_id=collection.id,
        actor_user_id=actor_user_id,
        actor_type=AuditActorType.USER if actor_user_id else AuditActorType.SYSTEM,
        after={
            "slug": collection.slug,
            "kind": collection.kind,
            "source_key": COMBINED_SOURCE_KEY,
            "source_collections": [str(item.id) for item in sources],
            "combine_mode": payload.combine_mode,
        },
    )
    db.commit()
    return collections_service.get_collection(db, collection.id)


def _update_combined_collection(
    db: Session,
    collection: Collection,
    payload: CollectionUpdateIn,
    *,
    actor_user_id: uuid.UUID | None = None,
) -> CollectionSummary:
    """Update a combined collection keeping its local derivation."""
    if payload.source_key is not None and payload.source_key != COMBINED_SOURCE_KEY:
        raise ValidationError(
            "La fonte di una collezione esistente non può essere cambiata.",
            code="SOURCE_KEY_IMMUTABLE",
            details={"source_key": COMBINED_SOURCE_KEY},
        )
    if payload.kind is not None and payload.kind != CollectionKind.CUSTOM_FILTER.value:
        raise ValidationError(
            "Una collezione combinata deve essere di tipo CUSTOM_FILTER.",
            code="COMBINED_LOCAL_KIND",
            details={"kind": payload.kind},
        )
    existing_filters = collection.filters or {}
    raw_ids = payload.source_collection_ids
    if raw_ids is None:
        raw_ids = [
            uuid.UUID(str(value)) for value in existing_filters.get("source_collection_ids", [])
        ]
    sources = _validate_combined_sources(db, raw_ids, media_type=collection.media_type)
    genre_ids = (
        _validate_genres(collection.media_type, payload.genre_ids)
        if payload.genre_ids is not None
        else [
            int(value)
            for value in str(existing_filters.get("with_genres", "")).split(",")
            if value.strip().isdigit()
        ]
    )
    exclude_genre_ids = (
        _validate_genres(collection.media_type, payload.exclude_genre_ids)
        if payload.exclude_genre_ids is not None
        else [
            int(value)
            for value in str(existing_filters.get("exclude_genres", "")).split(",")
            if value.strip().isdigit()
        ]
    )
    genre_ids, exclude_genre_ids = _validate_local_filters(
        media_type=collection.media_type,
        genre_ids=genre_ids,
        exclude_genre_ids=exclude_genre_ids,
        original_language=payload.original_language
        if payload.original_language is not None
        else existing_filters.get("original_language"),
        local_sort_by=payload.local_sort_by
        or str(existing_filters.get("sort_by", "vote_average.desc")),
    )
    combine_mode = payload.combine_mode or str(existing_filters.get("combine_mode") or "UNION")
    collection.provider_id = sources[0].provider_id
    collection.kind = CollectionKind.CUSTOM_FILTER.value
    collection.origin = CollectionOrigin.CUSTOM.value
    collection.date_basis = DateBasis.UNKNOWN.value
    collection.name = payload.name or collection.name
    collection.description = (
        payload.description if payload.description is not None else collection.description
    )
    collection.offer_types = [
        payload.monetization_type or str((collection.offer_types or [OfferType.FLATRATE.value])[0])
    ]
    collection.filters = _build_filters(
        provider_external_id="",
        media_type=collection.media_type,
        genre_ids=genre_ids,
        monetization_type=str(collection.offer_types[0]),
        kind=collection.kind,
        source_collection_id=None,
        window_days=None,
        shared_snapshot_collection_id=None,
        source_collections=sources,
        exclude_genre_ids=exclude_genre_ids,
        min_vote_average=payload.min_vote_average
        if payload.min_vote_average is not None
        else existing_filters.get("min_vote_average"),
        min_vote_count=payload.min_vote_count
        if payload.min_vote_count is not None
        else existing_filters.get("min_vote_count"),
        year_from=payload.year_from
        if payload.year_from is not None
        else existing_filters.get("year_from"),
        year_to=payload.year_to if payload.year_to is not None else existing_filters.get("year_to"),
        original_language=payload.original_language
        if payload.original_language is not None
        else existing_filters.get("original_language"),
        local_sort_by=payload.local_sort_by
        or str(existing_filters.get("sort_by", "vote_average.desc")),
        derivation=COMBINED_DERIVATION,
        combine_mode=combine_mode,
    )
    quality_flags = _custom_quality_flags(sources)
    quality_flags["combine_mode"] = combine_mode
    collection.quality_flags = quality_flags
    collection.sort_mode = "CUSTOM"
    if payload.is_active is not None:
        collection.is_active = payload.is_active
    db.flush()
    audit.record(
        db,
        action="collection_updated",
        entity_type="collection",
        entity_id=collection.id,
        actor_user_id=actor_user_id,
        actor_type=AuditActorType.USER if actor_user_id else AuditActorType.SYSTEM,
        after={
            "slug": collection.slug,
            "kind": collection.kind,
            "source_key": COMBINED_SOURCE_KEY,
            "filters": collection.filters,
            "is_active": collection.is_active,
        },
    )
    db.commit()
    return collections_service.get_collection(db, collection.id)


def _create_justwatch_collection(
    db: Session,
    payload: CollectionCreateIn,
    *,
    actor_user_id: uuid.UUID | None = None,
) -> CollectionSummary:
    """Create a JustWatch collection: aggregator, no add dates, verified mapping."""
    if payload.kind not in _JUSTWATCH_KINDS:
        raise ValidationError(
            "JustWatch supporta CATALOG, RECENTLY_ADDED, UPCOMING e CHART.",
            code="KIND_NOT_SUPPORTED",
            details={"kind": payload.kind, "source_key": JUSTWATCH_SOURCE_KEY},
        )
    if payload.genre_ids or payload.exclude_genre_ids:
        raise ValidationError(
            "JustWatch usa generi propri (slug), non gli id TMDb: filtro generi non applicato.",
            code="JUSTWATCH_GENRES_UNSUPPORTED",
        )
    if payload.provider_id is None:
        raise ValidationError(
            "provider_id è obbligatorio per una collezione JustWatch.",
            code="PROVIDER_REQUIRED",
        )
    provider = providers_repo.get_provider(db, payload.provider_id)
    if provider is None:
        raise NotFoundError(
            "Provider non trovato.", details={"provider_id": str(payload.provider_id)}
        )
    source = sources_repo.get_source_by_key(db, JUSTWATCH_SOURCE_KEY)
    if source is None:
        raise ValidationError("Fonte JustWatch non trovata.", code="SOURCE_MISSING")
    mapping = _justwatch_mapping(db, provider.id)
    offer_types = _justwatch_offer_types(payload.offer_types, mapping)
    collection = collections_repo.upsert_collection(
        db,
        slug=payload.slug,
        source_id=source.id,
        provider_id=provider.id,
        country_code="IT",
        media_type=payload.media_type,
        kind=payload.kind,
        origin=CollectionOrigin.AGGREGATOR.value,
        date_basis=DateBasis.UNKNOWN.value,
        name=payload.name,
        description=payload.description or _JUSTWATCH_DESCRIPTION[payload.kind],
        source_collection_key=f"custom:{payload.slug}",
        source_url=None,
        offer_types=offer_types,
        filters=_justwatch_filters(
            external_provider_id=mapping.external_provider_id,
            media_type=payload.media_type,
            offer_types=offer_types,
            year_from=payload.year_from,
            year_to=payload.year_to,
        ),
        quality_flags=_justwatch_quality_flags(payload.kind),
        sort_mode="SOURCE_ORDER",
        is_active=payload.is_active,
    )
    audit.record(
        db,
        action="collection_created",
        entity_type="collection",
        entity_id=collection.id,
        actor_user_id=actor_user_id,
        actor_type=AuditActorType.USER if actor_user_id else AuditActorType.SYSTEM,
        after={
            "slug": collection.slug,
            "kind": collection.kind,
            "source_key": JUSTWATCH_SOURCE_KEY,
            "packages": [mapping.external_provider_id],
            "offer_types": offer_types,
        },
    )
    db.commit()
    return collections_service.get_collection(db, collection.id)


def _update_justwatch_collection(
    db: Session,
    collection: Collection,
    payload: CollectionUpdateIn,
    *,
    actor_user_id: uuid.UUID | None = None,
) -> CollectionSummary:
    """Update a JustWatch collection keeping aggregator origin and UNKNOWN dates."""
    if payload.source_key is not None and payload.source_key != JUSTWATCH_SOURCE_KEY:
        raise ValidationError(
            "La fonte di una collezione esistente non può essere cambiata.",
            code="SOURCE_KEY_IMMUTABLE",
            details={"source_key": JUSTWATCH_SOURCE_KEY},
        )
    if payload.genre_ids or payload.exclude_genre_ids:
        raise ValidationError(
            "JustWatch usa generi propri (slug), non gli id TMDb: filtro generi non applicato.",
            code="JUSTWATCH_GENRES_UNSUPPORTED",
        )
    mapping = _justwatch_mapping(db, collection.provider_id)
    kind = payload.kind or collection.kind
    if kind not in _JUSTWATCH_KINDS:
        raise ValidationError(
            "JustWatch supporta CATALOG, RECENTLY_ADDED, UPCOMING e CHART.",
            code="KIND_NOT_SUPPORTED",
            details={"kind": kind, "source_key": JUSTWATCH_SOURCE_KEY},
        )
    existing_filters = collection.filters or {}
    requested_offers: Sequence[str] = payload.offer_types or [
        str(value) for value in (collection.offer_types or [OfferType.FLATRATE.value])
    ]
    offer_types = _justwatch_offer_types(requested_offers, mapping)
    year_from = (
        payload.year_from if payload.year_from is not None else existing_filters.get("year_from")
    )
    year_to = payload.year_to if payload.year_to is not None else existing_filters.get("year_to")
    collection.name = payload.name or collection.name
    collection.description = (
        payload.description if payload.description is not None else collection.description
    )
    collection.kind = kind
    collection.origin = CollectionOrigin.AGGREGATOR.value
    collection.date_basis = DateBasis.UNKNOWN.value
    collection.offer_types = offer_types
    collection.filters = _justwatch_filters(
        external_provider_id=mapping.external_provider_id,
        media_type=collection.media_type,
        offer_types=offer_types,
        year_from=year_from,
        year_to=year_to,
    )
    collection.quality_flags = _justwatch_quality_flags(kind)
    collection.sort_mode = "SOURCE_ORDER"
    if payload.is_active is not None:
        collection.is_active = payload.is_active
    db.flush()
    audit.record(
        db,
        action="collection_updated",
        entity_type="collection",
        entity_id=collection.id,
        actor_user_id=actor_user_id,
        actor_type=AuditActorType.USER if actor_user_id else AuditActorType.SYSTEM,
        after={
            "slug": collection.slug,
            "kind": collection.kind,
            "source_key": JUSTWATCH_SOURCE_KEY,
            "filters": collection.filters,
            "is_active": collection.is_active,
        },
    )
    db.commit()
    return collections_service.get_collection(db, collection.id)


@dataclass(frozen=True)
class CollectionAcquisition:
    job_id: uuid.UUID
    collection_id: uuid.UUID
    status: str
    snapshot_id: uuid.UUID | None


def enqueue_collection_acquisition(
    db: Session,
    settings: Settings,
    collection_id: uuid.UUID,
    *,
    actor_user_id: uuid.UUID | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
) -> CollectionAcquisition:
    """Validate the source/connector and enqueue one acquisition job."""
    collection = collections_repo.get_collection(db, collection_id)
    if collection is None:
        raise NotFoundError(
            "Collezione non trovata.", details={"collection_id": str(collection_id)}
        )
    source = sources_repo.get_source(db, collection.source_id)
    if source is None:
        raise SourceUnavailableError(
            "Fonte della collezione non trovata.",
            details={"collection_id": str(collection_id)},
        )
    if source.key != COMBINED_SOURCE_KEY:
        if not registry.is_registered(source.key):
            raise SourceUnavailableError(
                f"Connettore non disponibile per la fonte '{source.key}'.",
                details={"source_key": source.key},
            )
        registry.ensure_source_credentials(db, settings, source.key)
    job = tasks.enqueue_acquire_collection(db, settings, collection.id, actor_user_id=actor_user_id)
    audit.record(
        db,
        action="collection_acquisition_enqueued",
        entity_type="collection",
        entity_id=collection.id,
        actor_user_id=actor_user_id,
        actor_type=AuditActorType.USER if actor_user_id else AuditActorType.SYSTEM,
        after={"job_id": str(job.id), "source_key": source.key},
        ip=ip,
        user_agent=user_agent,
        request_id=request_id,
    )
    db.commit()
    snapshot_id = job.result.get("snapshot_id") if job.result else None
    return CollectionAcquisition(
        job_id=job.id,
        collection_id=collection.id,
        status=job.status,
        snapshot_id=snapshot_id,
    )
