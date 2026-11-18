"""Synchronous client for the public JustWatch GraphQL endpoint.

This is the *public* endpoint the website itself calls. It is not the
commercial JustWatch Partner API: there are no credentials, no contract and no
support commitment, and the Terms of Service forbid scraping/data mining. The
connector built on top of this client is therefore opt-in and disabled by
default (see ``JUSTWATCH_PUBLIC_ENABLED``).

What the endpoint actually allows, measured against the live service:

- 100 items per page at most (``first: 101`` answers ``page too large``);
- no way to reach past item #1999 (``offset`` beyond that returns no edges);
- no rate-limit headers and no ``429`` observed, but also no warning before a
  block: throttling is a local, voluntary choice;
- introspection disabled, so the documents in ``queries.py`` are hand-verified.

The client never logs the payload, never follows redirects and keeps a minimum
interval between calls. The interval is enforced by :data:`_PROCESS_PACER`, a
process-wide pacer: the worker runs with concurrency 2 and each task builds its
own client, so a per-instance timer would allow two requests per second.
Successful payloads are cached in-process for a short TTL
(``JUSTWATCH_CACHE_TTL_SECONDS``, ``JUSTWATCH_CACHE_MAX_ENTRIES``); errors and
the healthcheck are never cached, and a response whose shape drifted raises
:class:`JustWatchGraphQLError` instead of producing an empty ``COMPLETE`` page.
"""

from __future__ import annotations

import copy
import json
import threading
import time
from typing import Any

import httpx

from app.connectors.base import HealthStatus
from app.core.metrics import record_api_call, record_cache_event
from app.core.retry import backoff_delay
from app.domain.enums import MediaType
from app.integrations.justwatch.models import (
    JustWatchChartEntry,
    JustWatchEpisode,
    JustWatchOffer,
    JustWatchPackage,
    JustWatchPage,
    JustWatchSeason,
    JustWatchTitle,
)
from app.integrations.justwatch.queries import (
    CHART_OBJECT_TYPES,
    NEW_PAGE_TYPES,
    QUERY_EPISODES,
    QUERY_GENRES,
    QUERY_HEALTHCHECK,
    QUERY_NEW_TITLES,
    QUERY_PACKAGES,
    QUERY_POPULAR_TITLES,
    QUERY_SEARCH_TITLES,
    QUERY_SEASONS,
    QUERY_STREAMING_CHARTS,
)

DEFAULT_BASE_URL = "https://apis.justwatch.com/graphql"
DEFAULT_TIMEOUT_SECONDS = 20.0
DEFAULT_MAX_RETRY_WAIT_SECONDS = 5.0
DEFAULT_MIN_INTERVAL_SECONDS = 1.0
DEFAULT_CACHE_TTL_SECONDS = 300.0
DEFAULT_CACHE_MAX_ENTRIES = 512
DEFAULT_PLATFORM = "WEB"

# Hard server limits, verified against the live endpoint.
MAX_PAGE_SIZE = 100
MAX_REACHABLE_ITEMS = 1999


class JustWatchError(RuntimeError):
    """Base class for JustWatch transport and protocol errors."""


class JustWatchAuthError(JustWatchError):
    """The endpoint answered 401/403."""


