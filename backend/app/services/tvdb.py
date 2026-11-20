"""TheTVDB company discovery for the source API."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.integrations.tvdb.client import TVDbClient
from app.integrations.tvdb.models import TVDbCompany
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
