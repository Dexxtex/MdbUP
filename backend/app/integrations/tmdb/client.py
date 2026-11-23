"""Synchronous TMDb API client (v3 API key or v4 Bearer token).

TMDb accepts both a v3 ``api_key`` query parameter and a v4 read access token
as ``Authorization: Bearer``. The credential shape decides the mode: a JWT
(three dot-separated segments) uses the header, anything else uses ``api_key``.

Endpoints are limited to the ones verified in the phase-1 project spec:
watch providers, discover, external ids and find. The client never logs the
credential and never follows redirects.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable, Sequence
from typing import Any

import httpx

from app.connectors.base import HealthStatus
from app.core.metrics import record_api_call
from app.core.retry import backoff_delay
from app.domain.enums import MediaType
from app.integrations.tmdb.models import (
    TMDbDiscoverItem,
    TMDbDiscoverPage,
    TMDbExternalIds,
    TMDbProvider,
    TMDbSeason,
    TMDbTvDetails,
)

DEFAULT_BASE_URL = "https://api.themoviedb.org/3"
DEFAULT_TIMEOUT_SECONDS = 20.0
DEFAULT_MAX_RETRY_WAIT_SECONDS = 5.0
DEFAULT_LANGUAGE = "it-IT"


def tmdb_auth_mode(token: str) -> str:
    """Return ``"bearer"`` for a v4 JWT read token, ``"query"`` for a v3 key."""
    return "bearer" if token.count(".") == 2 else "query"


class TMDbError(RuntimeError):
    """Base class for TMDb transport and protocol errors."""


class TMDbAuthError(TMDbError):
    """The API key/token was rejected (401/403)."""


class TMDbNotFoundError(TMDbError):
    """The requested resource does not exist (404)."""


class TMDbRateLimitError(TMDbError):
    """TMDb answered 429 and the wait exceeds what the client is willing to block."""

    def __init__(self, message: str, *, retry_after_seconds: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class TMDbRequestError(TMDbError):
    """Any other HTTP or payload error."""


def _retry_after_seconds(response: httpx.Response) -> float:
    raw = response.headers.get("retry-after")
    if raw is None:
        return 1.0
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 1.0


def _parse_year(value: Any) -> int | None:
    if not isinstance(value, str) or len(value) < 4:
        return None
    try:
        return int(value[:4])
    except ValueError:
        return None


class TMDbClient:
    """Minimal TMDb client with bounded retries for transient failures."""

    def __init__(
        self,
        token: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retry_wait_seconds: float = DEFAULT_MAX_RETRY_WAIT_SECONDS,
        max_retries: int = 4,
        backoff_base_seconds: float = 0.5,
        backoff_max_seconds: float = 30.0,
        jitter_ratio: float = 0.30,
        sleep: Callable[[float], None] = time.sleep,
        rng: random.Random | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        if not token:
            raise ValueError("Token TMDb mancante.")
        self.base_url = base_url.rstrip("/")
        self.max_retry_wait_seconds = max_retry_wait_seconds
        self.max_retries = max(1, max_retries)
        self.backoff_base_seconds = max(0.0, backoff_base_seconds)
        self.backoff_max_seconds = max(0.0, backoff_max_seconds)
        self.jitter_ratio = min(max(0.0, jitter_ratio), 1.0)
        self._sleep = sleep
        self._rng = rng
        self._token = token
        # v4 read access tokens are JWTs; v3 keys are 32-char hex strings.
        self._use_bearer = tmdb_auth_mode(token) == "bearer"
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=timeout, follow_redirects=False)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> TMDbClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self._use_bearer:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def _delay(self, attempt: int) -> float:
        return backoff_delay(
            attempt,
            base_seconds=self.backoff_base_seconds,
            max_seconds=self.backoff_max_seconds,
            jitter_ratio=self.jitter_ratio,
            rng=self._rng,
        )

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        query = dict(params or {})
        if not self._use_bearer:
            query["api_key"] = self._token
        for attempt in range(1, self.max_retries + 1):
            record_api_call("tmdb")
            try:
                response = self._client.get(url, params=query, headers=self._headers())
            except httpx.TimeoutException as exc:
                if attempt < self.max_retries:
                    self._sleep(self._delay(attempt))
                    continue
                raise TMDbRequestError(f"Timeout TMDb su {path}.") from exc
            except httpx.HTTPError as exc:
                if attempt < self.max_retries:
                    self._sleep(self._delay(attempt))
                    continue
                raise TMDbRequestError(f"Errore di rete TMDb su {path}.") from exc
            if response.status_code == 429:
                retry_after = _retry_after_seconds(response)
                if attempt < self.max_retries and retry_after <= self.max_retry_wait_seconds:
                    self._sleep(retry_after)
                    continue
                raise TMDbRateLimitError(
                    f"TMDb rate limit su {path}.",
                    retry_after_seconds=retry_after,
                )
            if response.status_code >= 500:
                if attempt < self.max_retries:
                    self._sleep(self._delay(attempt))
                    continue
                raise TMDbRequestError(f"TMDb ha risposto {response.status_code} su {path}.")
            if response.status_code in (401, 403):
                raise TMDbAuthError(f"TMDb ha rifiutato la credenziale su {path}.")
            if response.status_code == 404:
                raise TMDbNotFoundError(f"Risorsa TMDb non trovata: {path}.")
            if response.status_code >= 400:
                raise TMDbRequestError(f"TMDb ha risposto {response.status_code} su {path}.")
            try:
                payload = response.json()
            except ValueError as exc:
                raise TMDbRequestError(f"Payload TMDb non JSON su {path}.") from exc
            if not isinstance(payload, dict):
                raise TMDbRequestError(f"Payload TMDb inatteso su {path}.")
            return payload
        raise TMDbRateLimitError(f"TMDb rate limit su {path}.")  # pragma: no cover

    def healthcheck(self) -> HealthStatus:
        """Probe ``/configuration``; never raises, returns the outcome."""
        started = time.monotonic()
        try:
            self._get("/configuration")
        except TMDbError as exc:
            latency_ms = int((time.monotonic() - started) * 1000)
            return HealthStatus(ok=False, message=str(exc), latency_ms=latency_ms)
        latency_ms = int((time.monotonic() - started) * 1000)
        return HealthStatus(ok=True, message="TMDb raggiungibile.", latency_ms=latency_ms)

    def _list_providers(self, media_type: MediaType, country: str) -> list[TMDbProvider]:
        segment = "movie" if media_type is MediaType.MOVIE else "tv"
        payload = self._get(
            f"/watch/providers/{segment}",
            {"watch_region": country, "language": DEFAULT_LANGUAGE},
        )
        results = payload.get("results") or []
        providers: list[TMDbProvider] = []
        for entry in results:
            provider_id = entry.get("provider_id")
            name = entry.get("provider_name")
            if not isinstance(provider_id, int) or not isinstance(name, str):
                continue
            priority = entry.get("display_priority")
            providers.append(
                TMDbProvider(
                    provider_id=provider_id,
                    name=name,
                    country_code=country,
                    display_priority=priority if isinstance(priority, int) else None,
                    logo_path=entry.get("logo_path"),
                )
            )
        return providers

    def list_movie_providers(self, country: str = "IT") -> list[TMDbProvider]:
        return self._list_providers(MediaType.MOVIE, country)

    def list_tv_providers(self, country: str = "IT") -> list[TMDbProvider]:
        return self._list_providers(MediaType.SHOW, country)

    def _discover(
        self,
        media_type: MediaType,
        provider_id: int,
        country: str,
        page: int,
        genre_ids: Sequence[int] | None = None,
        sort_by: str = "popularity.desc",
    ) -> TMDbDiscoverPage:
        segment = "movie" if media_type is MediaType.MOVIE else "tv"
        params: dict[str, Any] = {
            "watch_region": country,
            "with_watch_providers": provider_id,
            "with_watch_monetization_types": "flatrate",
            "sort_by": sort_by,
            "page": page,
            "language": DEFAULT_LANGUAGE,
        }
        if genre_ids:
            params["with_genres"] = ",".join(str(genre_id) for genre_id in genre_ids)
        payload = self._get(f"/discover/{segment}", params)
        results = payload.get("results") or []
        items: list[TMDbDiscoverItem] = []
        for entry in results:
            tmdb_id = entry.get("id")
            if not isinstance(tmdb_id, int):
                continue
            if media_type is MediaType.MOVIE:
                title = entry.get("title") or entry.get("original_title") or ""
                original_title = entry.get("original_title")
                year = _parse_year(entry.get("release_date"))
            else:
                title = entry.get("name") or entry.get("original_name") or ""
                original_title = entry.get("original_name")
                year = _parse_year(entry.get("first_air_date"))
            popularity = entry.get("popularity")
            items.append(
                TMDbDiscoverItem(
                    tmdb_id=tmdb_id,
                    media_type=media_type,
                    title=str(title),
                    original_title=original_title if isinstance(original_title, str) else None,
                    release_year=year,
                    popularity=float(popularity) if isinstance(popularity, (int, float)) else None,
                    overview=entry.get("overview"),
                    raw=entry,
                )
            )
        total_pages = payload.get("total_pages")
        total_results = payload.get("total_results")
        return TMDbDiscoverPage(
            page=int(payload.get("page") or page),
            total_pages=int(total_pages) if isinstance(total_pages, int) else 0,
            total_results=int(total_results) if isinstance(total_results, int) else 0,
            items=tuple(items),
            raw={"page": payload.get("page"), "total_pages": total_pages},
        )

    def discover_movies(
        self,
        provider_id: int,
        country: str = "IT",
        page: int = 1,
        genre_ids: Sequence[int] | None = None,
        sort_by: str = "popularity.desc",
    ) -> TMDbDiscoverPage:
        return self._discover(MediaType.MOVIE, provider_id, country, page, genre_ids, sort_by)

    def discover_tv(
        self,
        provider_id: int,
        country: str = "IT",
        page: int = 1,
        genre_ids: Sequence[int] | None = None,
        sort_by: str = "popularity.desc",
    ) -> TMDbDiscoverPage:
        return self._discover(MediaType.SHOW, provider_id, country, page, genre_ids, sort_by)

    def external_ids(self, media_type: MediaType, tmdb_id: int) -> TMDbExternalIds:
        segment = "movie" if media_type is MediaType.MOVIE else "tv"
        payload = self._get(f"/{segment}/{tmdb_id}/external_ids")
        imdb_id = payload.get("imdb_id")
        return TMDbExternalIds(
            tmdb_id=tmdb_id,
            imdb_id=imdb_id if isinstance(imdb_id, str) and imdb_id else None,
        )

    def tv_details(self, tmdb_id: int) -> TMDbTvDetails:
        """Fetch show-level metadata; seasons/episodes are not media rows."""
        payload = self._get(f"/tv/{tmdb_id}")
        seasons: list[TMDbSeason] = []
        for entry in payload.get("seasons") or []:
            season_number = entry.get("season_number")
            if not isinstance(season_number, int):
                continue
            episode_count = entry.get("episode_count")
            seasons.append(
                TMDbSeason(
                    season_number=season_number,
                    name=entry.get("name") if isinstance(entry.get("name"), str) else None,
                    episode_count=(episode_count if isinstance(episode_count, int) else None),
                    air_date=(
                        entry.get("air_date") if isinstance(entry.get("air_date"), str) else None
                    ),
                )
            )
        number_of_seasons = payload.get("number_of_seasons")
        number_of_episodes = payload.get("number_of_episodes")
        return TMDbTvDetails(
            tmdb_id=tmdb_id,
            name=str(payload.get("name") or payload.get("original_name") or ""),
            number_of_seasons=(number_of_seasons if isinstance(number_of_seasons, int) else None),
            number_of_episodes=(
                number_of_episodes if isinstance(number_of_episodes, int) else None
            ),
            seasons=tuple(seasons),
            raw=payload,
        )

    def find_by_imdb(self, imdb_id: str, media_type: MediaType) -> int | None:
        """Resolve an IMDb id to a TMDb id through ``/find``."""
        payload = self._get(f"/find/{imdb_id}", {"external_source": "imdb_id"})
        key = "movie_results" if media_type is MediaType.MOVIE else "tv_results"
        for entry in payload.get(key) or []:
            tmdb_id = entry.get("id")
            if isinstance(tmdb_id, int):
                return tmdb_id
        return None