class JustWatchRateLimitError(JustWatchError):
    """The endpoint answered 429 and the wait exceeds the client budget."""

    def __init__(self, message: str, *, retry_after_seconds: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class JustWatchRequestError(JustWatchError):
    """Any other HTTP or payload error."""


class JustWatchGraphQLError(JustWatchError):
    """A GraphQL ``errors`` payload or a drifted response shape.

    The same exception covers a missing/non-object root field, a connection
    without ``pageInfo`` and ``edges`` that is not a list: the acquisition layer
    must see the anomaly, never an empty ``COMPLETE`` page.
    """

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


SCHEMA_DRIFT_CODE = "SCHEMA_DRIFT"


def _cache_key(query: str, variables: dict[str, Any] | None) -> str:
    return json.dumps([query, variables or {}], sort_keys=True, default=str)


class RequestPacer:
    """Minimum interval between calls, shareable across client instances.

    ``wait`` holds the lock for the whole pause, so concurrent threads queue
    behind the same deadline instead of all measuring the same idle gap. The
    interval is measured start-to-start, which is what a "1 request per second"
    budget means for the remote endpoint.
    """

    def __init__(self, *, monotonic=time.monotonic, sleep=time.sleep) -> None:
        self._monotonic = monotonic
        self._sleep = sleep
        self._lock = threading.Lock()
        self._last_call_at: float | None = None

    def wait(self, min_interval_seconds: float) -> None:
        if min_interval_seconds <= 0:
            return
        with self._lock:
            if self._last_call_at is not None:
                remaining = min_interval_seconds - (self._monotonic() - self._last_call_at)
                if remaining > 0:
                    self._sleep(remaining)
            self._last_call_at = self._monotonic()


# One pacer per process: every client built by the registry shares it.
_PROCESS_PACER = RequestPacer()


class ResponseCache:
    """Small TTL cache for successful GraphQL payloads.

    Entries are deep-copied on write and on read, so a caller mutating a page
    cannot poison the next call. Expired entries are dropped lazily; when the
    cache is full the oldest insertion is evicted first.
    """

    def __init__(
        self,
        *,
        ttl_seconds: float = DEFAULT_CACHE_TTL_SECONDS,
        max_entries: int = DEFAULT_CACHE_MAX_ENTRIES,
        monotonic=time.monotonic,
    ) -> None:
        self.ttl_seconds = max(0.0, float(ttl_seconds))
        self.max_entries = max(0, int(max_entries))
        self._monotonic = monotonic
        self._entries: dict[str, tuple[float, dict[str, Any]]] = {}

    @property
    def enabled(self) -> bool:
        return self.ttl_seconds > 0 and self.max_entries > 0

    def get(self, key: str) -> dict[str, Any] | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        expires_at, payload = entry
        if expires_at <= self._monotonic():
            self._entries.pop(key, None)
            return None
        return copy.deepcopy(payload)

    def set(self, key: str, payload: dict[str, Any]) -> None:
        if not self.enabled:
            return
        self._drop_expired()
        while len(self._entries) >= self.max_entries:
            self._entries.pop(next(iter(self._entries)))
        self._entries[key] = (self._monotonic() + self.ttl_seconds, copy.deepcopy(payload))

    def clear(self) -> None:
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)

    def _drop_expired(self) -> None:
        now = self._monotonic()
        for key in [key for key, (expires_at, _) in self._entries.items() if expires_at <= now]:
            self._entries.pop(key, None)


def _validate_connection(data: dict[str, Any], field: str, operation: str) -> dict[str, Any]:
    """Raise ``JustWatchGraphQLError`` when a connection is not shaped as expected."""
    connection = data.get(field)
    if not isinstance(connection, dict):
        raise JustWatchGraphQLError(
            f"Schema JustWatch inatteso: campo '{field}' mancante o non oggetto ({operation}).",
            code=SCHEMA_DRIFT_CODE,
        )
    if not isinstance(connection.get("pageInfo"), dict):
        raise JustWatchGraphQLError(
            f"Schema JustWatch inatteso: pageInfo mancante in '{field}' ({operation}).",
            code=SCHEMA_DRIFT_CODE,
        )
    if not isinstance(connection.get("edges"), list):
        raise JustWatchGraphQLError(
            f"Schema JustWatch inatteso: 'edges' non è una lista in '{field}' ({operation}).",
            code=SCHEMA_DRIFT_CODE,
        )
    return connection


def _validate_sequence(data: dict[str, Any], field: str, operation: str) -> list[Any]:
    """Raise ``JustWatchGraphQLError`` when a list root field is missing."""
    value = data.get(field)
    if not isinstance(value, list):
        raise JustWatchGraphQLError(
            f"Schema JustWatch inatteso: campo '{field}' mancante o non lista ({operation}).",
            code=SCHEMA_DRIFT_CODE,
        )
    return value


def _retry_after_seconds(response: httpx.Response) -> float:
    raw = response.headers.get("retry-after")
    if raw is None:
        return 1.0
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 1.0


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _media_type(value: Any) -> MediaType | None:
    if value == MediaType.MOVIE.value:
        return MediaType.MOVIE
    if value == MediaType.SHOW.value:
        return MediaType.SHOW
    return None


