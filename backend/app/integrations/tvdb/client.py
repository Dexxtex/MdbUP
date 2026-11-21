"""Minimal TheTVDB API v4 client for company/provider discovery.

TheTVDB is a metadata catalogue, not an availability API: a company is a
streaming service but TVDB does not expose per-country offers. The provider
catalog therefore treats TVDB as an additional identifier source, never as a
claim that the service is available in Italy.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import httpx

from app.integrations.tvdb.models import TVDbCatalogItem, TVDbCompany, TVDbGenre

DEFAULT_BASE_URL = "https://api4.thetvdb.com/v4"


def _data_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """TVDB returns either ``data: [...]`` or ``data: {items: [...]}``."""
    data = payload.get("data")
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        items = data.get("items")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    return []


class TVDbError(RuntimeError):
    """Base class for TVDB transport/protocol errors."""


class TVDbAuthError(TVDbError):
    """The API key was rejected."""


class TVDbRequestError(TVDbError):
    """A non-auth HTTP or payload error."""


class TVDbClient:
    """Small synchronous TVDB client with lazy login and bounded retries."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 20.0,
        max_retries: int = 3,
        sleep: Callable[[float], None] = time.sleep,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("TheTVDB API key mancante.")
        self.base_url = base_url.rstrip("/")
        self.max_retries = max(1, max_retries)
        self._sleep = sleep
        self._api_key = api_key
        self._token: str | None = None
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=timeout, follow_redirects=False)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> TVDbClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _login(self) -> None:
        response = self._request("POST", "/login", json={"apikey": self._api_key})
        token = (response.get("data") or {}).get("token")
        if not isinstance(token, str) or not token:
            raise TVDbAuthError("TheTVDB non ha restituito un token.")
        self._token = token

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            headers = {"Accept": "application/json"}
            if self._token:
                headers["Authorization"] = f"Bearer {self._token}"
            try:
                response = self._client.request(
                    method,
                    f"{self.base_url}{path}",
                    json=json,
                    params=params,
                    headers=headers,
                )
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt + 1 < self.max_retries:
                    self._sleep(0.5 * (2**attempt))
                    continue
                raise TVDbRequestError(f"TheTVDB non raggiungibile: {exc}") from exc
            if response.status_code in (401, 403):
                raise TVDbAuthError("TheTVDB ha rifiutato la credenziale.")
            if response.status_code >= 400:
                last_error = TVDbRequestError(
                    f"TheTVDB ha risposto {response.status_code} su {path}."
                )
                if response.status_code >= 500 and attempt + 1 < self.max_retries:
                    self._sleep(0.5 * (2**attempt))
                    continue
                raise last_error
            try:
                payload = response.json()
            except ValueError as exc:
                raise TVDbRequestError("Payload TheTVDB non JSON.") from exc
            if not isinstance(payload, dict):
                raise TVDbRequestError("Payload TheTVDB inatteso.")
            return payload
        raise TVDbRequestError(str(last_error or "TheTVDB non disponibile."))

    def _ensure_token(self) -> None:
        if not self._token:
            self._login()

    def search_companies(self, query: str, *, limit: int = 50) -> list[TVDbCompany]:
        """Search TVDB companies by name.

        TVDB has no streaming-only company type and no country availability:
        these rows are identifiers, never proof of an Italian offer.
        """
        query = query.strip()
        if len(query) < 2:
            return []
        self._ensure_token()
        payload = self._request(
            "GET",
            "/search",
            params={
                "query": query,
                "type": "company",
                "limit": max(1, min(limit, 100)),
            },
        )
        rows: dict[str, TVDbCompany] = {}
        for item in _data_items(payload):
            raw_id = item.get("id") or item.get("objectID")
            name = item.get("name") or item.get("title")
            if raw_id is None or not name:
                continue
            company_id = str(raw_id).removeprefix("company-")
            rows[company_id] = TVDbCompany(
                company_id=company_id,
                name=str(name),
                company_type=item.get("company_type") or item.get("companyTypeName"),
                slug=item.get("slug"),
                country=item.get("country"),
            )
        return sorted(rows.values(), key=lambda row: (row.name.casefold(), row.company_id))

    def list_genres(self) -> list[TVDbGenre]:
        """TVDB genres used by the series filter."""
        self._ensure_token()
        payload = self._request("GET", "/genres")
        rows: list[TVDbGenre] = []
        for item in _data_items(payload):
            if not isinstance(item, dict) or item.get("id") is None or not item.get("name"):
                continue
            rows.append(
                TVDbGenre(
                    genre_id=str(item["id"]),
                    name=str(item["name"]),
                    slug=item.get("slug"),
                )
            )
        return sorted(rows, key=lambda item: item.name.casefold())

    def filter_series(
        self,
        *,
        country: str,
        language: str,
        genre_id: str | None = None,
        year: int | None = None,
        sort: str = "score",
        sort_type: str = "desc",
    ) -> list[TVDbCatalogItem]:
        """Filter movies or series by origin country, language, genre and year.

        TVDB's ``country``/``lang`` are metadata (country of origin and original
        language), not availability in a streaming market.
        """
        segment = "series"
        params: dict[str, object] = {
            "country": country,
            "lang": language,
            "sort": sort,
            "sortType": sort_type,
        }
        if genre_id is not None:
            params["genre"] = genre_id
        if year is not None:
            params["year"] = year
        self._ensure_token()
        payload = self._request("GET", f"/{segment}/filter", params=params)
        rows: list[TVDbCatalogItem] = []
        for item in _data_items(payload):
            if not isinstance(item, dict) or item.get("id") is None or not item.get("name"):
                continue
            score = item.get("score")
            rows.append(
                TVDbCatalogItem(
                    item_id=str(item["id"]),
                    name=str(item["name"]),
                    year=str(item["year"]) if item.get("year") is not None else None,
                    overview=item.get("overview"),
                    image=item.get("image"),
                    score=float(score) if isinstance(score, (int, float)) else None,
                    slug=item.get("slug"),
                )
            )
        return rows

    def healthcheck(self) -> None:
        self._ensure_token()
        self._request("GET", "/companies", params={"page": 0})
