"""Connector registry: source key -> live connector instance.

Only sources with a real, configured connector are registered. A source without
a connector (JustWatch partner, manual CSV) is never simulated: callers get
``SourceUnavailableError`` instead of fake data.
"""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from app.connectors.base import SourceConnector
from app.connectors.justwatch.connector import (
    JUSTWATCH_SOURCE_KEY,
    JustWatchConnector,
)
from app.connectors.tmdb.connector import TMDB_SOURCE_KEY, TMDbConnector
from app.core.config import Settings
from app.domain.errors import SourceUnavailableError
from app.integrations.justwatch.client import JustWatchClient
from app.integrations.tmdb.client import DEFAULT_BASE_URL, TMDbClient
from app.services import credentials as credentials_service
from app.services.credentials import CredentialKind

ConnectorFactory = Callable[[Session, Settings], SourceConnector]

# Credentials required before a connector can be built for a source key.
_REQUIRED_CREDENTIALS: dict[str, CredentialKind] = {
    TMDB_SOURCE_KEY: CredentialKind.TMDB,
    "tvdb": CredentialKind.TVDB,
}


def _build_tmdb(db: Session, settings: Settings) -> SourceConnector:
    token = credentials_service.get_secret(db, settings, CredentialKind.TMDB)
    client = TMDbClient(
        token,
        base_url=DEFAULT_BASE_URL,
        timeout=float(settings.http_timeout_seconds),
        max_retries=settings.http_max_retries,
        backoff_base_seconds=settings.http_backoff_base_ms / 1000,
        backoff_max_seconds=settings.http_backoff_max_ms / 1000,
        jitter_ratio=settings.http_jitter_ratio,
    )
    return TMDbConnector(client)


def _build_justwatch(db: Session, settings: Settings) -> SourceConnector:
    """Build the JustWatch connector over the public GraphQL endpoint.

    No credential is needed. The source is a first-class aggregator: the only
    guardrail is the local throttle, because the endpoint reports no rate limit
    and does not warn before blocking. The response cache keeps repeated
    collection runs inside the same throttle budget.
    """
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
    return JustWatchConnector(client, language=settings.justwatch_language)


_FACTORIES: dict[str, ConnectorFactory] = {
    TMDB_SOURCE_KEY: _build_tmdb,
    JUSTWATCH_SOURCE_KEY: _build_justwatch,
}


def is_registered(source_key: str) -> bool:
    return source_key in _FACTORIES


def required_credential_kind(source_key: str) -> CredentialKind | None:
    return _REQUIRED_CREDENTIALS.get(source_key)


def ensure_source_credentials(db: Session, settings: Settings, source_key: str) -> None:
    """Raise ``CredentialMissingError`` when a required credential is absent."""
    kind = required_credential_kind(source_key)
    if kind is None:
        return
    credentials_service.get_secret(db, settings, kind)


def create_connector(db: Session, settings: Settings, source_key: str) -> SourceConnector:
    """Build the connector for ``source_key`` or fail with a clear error."""
    factory = _FACTORIES.get(source_key)
    if factory is None:
        raise SourceUnavailableError(
            f"Connettore non disponibile per la fonte '{source_key}'.",
            details={"source_key": source_key},
        )
    return factory(db, settings)
