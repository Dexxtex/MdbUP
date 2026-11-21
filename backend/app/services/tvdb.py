"""TheTVDB company discovery for the source API."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domain.errors import SOURCE, AppError
from app.integrations.tvdb.client import TVDbAuthError, TVDbClient, TVDbRequestError
from app.integrations.tvdb.models import TVDbCatalogItem, TVDbCompany, TVDbGenre
from app.services import credentials as credentials_service
from app.services.credentials import CredentialKind


@contextmanager
def _client(db: Session, settings: Settings) -> Iterator[TVDbClient]:
    token = credentials_service.get_secret(db, settings, CredentialKind.TVDB)
    client = TVDbClient(
        token,
        timeout=float(settings.http_timeout_seconds),
        max_retries=settings.http_max_retries,
    )
    try:
        yield client
    except TVDbAuthError as exc:
        raise AppError(
            "TheTVDB ha rifiutato la credenziale.",
            code="SOURCE_AUTH_FAILED",
            category=SOURCE,
            status_code=409,
        ) from exc
    except TVDbRequestError as exc:
        raise AppError(
            "TheTVDB non ha risposto correttamente.",
            code="SOURCE_UNAVAILABLE",
            category=SOURCE,
            status_code=503,
            retryable=True,
        ) from exc
    finally:
        client.close()


def search_companies(db: Session, settings: Settings, query: str) -> list[TVDbCompany]:
    """Search TVDB companies by name; no country availability is implied."""
    with _client(db, settings) as client:
        return client.search_companies(query)


def list_genres(db: Session, settings: Settings) -> list[TVDbGenre]:
    with _client(db, settings) as client:
        return client.list_genres()


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
    with _client(db, settings) as client:
        return client.filter_series(
            country=country,
            language=language,
            genre_id=genre_id,
            year=year,
            sort=sort,
            sort_type=sort_type,
        )
