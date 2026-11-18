"""TMDb connector package."""

from __future__ import annotations

from app.connectors.tmdb.connector import CAPABILITIES, MAX_DISCOVER_PAGES, TMDbConnector

__all__ = ["CAPABILITIES", "MAX_DISCOVER_PAGES", "TMDbConnector"]
