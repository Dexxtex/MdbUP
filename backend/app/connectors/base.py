from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol

from app.domain.enums import CollectionKind, CollectionOrigin, DateBasis, MediaType
from app.domain.health import HealthStatus


class NotSupportedError(RuntimeError):
    """The source does not support the requested capability."""


@dataclass(frozen=True)
class ConnectorCapabilities:
    catalog: bool = False
    recently_added: bool = False
    upcoming: bool = False
    charts: bool = False
    ordering: bool = False
    added_dates: bool = False
    seasons_episodes: bool = False
    full_pagination: bool = False
    data_export: bool = False
    requires_credentials: bool = True
    requires_contract: bool = False
    # A source whose pages can fail independently must never produce a COMPLETE
    # snapshot when any fetch failed: the acquisition classifies it INCOMPLETE.
    partial_on_error: bool = False
    max_page_size: int = 100
    notes: str = ""


@dataclass(frozen=True)
class SourceProvider:
    external_id: str
    name: str
    country_code: str = "IT"


@dataclass(frozen=True)
class SourceCollection:
    key: str
    name: str
    provider_external_id: str
    media_type: MediaType
    kind: CollectionKind
    origin: CollectionOrigin
    date_basis: DateBasis
    source_url: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RawItem:
    source_item_id: str
    media_type: MediaType
    title: str
    year: int | None = None
    tmdb_id: int | None = None
    imdb_id: str | None = None
    tvdb_id: int | None = None
    source_date_created: date | None = None
    offer_types: frozenset[str] = field(default_factory=frozenset)
    availability_status: str | None = None
    source_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Page:
    items: Sequence[RawItem]
    next_cursor: str | None
    total_pages: int | None = None
    total_items: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class NormalizedItem:
    media_type: MediaType
    tmdb_id: int | None
    imdb_id: str | None
    title: str
    year: int | None
    offer_types: frozenset[str]
    source_date_created: date | None
    date_basis: DateBasis
    availability_status: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class SourceConnector(Protocol):
    key: str
    capabilities: ConnectorCapabilities

    def healthcheck(self) -> HealthStatus: ...

    def list_providers(self, country_code: str) -> Sequence[SourceProvider]: ...

    def list_collections(self, country_code: str) -> Sequence[SourceCollection]: ...

    def fetch_collection_page(
        self,
        collection: SourceCollection,
        cursor: str | None,
        page_size: int,
    ) -> Page: ...

    def normalize_item(self, raw: RawItem) -> NormalizedItem: ...

    def close(self) -> None: ...
