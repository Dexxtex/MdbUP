"""Canonical providers and their per-source mappings."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Provider, ProviderMapping


def list_providers(db: Session) -> list[Provider]:
    return list(db.scalars(select(Provider).order_by(Provider.name)).all())


def get_provider(db: Session, provider_id: uuid.UUID) -> Provider | None:
    return db.get(Provider, provider_id)


def get_provider_by_slug(db: Session, slug: str) -> Provider | None:
    return db.scalar(select(Provider).where(Provider.slug == slug))


def upsert_provider(
    db: Session,
    *,
    slug: str,
    name: str,
    kind: str = "SVOD",
    logo_url: str | None = None,
    website_url: str | None = None,
) -> Provider:
    """Insert or update a canonical provider by slug."""
    provider = get_provider_by_slug(db, slug)
    if provider is None:
        provider = Provider(slug=slug, name=name, kind=kind)
        db.add(provider)
    provider.name = name
    provider.kind = kind
    provider.logo_url = logo_url
    provider.website_url = website_url
    db.flush()
    return provider


def list_mappings(
    db: Session,
    *,
    source_id: uuid.UUID | None = None,
    country_code: str | None = None,
) -> list[ProviderMapping]:
    stmt = select(ProviderMapping)
    if source_id is not None:
        stmt = stmt.where(ProviderMapping.source_id == source_id)
    if country_code is not None:
        stmt = stmt.where(ProviderMapping.country_code == country_code)
    stmt = stmt.order_by(ProviderMapping.provider_id, ProviderMapping.is_primary.desc())
    return list(db.scalars(stmt).all())


def get_mapping(
    db: Session,
    *,
    provider_id: uuid.UUID,
    source_id: uuid.UUID,
    country_code: str,
) -> ProviderMapping | None:
    """Return the primary mapping for a provider/source/country, if any."""
    stmt = (
        select(ProviderMapping)
        .where(
            ProviderMapping.provider_id == provider_id,
            ProviderMapping.source_id == source_id,
            ProviderMapping.country_code == country_code,
        )
        .order_by(ProviderMapping.is_primary.desc(), ProviderMapping.created_at)
    )
    return db.scalars(stmt).first()


def get_mapping_by_external_id(
    db: Session,
    *,
    source_id: uuid.UUID,
    country_code: str,
    external_provider_id: str,
) -> ProviderMapping | None:
    return db.scalar(
        select(ProviderMapping).where(
            ProviderMapping.source_id == source_id,
            ProviderMapping.country_code == country_code,
            ProviderMapping.external_provider_id == external_provider_id,
        )
    )


def upsert_mapping(
    db: Session,
    *,
    provider_id: uuid.UUID,
    source_id: uuid.UUID,
    country_code: str,
    external_provider_id: str,
    external_name: str | None = None,
    is_primary: bool = True,
    is_verified: bool = False,
    metadata: dict[str, Any] | None = None,
) -> ProviderMapping:
    """Insert or update the mapping for one external provider id."""
    mapping = db.scalar(
        select(ProviderMapping).where(
            ProviderMapping.source_id == source_id,
            ProviderMapping.country_code == country_code,
            ProviderMapping.external_provider_id == external_provider_id,
        )
    )
    if mapping is None:
        mapping = ProviderMapping(
            provider_id=provider_id,
            source_id=source_id,
            country_code=country_code,
            external_provider_id=external_provider_id,
        )
        db.add(mapping)
    mapping.external_name = external_name
    mapping.is_primary = is_primary
    mapping.is_verified = is_verified
    mapping.metadata_json = metadata or {}
    db.flush()
    return mapping