def _parse_offers(node: dict[str, Any]) -> tuple[JustWatchOffer, ...]:
    offers: list[JustWatchOffer] = []
    for raw_offer in node.get("offers") or []:
        package = raw_offer.get("package") or {}
        offers.append(
            JustWatchOffer(
                monetization_type=str(raw_offer.get("monetizationType") or ""),
                presentation_type=raw_offer.get("presentationType"),
                package_short_name=package.get("shortName"),
                package_name=package.get("clearName"),
                standard_web_url=raw_offer.get("standardWebURL"),
            )
        )
    return tuple(offers)


def _parse_title(node: dict[str, Any]) -> JustWatchTitle | None:
    media_type = _media_type(node.get("objectType"))
    node_id = node.get("id")
    content = node.get("content") or {}
    if media_type is None or not node_id or not content.get("title"):
        return None
    external = content.get("externalIds") or {}
    return JustWatchTitle(
        node_id=str(node_id),
        media_type=media_type,
        title=str(content["title"]),
        year=_to_int(content.get("originalReleaseYear")),
        tmdb_id=_to_int(external.get("tmdbId")),
        imdb_id=external.get("imdbId") or None,
        full_path=content.get("fullPath"),
        runtime_minutes=_to_int(content.get("runtime")),
        offers=_parse_offers(node),
        raw=node,
    )


