"""JustWatch connector package (public endpoint)."""

from __future__ import annotations

from app.connectors.justwatch.connector import (
    CAPABILITIES,
    DEFAULT_YEAR_FROM,
    DEFAULT_YEAR_TO,
    JUSTWATCH_SOURCE_KEY,
    PROVIDER_COLLECTIONS,
    JustWatchConnector,
    YearRanges,
)

__all__ = [
    "CAPABILITIES",
    "DEFAULT_YEAR_FROM",
    "DEFAULT_YEAR_TO",
    "JUSTWATCH_SOURCE_KEY",
    "PROVIDER_COLLECTIONS",
    "JustWatchConnector",
    "YearRanges",
]
