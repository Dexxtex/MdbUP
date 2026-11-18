"""TMDb integration: synchronous client and typed payloads."""

from __future__ import annotations

from app.integrations.tmdb.client import (
    DEFAULT_BASE_URL,
    TMDbAuthError,
    TMDbClient,
    TMDbError,
    TMDbNotFoundError,
    TMDbRateLimitError,
    TMDbRequestError,
)
from app.integrations.tmdb.models import (
    TMDbDiscoverItem,
    TMDbDiscoverPage,
    TMDbExternalIds,
    TMDbProvider,
)

__all__ = [
    "DEFAULT_BASE_URL",
    "TMDbAuthError",
    "TMDbClient",
    "TMDbDiscoverItem",
    "TMDbDiscoverPage",
    "TMDbError",
    "TMDbExternalIds",
    "TMDbNotFoundError",
    "TMDbProvider",
    "TMDbRateLimitError",
    "TMDbRequestError",
]