class JustWatchClient:
    """Minimal, throttled GraphQL client for the public JustWatch endpoint."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = 4,
        backoff_base_seconds: float = 0.5,
        backoff_max_seconds: float = 30.0,
        jitter_ratio: float = 0.3,
        min_interval_seconds: float = DEFAULT_MIN_INTERVAL_SECONDS,
        max_retry_wait_seconds: float = DEFAULT_MAX_RETRY_WAIT_SECONDS,
        cache_ttl_seconds: float = DEFAULT_CACHE_TTL_SECONDS,
        cache_max_entries: int = DEFAULT_CACHE_MAX_ENTRIES,
        client: httpx.Client | None = None,
        sleep=time.sleep,
        monotonic=time.monotonic,
    ) -> None:
        self.base_url = base_url
        self.max_retries = max(1, max_retries)
        self.max_retry_wait_seconds = max_retry_wait_seconds
        self.backoff_base_seconds = max(0.0, backoff_base_seconds)
        self.backoff_max_seconds = max(0.0, backoff_max_seconds)
        self.jitter_ratio = min(max(0.0, jitter_ratio), 1.0)
        self.min_interval_seconds = max(0.0, min_interval_seconds)
        self._sleep = sleep
        self._monotonic = monotonic
        # Callers injecting a clock/sleep (tests) get their own pacer; the real
        # worker uses the process-wide one so concurrent clients share it.
        self._pacer = (
            _PROCESS_PACER
            if sleep is time.sleep and monotonic is time.monotonic
            else RequestPacer(monotonic=monotonic, sleep=sleep)
        )
        self.cache = ResponseCache(
            ttl_seconds=cache_ttl_seconds,
            max_entries=cache_max_entries,
            monotonic=monotonic,
        )
        self._client = client or httpx.Client(
            timeout=timeout,
            follow_redirects=False,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )

    # -- transport ---------------------------------------------------------
    def _delay(self, attempt: int) -> float:
        return backoff_delay(
            attempt,
            base_seconds=self.backoff_base_seconds,
            max_seconds=self.backoff_max_seconds,
            jitter_ratio=self.jitter_ratio,
        )

    def _throttle(self) -> None:
        self._pacer.wait(self.min_interval_seconds)

    def _execute(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
        *,
        operation: str,
        cache: bool = True,
        connection: str | None = None,
        sequence: str | None = None,
    ) -> dict[str, Any]:
        body = {"query": query, "variables": variables or {}}
        cache_key = _cache_key(query, variables)
        use_cache = cache and self.cache.enabled
        if use_cache:
            cached = self.cache.get(cache_key)
            if cached is not None:
                record_cache_event("justwatch", hit=True)
                return cached
            record_cache_event("justwatch", hit=False)
        for attempt in range(1, self.max_retries + 1):
            self._throttle()
            record_api_call("justwatch")
            try:
                response = self._client.post(self.base_url, json=body)
            except httpx.TimeoutException as exc:
                if attempt < self.max_retries:
                    self._sleep(self._delay(attempt))
                    continue
                raise JustWatchRequestError(f"Timeout JustWatch su {operation}.") from exc
            except httpx.HTTPError as exc:
                if attempt < self.max_retries:
                    self._sleep(self._delay(attempt))
                    continue
                raise JustWatchRequestError(f"Errore di rete JustWatch su {operation}.") from exc

            if response.status_code == 429:
                retry_after = _retry_after_seconds(response)
                if attempt < self.max_retries and retry_after <= self.max_retry_wait_seconds:
                    self._sleep(retry_after)
                    continue
                raise JustWatchRateLimitError(
                    f"JustWatch ha risposto 429 su {operation}.",
                    retry_after_seconds=retry_after,
                )
            if response.status_code in (401, 403):
                raise JustWatchAuthError(
                    f"JustWatch ha rifiutato la richiesta su {operation} "
                    f"(HTTP {response.status_code})."
                )
            if response.status_code >= 500:
                if attempt < self.max_retries:
                    self._sleep(self._delay(attempt))
                    continue
                raise JustWatchRequestError(
                    f"JustWatch ha risposto {response.status_code} su {operation}."
                )
            if response.status_code not in (200, 422):
                raise JustWatchRequestError(
                    f"JustWatch ha risposto {response.status_code} su {operation}."
                )
            try:
                payload = response.json()
            except ValueError as exc:
                raise JustWatchRequestError(
                    f"Risposta non JSON da JustWatch su {operation}."
                ) from exc
            errors = payload.get("errors") or []
            if errors:
                first = errors[0] if isinstance(errors[0], dict) else {}
                code = (first.get("extensions") or {}).get("code")
                message = str(first.get("message") or "errore GraphQL")
                raise JustWatchGraphQLError(f"JustWatch: {message} ({operation})", code=code)
            data = payload.get("data")
            if not isinstance(data, dict):
                raise JustWatchRequestError(f"Payload JustWatch inatteso su {operation}.")
            # Validate before caching: a drifted payload must never be served
            # from the cache for the rest of its TTL.
            if connection is not None:
                _validate_connection(data, connection, operation)
            if sequence is not None:
                _validate_sequence(data, sequence, operation)
            if use_cache:
                self.cache.set(cache_key, data)
            return data
        raise JustWatchRequestError(f"JustWatch: tentativi esauriti su {operation}.")

    # -- API ---------------------------------------------------------------
    def healthcheck(self) -> HealthStatus:
        """Probe the endpoint with a trivial query; never raises."""
        started = time.monotonic()
        try:
            self._execute(QUERY_HEALTHCHECK, None, operation="healthcheck", cache=False)
        except JustWatchError as exc:
            latency_ms = int((time.monotonic() - started) * 1000)
            return HealthStatus(ok=False, message=str(exc), latency_ms=latency_ms)
        latency_ms = int((time.monotonic() - started) * 1000)
        return HealthStatus(ok=True, message="JustWatch raggiungibile.", latency_ms=latency_ms)

    def list_packages(
        self, country: str, platform: str = DEFAULT_PLATFORM
    ) -> list[JustWatchPackage]:
        data = self._execute(
            QUERY_PACKAGES,
            {"country": country, "platform": platform},
            operation="packages",
            sequence="packages",
        )
        packages: list[JustWatchPackage] = []
        for row in data["packages"]:
            short_name = row.get("shortName")
            name = row.get("clearName")
            if not short_name or not name:
                continue
            packages.append(
                JustWatchPackage(
                    short_name=str(short_name),
                    name=str(name),
                    package_id=str(row["id"]) if row.get("id") is not None else None,
                    technical_name=row.get("technicalName"),
                    monetization_types=tuple(row.get("monetizationTypes") or ()),
                )
            )
        return packages

    def list_genres(self, language: str) -> list[dict[str, Any]]:
        data = self._execute(
            QUERY_GENRES, {"language": language}, operation="genres", sequence="genres"
        )
        return [row for row in data["genres"] if row.get("shortName")]

    def popular_titles(
        self,
        country: str,
        language: str,
        *,
        offset: int = 0,
        limit: int = MAX_PAGE_SIZE,
        packages: list[str] | None = None,
        object_type: MediaType | None = None,
        monetization_types: list[str] | None = None,
        genres: list[str] | None = None,
        subgenres: list[str] | None = None,
        release_year: tuple[int, int] | None = None,
        presentation_types: list[str] | None = None,
    ) -> JustWatchPage:
        return self._paged(
            QUERY_POPULAR_TITLES,
            "popularTitles",
            country,
            language,
            offset=offset,
            limit=limit,
            packages=packages,
            object_type=object_type,
            monetization_types=monetization_types,
            genres=genres,
            subgenres=subgenres,
            release_year=release_year,
            presentation_types=presentation_types,
            operation="popularTitles",
        )

    def search_titles(
        self,
        country: str,
        language: str,
        query: str,
        *,
        offset: int = 0,
        limit: int = MAX_PAGE_SIZE,
        source: str = "",
        object_type: MediaType | None = None,
    ) -> JustWatchPage:
        flt = _build_filter(packages=None, object_type=object_type, monetization_types=None) or {}
        flt["searchQuery"] = query
        return self._paged(
            QUERY_SEARCH_TITLES,
            "searchTitles",
            country,
            language,
            offset=offset,
            limit=limit,
            extra_variables={"source": source},
            explicit_filter=flt,
            operation="searchTitles",
        )

    def new_titles(
        self,
        country: str,
        language: str,
        page_type: str,
        *,
        offset: int = 0,
        limit: int = MAX_PAGE_SIZE,
        packages: list[str] | None = None,
        object_type: MediaType | None = None,
        monetization_types: list[str] | None = None,
    ) -> JustWatchPage:
        if page_type not in NEW_PAGE_TYPES:
            raise ValueError(
                f"pageType JustWatch non valido: {page_type!r} "
                f"(ammessi: {', '.join(sorted(NEW_PAGE_TYPES))})."
            )
        return self._paged(
            QUERY_NEW_TITLES,
            "newTitles",
            country,
            language,
            offset=offset,
            limit=limit,
            packages=packages,
            object_type=object_type,
            monetization_types=monetization_types,
            extra_variables={"pageType": page_type},
            operation=f"newTitles[{page_type}]",
        )

    def streaming_charts(
        self,
        country: str,
        language: str,
        *,
        after: str | None = None,
        limit: int = MAX_PAGE_SIZE,
        object_type: MediaType | None = None,
        packages: list[str] | None = None,
    ) -> JustWatchPage:
        """Fetch a streaming-chart page. The rank comes from ``streamingChartInfo``."""
        size = _clamp_page_size(limit)
        flt: dict[str, Any] = {}
        if object_type is not None:
            if object_type.value not in CHART_OBJECT_TYPES:
                raise ValueError(f"objectType non valido per le charts: {object_type.value!r}.")
            flt["objectType"] = object_type.value
        if packages:
            flt["packages"] = list(packages)
        data = self._execute(
            QUERY_STREAMING_CHARTS,
            {
                "country": country,
                "language": language,
                "first": size,
                "after": after,
                "filter": flt or None,
            },
            operation="streamingCharts",
            connection="streamingCharts",
        )
        connection = data["streamingCharts"]
        charts: list[JustWatchChartEntry] = []
        for edge in connection["edges"]:
            title = _parse_title(edge.get("node") or {})
            if title is None:
                continue
            info = edge.get("streamingChartInfo") or {}
            charts.append(
                JustWatchChartEntry(
                    title=title,
                    rank=_to_int(info.get("rank")),
                    trend=info.get("trend"),
                    trend_difference=_to_int(info.get("trendDifference")),
                    days_in_top10=_to_int(info.get("daysInTop10")),
                    top_rank=_to_int(info.get("topRank")),
                )
            )
        page_info = connection["pageInfo"]
        next_cursor = page_info.get("endCursor") if page_info.get("hasNextPage") else None
        return JustWatchPage(
            charts=tuple(charts),
            next_cursor=next_cursor,
            total_items=_to_int(connection.get("totalCount")),
            raw=connection,
        )

    def seasons(self, show_id: str, country: str, language: str) -> list[JustWatchSeason]:
        """Seasons of a show. Each season carries its own offers on the node."""
        data = self._execute(
            QUERY_SEASONS,
            {"showId": show_id, "country": country, "language": language},
            operation="seasons",
        )
        node = data.get("node") or {}
        seasons: list[JustWatchSeason] = []
        for row in node.get("seasons") or []:
            content = row.get("content") or {}
            if not row.get("id"):
                continue
            seasons.append(
                JustWatchSeason(
                    node_id=str(row["id"]),
                    title=str(content.get("title") or ""),
                    total_episode_count=_to_int(row.get("totalEpisodeCount")),
                    raw=row,
                )
            )
        return seasons

    def episodes(self, season_id: str, country: str, language: str) -> list[JustWatchEpisode]:
        """Episodes of a season, with per-episode offers."""
        data = self._execute(
            QUERY_EPISODES,
            {"seasonId": season_id, "country": country, "language": language},
            operation="episodes",
        )
        node = data.get("node") or {}
        episodes: list[JustWatchEpisode] = []
        for row in node.get("episodes") or []:
            content = row.get("content") or {}
            if not row.get("id"):
                continue
            episodes.append(
                JustWatchEpisode(
                    node_id=str(row["id"]),
                    title=str(content.get("title") or ""),
                    season_number=_to_int(content.get("seasonNumber")),
                    episode_number=_to_int(content.get("episodeNumber")),
                    offers=_parse_offers(row),
                    raw=row,
                )
            )
        return episodes

    # -- internals ---------------------------------------------------------
    def _paged(
        self,
        query: str,
        field: str,
        country: str,
        language: str,
        *,
        offset: int,
        limit: int,
        packages: list[str] | None = None,
        object_type: MediaType | None = None,
        monetization_types: list[str] | None = None,
        operation: str,
        genres: list[str] | None = None,
        subgenres: list[str] | None = None,
        release_year: tuple[int, int] | None = None,
        presentation_types: list[str] | None = None,
        extra_variables: dict[str, Any] | None = None,
        explicit_filter: dict[str, Any] | None = None,
    ) -> JustWatchPage:
        if offset >= MAX_REACHABLE_ITEMS:
            # The endpoint stops answering past item #1999 without an error.
            return JustWatchPage(titles=(), next_cursor=None, total_items=None, raw={})
        # Never ask for a page that would cross the reachable cap.
        size = _clamp_page_size(min(limit, MAX_REACHABLE_ITEMS - offset))
        variables: dict[str, Any] = {
            "country": country,
            "language": language,
            "first": size,
            "offset": offset,
            "filter": explicit_filter
            if explicit_filter is not None
            else _build_filter(
                packages=packages,
                object_type=object_type,
                monetization_types=monetization_types,
                genres=genres,
                subgenres=subgenres,
                release_year=release_year,
                presentation_types=presentation_types,
            ),
        }
        variables.update(extra_variables or {})
        data = self._execute(query, variables, operation=operation, connection=field)
        connection = data[field]
        parsed = (_parse_title(edge.get("node") or {}) for edge in connection["edges"])
        titles = tuple(title for title in parsed if title is not None)
        page_info = connection["pageInfo"]
        has_next = bool(page_info.get("hasNextPage")) and offset + len(titles) < MAX_REACHABLE_ITEMS
        return JustWatchPage(
            titles=titles,
            next_cursor=str(offset + len(titles)) if has_next else None,
            total_items=_to_int(connection.get("totalCount")),
            raw=connection,
        )

    def close(self) -> None:
        self._client.close()


def _clamp_page_size(limit: int) -> int:
    if limit < 1:
        raise ValueError("limit deve essere >= 1")
    return min(limit, MAX_PAGE_SIZE)


def _build_filter(
    *,
    packages: list[str] | None,
    object_type: MediaType | None,
    monetization_types: list[str] | None,
    genres: list[str] | None = None,
    subgenres: list[str] | None = None,
    release_year: tuple[int, int] | None = None,
    presentation_types: list[str] | None = None,
) -> dict[str, Any] | None:
    flt: dict[str, Any] = {}
    if packages:
        flt["packages"] = list(packages)
    if object_type is not None:
        flt["objectTypes"] = [object_type.value]
    if monetization_types:
        flt["monetizationTypes"] = [value.upper() for value in monetization_types]
    if genres:
        flt["genres"] = list(genres)
    if subgenres:
        flt["subgenres"] = list(subgenres)
    if presentation_types:
        # The endpoint spells 4K as ``_4K``.
        flt["presentationTypes"] = [
            "_4K" if value.upper() in ("4K", "_4K") else value.upper()
            for value in presentation_types
        ]
    if release_year is not None:
        lo, hi = release_year
        flt["releaseYear"] = {"min": int(lo), "max": int(hi)}
    return flt or None
