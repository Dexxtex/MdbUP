"""Live verification of TMDb watch-provider ids for the Italian market.

TMDb exposes separate ``/watch/providers/movie`` and ``/watch/providers/tv``
lists. A canonical provider may have different ids or coverage per media type,
so both ids are stored in ``provider_mapping.metadata`` and the acquisition
layer picks the right one for the collection's media type.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.time import utcnow
from app.db.models import Collection, Provider, ProviderMapping, Source
from app.domain.enums import AuditActorType, MediaType
from app.integrations.tmdb.client import TMDbClient
from app.repositories import audit
from app.services import credentials as credentials_service
from app.services.credentials import CredentialKind

# Canonical slug -> names accepted from TMDb. Exact, case-insensitive match:
# variants such as "Amazon Prime Video with Ads" or "Apple TV Store" must not
# be selected as the main provider.
PROVIDER_ALIASES: dict[str, tuple[str, ...]] = {
    "netflix": ("Netflix",),
    "prime-video": ("Amazon Prime Video",),
    "disney-plus": ("Disney Plus",),
    "now": ("Now", "Now TV"),
    "timvision": ("Timvision",),
    "infinity-plus": ("Infinity+",),
    "rakuten-tv": ("Rakuten TV",),
    "mubi": ("MUBI",),
    "apple-tv-plus": ("Apple TV",),
    "paramount-plus": ("Paramount Plus",),
    "raiplay": ("Rai Play",),
    "mediaset-infinity": ("Mediaset Infinity",),
}


@dataclass(frozen=True)
class ProviderVerification:
    slug: str
    name: str
    movie_provider_id: str | None
    tv_provider_id: str | None
    movie_name: str | None
    tv_name: str | None
    movie_verified: bool
    tv_verified: bool
    deactivated_movie: int
    deactivated_show: int


def _match(providers: dict[int, str], aliases: tuple[str, ...]) -> tuple[int, str] | None:
    wanted = {alias.casefold() for alias in aliases}
    for provider_id, name in providers.items():
        if name.strip().casefold() in wanted:
            return provider_id, name
    return None


def verify_tmdb_providers(
    db: Session,
    settings: Settings,
    *,
    country_code: str = "IT",
) -> list[ProviderVerification]:
    """Fetch live TMDb provider lists and update every canonical mapping."""
    source = db.scalar(select(Source).where(Source.key == "tmdb"))
    if source is None:
        raise RuntimeError("Fonte TMDb non trovata: eseguire seed-providers.")
    token = credentials_service.get_secret(db, settings, CredentialKind.TMDB)
    with TMDbClient(token) as client:
        movie_providers = {
            provider.provider_id: provider.name
            for provider in client.list_movie_providers(country_code)
        }
        tv_providers = {
            provider.provider_id: provider.name
            for provider in client.list_tv_providers(country_code)
        }

    providers = list(db.scalars(select(Provider).order_by(Provider.name)).all())
    results: list[ProviderVerification] = []
    verified_at: datetime = utcnow()
    for provider in providers:
        aliases = PROVIDER_ALIASES.get(provider.slug)
        if not aliases:
            continue
        movie = _match(movie_providers, aliases)
        tv = _match(tv_providers, aliases)
        mapping = db.scalar(
            select(ProviderMapping).where(
                ProviderMapping.provider_id == provider.id,
                ProviderMapping.source_id == source.id,
                ProviderMapping.country_code == country_code,
                ProviderMapping.is_primary.is_(True),
            )
        )
        if mapping is None and movie is None and tv is None:
            continue
        if mapping is None:
            mapping = ProviderMapping(
                provider_id=provider.id,
                source_id=source.id,
                country_code=country_code,
                external_provider_id=str(movie[0] if movie else tv[0] if tv else ""),
                is_primary=True,
            )
            db.add(mapping)
        metadata = dict(mapping.metadata_json or {})
        metadata.update(
            {
                "movie_provider_id": str(movie[0]) if movie else None,
                "tv_provider_id": str(tv[0]) if tv else None,
                "movie_name": movie[1] if movie else None,
                "tv_name": tv[1] if tv else None,
                "movie_verified": movie is not None,
                "tv_verified": tv is not None,
                "verified_at": verified_at.isoformat(),
                "verification_source": "tmdb/watch/providers",
                "country_code": country_code,
            }
        )
        mapping.metadata_json = metadata
        mapping.external_name = (movie or tv or (None, provider.name))[1]
        mapping.external_provider_id = str(
            movie[0] if movie else tv[0] if tv else mapping.external_provider_id
        )
        mapping.is_primary = True
        mapping.is_verified = movie is not None or tv is not None

        deactivated_movie = 0
        deactivated_show = 0
        if movie is None:
            deactivated_result = db.execute(
                update(Collection)
                .where(
                    Collection.provider_id == provider.id,
                    Collection.media_type == MediaType.MOVIE.value,
                    Collection.is_active.is_(True),
                )
                .values(is_active=False)
            )
            deactivated_movie = int(getattr(deactivated_result, "rowcount", 0) or 0)
        if tv is None:
            deactivated_result = db.execute(
                update(Collection)
                .where(
                    Collection.provider_id == provider.id,
                    Collection.media_type == MediaType.SHOW.value,
                    Collection.is_active.is_(True),
                )
                .values(is_active=False)
            )
            deactivated_show = int(getattr(deactivated_result, "rowcount", 0) or 0)
        results.append(
            ProviderVerification(
                slug=provider.slug,
                name=provider.name,
                movie_provider_id=str(movie[0]) if movie else None,
                tv_provider_id=str(tv[0]) if tv else None,
                movie_name=movie[1] if movie else None,
                tv_name=tv[1] if tv else None,
                movie_verified=movie is not None,
                tv_verified=tv is not None,
                deactivated_movie=deactivated_movie,
                deactivated_show=deactivated_show,
            )
        )

    audit.record(
        db,
        action="providers_verified",
        entity_type="provider",
        entity_id=None,
        actor_type=AuditActorType.SYSTEM,
        after={
            "country_code": country_code,
            "verified": sum(1 for item in results if item.movie_verified or item.tv_verified),
            "movie_verified": sum(1 for item in results if item.movie_verified),
            "tv_verified": sum(1 for item in results if item.tv_verified),
            "deactivated_movie": sum(item.deactivated_movie for item in results),
            "deactivated_show": sum(item.deactivated_show for item in results),
        },
    )
    db.commit()
    return results
