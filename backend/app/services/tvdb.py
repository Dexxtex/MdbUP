"""TheTVDB company discovery for the source API."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.integrations.tvdb.client import TVDbClient
from app.integrations.tvdb.models import TVDbCatalogItem, TVDbCompany, TVDbGenre
from app.services import credentials as credentials_service
from app.services.credentials import CredentialKind


def list_streaming_companies(db: Session, settings: Settings) -> list[TVDbCompany]:
    """Read TVDB SVOD/TVOD/AVOD companies; no country availability is implied."""
    token = credentials_service.get_secret(db, settings, CredentialKind.TVDB)
    client = TVDbClient(
        token,
        timeout=float(settings.http_timeout_seconds),
        max_retries=settings.http_max_retries,
    )
    try:
        return client.list_streaming_companies()
    finally:
        client.close()


def list_genres(db: Session, settings: Settings) -> list[TVDbGenre]:
    token = credentials_service.get_secret(db, settings, CredentialKind.TVDB)
    client = TVDbClient(
        token,
        timeout=float(settings.http_timeout_seconds),
        max_retries=settings.http_max_retries,
    )
    try:
        return client.list_genres()
    finally:
        client.close()


def filter_series(
    db: Session,
    settings: Settings,
    *,
    country: str,
    language: str,
    genre_id: str | None = None,
    year: int | None = None,
    sort: str = "score",
    sort_type: str = "desc",
) -> list[TVDbCatalogItem]:
    token = credentials_service.get_secret(db, settings, CredentialKind.TVDB)
    client = TVDbClient(
        token,
        timeout=float(settings.http_timeout_seconds),
        max_retries=settings.http_max_retries,
    )
    try:
        return client.filter_series(
            country=country,
            language=language,
            genre_id=genre_id,
            year=year,
            sort=sort,
            sort_type=sort_type,
        )
    finally:
        client.close()
