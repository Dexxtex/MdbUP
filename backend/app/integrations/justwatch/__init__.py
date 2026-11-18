"""JustWatch public GraphQL integration: client and typed payloads."""

from __future__ import annotations

from app.integrations.justwatch.client import (
    DEFAULT_BASE_URL,
    MAX_PAGE_SIZE,
    MAX_REACHABLE_ITEMS,
    JustWatchAuthError,
    JustWatchClient,
    JustWatchError,
    JustWatchGraphQLError,
    JustWatchRateLimitError,
    JustWatchRequestError,
)
from app.integrations.justwatch.models import (
    JustWatchChartEntry,
    JustWatchEpisode,
    JustWatchOffer,
    JustWatchPackage,
    JustWatchPage,
    JustWatchSeason,
    JustWatchTitle,
)

__all__ = [
    "DEFAULT_BASE_URL",
    "MAX_PAGE_SIZE",
    "MAX_REACHABLE_ITEMS",
    "JustWatchAuthError",
    "JustWatchChartEntry",
    "JustWatchClient",
    "JustWatchError",
    "JustWatchGraphQLError",
    "JustWatchEpisode",
    "JustWatchOffer",
    "JustWatchPackage",
    "JustWatchPage",
    "JustWatchRateLimitError",
    "JustWatchRequestError",
    "JustWatchSeason",
    "JustWatchTitle",
]
