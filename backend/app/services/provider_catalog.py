"""Read-only provider discovery for the manual provider picker.

TMDb and the public JustWatch endpoint are availability sources. TheTVDB is a
metadata catalogue: its streaming companies are offered as an additional
identifier source, never as proof of Italian availability.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.logging import get_logger
from app.integrations.justwatch.client import JustWatchClient, JustWatchError
from app.integrations.tmdb.client import TMDbClient, TMDbError
from app.integrations.tvdb.client import TVDbClient, TVDbError
from app.services import credentials as credentials_service
from app.services.credentials import CredentialKind

logger = get_logger(__name__)

SUPPORTED_COUNTRY = "IT"
_SOURCE_ORDER = ("tmdb", "justwatch", "tvdb")


@dataclass(frozen=True)
class SourceDiscovery:
    source_key: str
    status: str
    message: str
    count: int = 0

    def as_dict(self) -> dict[str, object]:
        return {
            "source_key": self.source_key,
            "status": self.status,
            "message": self.message,
            "count": self.count,
        }


@dataclass(frozen=True)
class ProviderCandidate:
    key: str
    name: str
    suggested_slug: str
    sources: tuple[str, ...]
    source_key: str
    tmdb_movie_id: str | None = None
    tmdb_tv_id: str | None = None
    justwatch_short_name: str | None = None
    justwatch_technical_name: str | None = None
    justwatch_monetization_types: tuple[str, ...] = ()
    tvdb_company_id: str | None = None
    logo_url: str | None = None
    country_code: str | None = None
    available_in_country: bool | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "name": self.name,
            "suggested_slug": self.suggested_slug,
            "sources": list(self.sources),
            "source_key": self.source_key,
            "tmdb_movie_id": self.tmdb_movie_id,
            "tmdb_tv_id": self.tmdb_tv_id,
            "justwatch_short_name": self.justwatch_short_name,
            "justwatch_technical_name": self.justwatch_technical_name,
            "justwatch_monetization_types": list(self.justwatch_monetization_types),
            "tvdb_company_id": self.tvdb_company_id,
            "logo_url": self.logo_url,
            "country_code": self.country_code,
            "available_in_country": self.available_in_country,
        }


@dataclass(frozen=True)
class ProviderCatalog:
    items: tuple[ProviderCandidate, ...]
    sources: tuple[SourceDiscovery, ...]


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return slug[:80] or "provider"


def _tmdb_candidates(
    db: Session, settings: Settings, country: str
) -> tuple[list[tuple[str, dict[str, Any]]], SourceDiscovery]:
    try:
        token = credentials_service.get_secret(db, settings, CredentialKind.TMDB)
    except Exception as exc:  # Credentials are optional for discovery.
        logger.info("provider_catalog_tmdb_credential_missing", error=type(exc).__name__)
        return [], SourceDiscovery(
            "tmdb", "MISSING_CREDENTIAL", "Configura la TMDb API key nelle Impostazioni."
        )
    client = TMDbClient(
        token,
        timeout=float(settings.http_timeout_seconds),
        max_retries=settings.http_max_retries,
        backoff_base_seconds=settings.http_backoff_base_ms / 1000,
        backoff_max_seconds=settings.http_backoff_max_ms / 1000,
        jitter_ratio=settings.http_jitter_ratio,
    )
    try:
        movie = {item.provider_id: item for item in client.list_movie_providers(country)}
        tv = {item.provider_id: item for item in client.list_tv_providers(country)}
    except TMDbError as exc:
        logger.warning("provider_catalog_tmdb_failed", error=type(exc).__name__)
        return [], SourceDiscovery("tmdb", "ERROR", "TMDb non ha risposto correttamente.")
    finally:
        client.close()
    rows: list[tuple[str, dict[str, Any]]] = []
    for provider_id in sorted(set(movie) | set(tv)):
        provider = movie.get(provider_id) or tv.get(provider_id)
        assert provider is not None
        logo = f"https://image.tmdb.org/t/p/w92{provider.logo_path}" if provider.logo_path else None
        rows.append(
            (
                provider.name,
                {
                    "source": "tmdb",
                    "tmdb_movie_id": str(movie[provider_id].provider_id)
                    if provider_id in movie
                    else None,
                    "tmdb_tv_id": str(tv[provider_id].provider_id) if provider_id in tv else None,
                    "logo_url": logo,
                    "country_code": country,
                    "available": True,
                },
            )
        )
    return rows, SourceDiscovery("tmdb", "OK", "Provider TMDb per il paese.", len(rows))


def _justwatch_candidates(
    settings: Settings, country: str
) -> tuple[list[tuple[str, dict[str, Any]]], SourceDiscovery]:
    client = JustWatchClient(
        settings.justwatch_base_url,
        timeout=float(settings.http_timeout_seconds),
        max_retries=settings.http_max_retries,
        backoff_base_seconds=settings.http_backoff_base_ms / 1000,
        backoff_max_seconds=settings.http_backoff_max_ms / 1000,
        jitter_ratio=settings.http_jitter_ratio,
        min_interval_seconds=settings.justwatch_min_interval_ms / 1000,
        cache_ttl_seconds=settings.justwatch_cache_ttl_seconds,
        cache_max_entries=settings.justwatch_cache_max_entries,
    )
    try:
        packages = client.list_packages(country)
    except JustWatchError as exc:
        logger.warning("provider_catalog_justwatch_failed", error=type(exc).__name__)
        return [], SourceDiscovery("justwatch", "ERROR", "JustWatch non ha risposto correttamente.")
    finally:
        client.close()
    rows = [
        (
            package.name,
            {
                "source": "justwatch",
                "justwatch_short_name": package.short_name,
                "justwatch_technical_name": package.technical_name,
                "justwatch_monetization_types": tuple(package.monetization_types),
                "country_code": country,
                "available": True,
            },
        )
        for package in packages
    ]
    return rows, SourceDiscovery("justwatch", "OK", "Package JustWatch per il paese.", len(rows))


def _tvdb_candidates(
    db: Session, settings: Settings
) -> tuple[list[tuple[str, dict[str, Any]]], SourceDiscovery]:
    try:
        token = credentials_service.get_secret(db, settings, CredentialKind.TVDB)
    except Exception as exc:  # Credentials are optional for discovery.
        logger.info("provider_catalog_tvdb_credential_missing", error=type(exc).__name__)
        return [], SourceDiscovery(
            "tvdb", "MISSING_CREDENTIAL", "Configura la TheTVDB API key nelle Impostazioni."
        )
    client = TVDbClient(
        token,
        timeout=float(settings.http_timeout_seconds),
        max_retries=settings.http_max_retries,
    )
    try:
        companies = client.list_streaming_companies()
    except TVDbError as exc:
        logger.warning("provider_catalog_tvdb_failed", error=type(exc).__name__)
        return [], SourceDiscovery("tvdb", "ERROR", "TheTVDB non ha risposto correttamente.")
    finally:
        client.close()
    rows = [
        (
            company.name,
            {
                "source": "tvdb",
                "tvdb_company_id": company.company_id,
                # TVDB does not expose country availability.
                "country_code": None,
                "available": None,
            },
        )
        for company in companies
    ]
    return rows, SourceDiscovery(
        "tvdb", "OK", "Company TVDB (metadati; disponibilità per paese non dichiarata).", len(rows)
    )


def _candidate_from_row(
    name: str,
    row: dict[str, Any],
    *,
    country: str,
    slug: str,
) -> ProviderCandidate:
    source = str(row.get("source") or "")
    if source == "tmdb":
        key = f"tmdb:{row.get('tmdb_movie_id') or row.get('tmdb_tv_id')}"
    elif source == "justwatch":
        key = f"justwatch:{row.get('justwatch_short_name') or _slugify(name)}"
    else:
        key = f"tvdb:{row.get('tvdb_company_id') or _slugify(name)}"
    return ProviderCandidate(
        key=key,
        name=name,
        suggested_slug=slug,
        sources=(source,),
        source_key=source,
        tmdb_movie_id=row.get("tmdb_movie_id"),
        tmdb_tv_id=row.get("tmdb_tv_id"),
        justwatch_short_name=row.get("justwatch_short_name"),
        justwatch_technical_name=row.get("justwatch_technical_name"),
        justwatch_monetization_types=tuple(row.get("justwatch_monetization_types") or ()),
        tvdb_company_id=row.get("tvdb_company_id"),
        logo_url=row.get("logo_url"),
        country_code=country if row.get("available") is True else None,
        available_in_country=row.get("available"),
    )


def discover_providers(
    db: Session, settings: Settings, *, country: str = SUPPORTED_COUNTRY
) -> ProviderCatalog:
    """Return candidates grouped by source, never merged across sources.

    A TMDb row and a JustWatch row for the same service are two distinct
    choices: the operator decides which mapping to configure. This keeps the
    provenance visible and prevents a discovered name from silently becoming a
    cross-source claim.
    """
    source_rows: list[tuple[str, dict[str, Any]]] = []
    statuses: list[SourceDiscovery] = []
    for rows, status in (
        _tmdb_candidates(db, settings, country),
        _justwatch_candidates(settings, country),
        _tvdb_candidates(db, settings),
    ):
        source_rows.extend(rows)
        statuses.append(status)

    used_slugs: set[str] = set()
    used_names: set[str] = set()
    items: list[ProviderCandidate] = []
    for name, row in sorted(
        source_rows,
        key=lambda item: (
            _SOURCE_ORDER.index(str(item[1].get("source") or "tvdb")),
            item[0].casefold(),
        ),
    ):
        base = _slugify(name)
        slug = base
        if base in used_names:
            source = str(row.get("source") or "provider")
            slug = f"{base}-{source}"
        suffix = 2
        while slug in used_slugs:
            slug = f"{base}-{suffix}"
            suffix += 1
        used_slugs.add(slug)
        used_names.add(base)
        items.append(_candidate_from_row(name, row, country=country, slug=slug))
    return ProviderCatalog(items=tuple(items), sources=tuple(statuses))
