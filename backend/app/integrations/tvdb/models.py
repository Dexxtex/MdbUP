"""Typed payloads returned by TheTVDB client."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TVDbCompany:
    """A TVDB company, not a country-specific watch provider."""

    company_id: str
    name: str
    company_type: str | None = None
    slug: str | None = None
    country: str | None = None


@dataclass(frozen=True)
class TVDbList:
    """A TVDB official or user list. TVDB does not classify lists by year."""

    list_id: str
    name: str
    overview: str | None = None
    is_official: bool = False
    score: int | None = None
    url: str | None = None
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class TVDbGenre:
    genre_id: str
    name: str
    slug: str | None = None


@dataclass(frozen=True)
class TVDbCatalogItem:
    item_id: str
    media_type: str
    name: str
    year: str | None = None
    overview: str | None = None
    image: str | None = None
    score: float | None = None
    slug: str | None = None
