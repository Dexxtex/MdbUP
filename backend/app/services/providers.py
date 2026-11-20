"""Provider read model: canonical provider plus its TMDb mapping."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.domain.commands import ProviderCreateIn
from app.domain.enums import AuditActorType
from app.domain.errors import ConflictError, NotFoundError, ValidationError
from app.repositories import audit
from app.repositories import collections as collections_repo
from app.repositories import providers as providers_repo
from app.repositories import sources as sources_repo


@dataclass(frozen=True)
class ProviderSummary:
    id: uuid.UUID
    slug: str
    name: str
    kind: str
    logo_url: str | None
    website_url: str | None
    country_code: str
    tmdb_provider_id: str | None
    tmdb_provider_id_movie: str | None
    tmdb_provider_id_tv: str | None
    mapping_verified: bool
    mapping_verified_movie: bool
    mapping_verified_tv: bool
    justwatch_provider_id: str | None
    justwatch_verified: bool
    justwatch_movie_verified: bool
    justwatch_tv_verified: bool
    justwatch_monetization_types: list[str]
    collections_count: int
    movie_collections: int
    show_collections: int


def list_providers(db: Session, *, country_code: str = "IT") -> list[ProviderSummary]:
    providers = providers_repo.list_providers(db)
    counts = collections_repo.count_by_provider(db, country_code=country_code)
    tmdb_source = sources_repo.get_source_by_key(db, "tmdb")
    mappings = (
        providers_repo.list_mappings(db, source_id=tmdb_source.id, country_code=country_code)
        if tmdb_source is not None
        else []
    )
    mapping_by_provider = {mapping.provider_id: mapping for mapping in mappings}
    justwatch_source = sources_repo.get_source_by_key(db, "justwatch")
    justwatch_mapping_by_provider = {
        mapping.provider_id: mapping
        for mapping in (
            providers_repo.list_mappings(
                db, source_id=justwatch_source.id, country_code=country_code
            )
            if justwatch_source is not None
            else []
        )
    }
    summaries: list[ProviderSummary] = []
    for provider in providers:
        mapping = mapping_by_provider.get(provider.id)
        metadata = (mapping.metadata_json or {}) if mapping is not None else {}
        justwatch_mapping = justwatch_mapping_by_provider.get(provider.id)
        justwatch_metadata = (
            (justwatch_mapping.metadata_json or {}) if justwatch_mapping is not None else {}
        )
        per_type = counts.get(provider.id, {})
        movie_count = per_type.get("MOVIE", 0)
        show_count = per_type.get("SHOW", 0)
        summaries.append(
            ProviderSummary(
                id=provider.id,
                slug=provider.slug,
                name=provider.name,
                kind=provider.kind,
                logo_url=provider.logo_url,
                website_url=provider.website_url,
                country_code=country_code,
                tmdb_provider_id=(mapping.external_provider_id if mapping is not None else None),
                tmdb_provider_id_movie=(
                    str(metadata["movie_provider_id"])
                    if metadata.get("movie_provider_id") is not None
                    else None
                ),
                tmdb_provider_id_tv=(
                    str(metadata["tv_provider_id"])
                    if metadata.get("tv_provider_id") is not None
                    else None
                ),
                mapping_verified=bool(mapping.is_verified) if mapping is not None else False,
                mapping_verified_movie=bool(metadata.get("movie_verified")),
                mapping_verified_tv=bool(metadata.get("tv_verified")),
                justwatch_provider_id=(
                    justwatch_mapping.external_provider_id
                    if justwatch_mapping is not None
                    else None
                ),
                justwatch_verified=(
                    bool(justwatch_mapping.is_verified) if justwatch_mapping is not None else False
                ),
                justwatch_movie_verified=bool(justwatch_metadata.get("movie_verified")),
                justwatch_tv_verified=bool(justwatch_metadata.get("tv_verified")),
                justwatch_monetization_types=[
                    str(value) for value in justwatch_metadata.get("monetization_types") or []
                ],
                collections_count=movie_count + show_count,
                movie_collections=movie_count,
                show_collections=show_count,
            )
        )
    return summaries


def get_provider(
    db: Session, provider_id: uuid.UUID, *, country_code: str = "IT"
) -> ProviderSummary:
    for summary in list_providers(db, country_code=country_code):
        if summary.id == provider_id:
            return summary
    raise NotFoundError("Provider non trovato.", details={"provider_id": str(provider_id)})


def create_provider(
    db: Session,
    payload: ProviderCreateIn,
    *,
    actor_user_id: uuid.UUID | None = None,
) -> ProviderSummary:
    """Create a provider chosen by the operator, with optional manual mappings."""
    if providers_repo.get_provider_by_slug(db, payload.slug) is not None:
        raise ConflictError(
            "Esiste già un provider con questo slug.",
            code="PROVIDER_ALREADY_EXISTS",
            details={"slug": payload.slug},
        )
    tmdb_source = sources_repo.get_source_by_key(db, "tmdb")
    justwatch_source = sources_repo.get_source_by_key(db, "justwatch")
    provider = providers_repo.upsert_provider(
        db,
        slug=payload.slug,
        name=payload.name,
        kind=payload.kind,
        logo_url=payload.logo_url,
        website_url=payload.website_url,
    )
    if payload.tmdb_movie_id or payload.tmdb_tv_id:
        if tmdb_source is None:
            raise ValidationError("Fonte TMDb non trovata.", code="SOURCE_MISSING")
        for external_id in (payload.tmdb_movie_id, payload.tmdb_tv_id):
            if not external_id:
                continue
            existing = providers_repo.get_mapping_by_external_id(
                db,
                source_id=tmdb_source.id,
                country_code="IT",
                external_provider_id=external_id,
            )
            if existing is not None and existing.provider_id != provider.id:
                raise ConflictError(
                    "ID TMDb già associato a un altro provider.",
                    code="MAPPING_ALREADY_EXISTS",
                    details={"external_id": external_id},
                )
        providers_repo.upsert_mapping(
            db,
            provider_id=provider.id,
            source_id=tmdb_source.id,
            country_code="IT",
            external_provider_id=payload.tmdb_movie_id or payload.tmdb_tv_id or "",
            external_name=provider.name,
            is_primary=True,
            is_verified=bool(payload.tmdb_movie_id or payload.tmdb_tv_id),
            metadata={
                "movie_provider_id": payload.tmdb_movie_id,
                "tv_provider_id": payload.tmdb_tv_id,
                "movie_verified": bool(payload.tmdb_movie_id),
                "tv_verified": bool(payload.tmdb_tv_id),
                "verification_source": "manual",
            },
        )
    if payload.justwatch_short_name:
        if justwatch_source is None:
            raise ValidationError("Fonte JustWatch non trovata.", code="SOURCE_MISSING")
        existing = providers_repo.get_mapping_by_external_id(
            db,
            source_id=justwatch_source.id,
            country_code="IT",
            external_provider_id=payload.justwatch_short_name,
        )
        if existing is not None and existing.provider_id != provider.id:
            raise ConflictError(
                "Package JustWatch già associato a un altro provider.",
                code="MAPPING_ALREADY_EXISTS",
                details={"short_name": payload.justwatch_short_name},
            )
        providers_repo.upsert_mapping(
            db,
            provider_id=provider.id,
            source_id=justwatch_source.id,
            country_code="IT",
            external_provider_id=payload.justwatch_short_name,
            external_name=provider.name,
            is_primary=True,
            is_verified=True,
            metadata={
                "technical_name": payload.justwatch_technical_name,
                "clear_name": provider.name,
                "monetization_types": [
                    value.upper() for value in payload.justwatch_monetization_types
                ],
                "movie_external_id": payload.justwatch_short_name,
                "tv_external_id": payload.justwatch_short_name,
                "movie_verified": True,
                "tv_verified": True,
                "verification_source": "manual",
            },
        )
    audit.record(
        db,
        action="provider_created",
        entity_type="provider",
        entity_id=provider.id,
        actor_user_id=actor_user_id,
        actor_type=AuditActorType.USER if actor_user_id else AuditActorType.SYSTEM,
        after={"slug": provider.slug, "name": provider.name},
    )
    db.commit()
    return get_provider(db, provider.id)
