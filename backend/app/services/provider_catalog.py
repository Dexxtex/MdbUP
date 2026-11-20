"""Read-only provider discovery for the manual provider picker.

TMDb and the public JustWatch endpoint are availability sources. TheTVDB is a
metadata catalogue: its streaming companies are offered as an additional
identifier source, never as proof of Italian availability.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
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


@dataclass
class _CandidateBuilder:
    name: str
    sources: set[str] = field(default_factory=set)
    tmdb_movie_id: str | None = None
    tmdb_tv_id: str | None = None
    justwatch_short_name: str | None = None
    justwatch_technical_name: str | None = None
    justwatch_monetization_types: tuple[str, ...] = ()
    tvdb_company_id: str | None = None
    logo_url: str | None = None
    available: bool | None = None


def _normalized_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    text = text.casefold().replace("&", " and ").replace("+", " plus ")
    words = re.sub(r"[^a-z0-9]+", " ", text).split()
    # "Now TV" and "NOW" are the same service in the Italian catalog.
    if len(words) > 1 and words[-1] == "tv":
        words.pop()
    return " ".join(words)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return slug[:80] or "provider"


def _candidate_key(builder: _CandidateBuilder) -> str:
    if builder.tmdb_movie_id or builder.tmdb_tv_id:
        return f"tmdb:{builder.tmdb_movie_id or builder.tmdb_tv_id}"
    if builder.justwatch_short_name:
        return f"justwatch:{builder.justwatch_short_name}"
    return f"tvdb:{builder.tvdb_company_id or _slugify(builder.name)}"


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


def discover_providers(
    db: Session, settings: Settings, *, country: str = SUPPORTED_COUNTRY
) -> ProviderCatalog:
    """Merge TMDb/JustWatch/TVDB candidates by normalized display name."""
    source_rows: list[tuple[str, dict[str, Any]]] = []
    statuses: list[SourceDiscovery] = []
    for rows, status in (
        _tmdb_candidates(db, settings, country),
        _justwatch_candidates(settings, country),
        _tvdb_candidates(db, settings),
    ):
        source_rows.extend(rows)
        statuses.append(status)

    by_name: dict[str, _CandidateBuilder] = {}
    for name, row in source_rows:
        key = _normalized_name(name)
        if not key:
            continue
        builder = by_name.get(key)
        if builder is None:
            builder = _CandidateBuilder(name=name)
            by_name[key] = builder
        source = str(row.get("source") or "")
        builder.sources.add(source)
        if source == "tmdb":
            movie_id = row.get("tmdb_movie_id")
            tv_id = row.get("tmdb_tv_id")
            if isinstance(movie_id, str):
                builder.tmdb_movie_id = movie_id
            if isinstance(tv_id, str):
                builder.tmdb_tv_id = tv_id
            logo = row.get("logo_url")
            if isinstance(logo, str) and not builder.logo_url:
                builder.logo_url = logo
            builder.available = True
        elif source == "justwatch":
            short_name = row.get("justwatch_short_name")
            technical_name = row.get("justwatch_technical_name")
            monetization = row.get("justwatch_monetization_types")
            if isinstance(short_name, str):
                builder.justwatch_short_name = short_name
            if isinstance(technical_name, str):
                builder.justwatch_technical_name = technical_name
            if isinstance(monetization, tuple):
                builder.justwatch_monetization_types = monetization
            builder.available = True
        elif source == "tvdb":
            company_id = row.get("tvdb_company_id")
            if isinstance(company_id, str):
                builder.tvdb_company_id = company_id

    used_slugs: set[str] = set()
    items: list[ProviderCandidate] = []
    for builder in sorted(by_name.values(), key=lambda item: item.name.casefold()):
        base = _slugify(builder.name)
        slug = base
        suffix = 2
        while slug in used_slugs:
            slug = f"{base}-{suffix}"
            suffix += 1
        used_slugs.add(slug)
        items.append(
            ProviderCandidate(
                key=_candidate_key(builder),
                name=builder.name,
                suggested_slug=slug,
                sources=tuple(source for source in _SOURCE_ORDER if source in builder.sources),
                tmdb_movie_id=builder.tmdb_movie_id,
                tmdb_tv_id=builder.tmdb_tv_id,
                justwatch_short_name=builder.justwatch_short_name,
                justwatch_technical_name=builder.justwatch_technical_name,
                justwatch_monetization_types=builder.justwatch_monetization_types,
                tvdb_company_id=builder.tvdb_company_id,
                logo_url=builder.logo_url,
                country_code=country if builder.available else None,
                available_in_country=builder.available,
            )
        )
    return ProviderCatalog(items=tuple(items), sources=tuple(statuses))
