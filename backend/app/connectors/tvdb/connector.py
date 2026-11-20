"""TheTVDB connector: health and company metadata, never country availability.

TVDB exposes companies and title metadata, but no per-country watch offers.
It is therefore registered so the generic source healthcheck and credential
UI work, while collection acquisition remains explicitly unsupported.
"""

from __future__ import annotations

import time
from collections.abc import Sequence

from app.connectors.base import (
    ConnectorCapabilities,
    HealthStatus,
    NormalizedItem,
    NotSupportedError,
    Page,
    RawItem,
    SourceCollection,
    SourceProvider,
)
from app.integrations.tvdb.client import TVDbClient, TVDbError

TVDB_SOURCE_KEY = "tvdb"

CAPABILITIES = ConnectorCapabilities(
    catalog=False,
    recently_added=False,
    upcoming=False,
    charts=False,
    ordering=False,
    added_dates=False,
    seasons_episodes=True,
    full_pagination=False,
    data_export=False,
    requires_credentials=True,
    requires_contract=False,
    max_page_size=500,
    notes=(
        "TheTVDB fornisce metadati e company ID, non disponibilità per paese. "
        "Non è utilizzabile come fonte di collezioni MDBList."
    ),
)


class TVDbConnector:
    key = TVDB_SOURCE_KEY
    capabilities = CAPABILITIES

    def __init__(self, client: TVDbClient) -> None:
        self._client = client

    def healthcheck(self) -> HealthStatus:
        started = time.monotonic()
        try:
            self._client.healthcheck()
        except TVDbError as exc:
            return HealthStatus(
                ok=False,
                message=str(exc),
                latency_ms=int((time.monotonic() - started) * 1000),
            )
        return HealthStatus(
            ok=True,
            message="TheTVDB raggiungibile.",
            latency_ms=int((time.monotonic() - started) * 1000),
        )

    def list_providers(self, country_code: str = "IT") -> Sequence[SourceProvider]:
        # TVDB companies are global metadata, not a country-specific provider
        # list. Returning them as Italian providers would be a false claim.
        return ()

    def list_collections(self, country_code: str = "IT") -> Sequence[SourceCollection]:
        raise NotSupportedError("TheTVDB non espone disponibilità per paese.")

    def fetch_collection_page(
        self,
        collection: SourceCollection,
        cursor: str | None,
        page_size: int,
    ) -> Page:
        raise NotSupportedError("TheTVDB non espone disponibilità per paese.")

    def normalize_item(self, raw: RawItem) -> NormalizedItem:
        raise NotSupportedError("TheTVDB non espone disponibilità per paese.")

    def close(self) -> None:
        self._client.close()
