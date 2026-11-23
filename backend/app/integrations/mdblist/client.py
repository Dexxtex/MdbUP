"""Synchronous MDBList API client (API key in the ``apikey`` query parameter).

Only endpoints verified in the phase-1 project spec are used. Reads may
retry once on a short ``429``; writes never retry blindly because a timeout or a
5xx after the request was sent leaves the remote outcome unknown. The caller
records ``UNCERTAIN`` and reconciles by reading the list.

The API key is never logged and redirects are never followed.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable, Iterator, Sequence
from typing import Any

import httpx

from app.core.metrics import record_api_call
from app.core.retry import backoff_delay
from app.integrations.mdblist.models import (
    MdbListId,
    MdbListItemPage,
    MdbListList,
    MdbListListItem,
    MdbListMutationResult,
    MdbListReorderResult,
    MdbListUser,
    normalize_media_type,
)

DEFAULT_BASE_URL = "https://api.mdblist.com"
DEFAULT_TIMEOUT_SECONDS = 20.0
DEFAULT_MAX_RETRY_WAIT_SECONDS = 5.0
DEFAULT_PAGE_LIMIT = 100
MAX_PAGE_LIMIT = 1000
MAX_REORDER_ITEMS = 1000


class MdbListError(RuntimeError):
    """Base class for MDBList transport and protocol errors."""


class MdbListAuthError(MdbListError):
    """The API key was missing or rejected (401)."""


class MdbListPermissionError(MdbListError):
    """The account cannot write this list (403): a permanent block, never a retry."""


class MdbListNotFoundError(MdbListError):
    """The list does not exist (404). Never recreate it automatically."""


class MdbListRateLimitError(MdbListError):
    """MDBList answered 429; ``retry_after_seconds`` comes from ``Retry-After``."""

    def __init__(self, message: str, *, retry_after_seconds: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class MdbListServerError(MdbListError):
    """A 5xx answer: the request may or may not have been applied."""


class MdbListTimeout(MdbListError):
    """A timeout after the request may have been sent: the outcome is uncertain."""


class MdbListRequestError(MdbListError):
    """A permanent request error (400/422 or a connection that never opened)."""


class MdbListSchemaError(MdbListError):
    """The payload does not match the documented shape."""


def retry_after_seconds(response: httpx.Response) -> float | None:
    """Parse ``Retry-After`` (seconds); ``None`` when absent or malformed."""
    raw = response.headers.get("retry-after")
    if raw is None:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        return None


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _str_or_none(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _counts(payload: Any) -> dict[str, int]:
    if not isinstance(payload, dict):
        return {}
    return {str(key): int(value) for key, value in payload.items() if isinstance(value, int)}


def _parse_item(entry: Any, mediatype: str) -> MdbListListItem | None:
    if not isinstance(entry, dict):
        return None
    ids_raw = entry.get("ids")
    ids: dict[str, Any] = ids_raw if isinstance(ids_raw, dict) else {}
    imdb_id = _str_or_none(ids.get("imdb")) or _str_or_none(entry.get("imdb_id"))
    mdblist_id = ids.get("mdblist")
    return MdbListListItem(
        mediatype=mediatype,
        tmdb_id=_int_or_none(ids.get("tmdb")),
        imdb_id=imdb_id,
        tvdb_id=_int_or_none(ids.get("tvdb")),
        trakt_id=_int_or_none(ids.get("trakt")),
        mdblist_id=str(mdblist_id) if mdblist_id is not None else None,
        title=_str_or_none(entry.get("title")) or _str_or_none(entry.get("name")),
        release_year=_int_or_none(entry.get("release_year")),
        rank=_int_or_none(entry.get("rank")),
        raw=entry,
    )


def _parse_list(entry: Any) -> MdbListList | None:
    if not isinstance(entry, dict):
        return None
    list_id = _int_or_none(entry.get("id"))
    if list_id is None:
        return None
    name = _str_or_none(entry.get("name")) or f"Lista {list_id}"
    return MdbListList(
        id=list_id,
        name=name,
        slug=_str_or_none(entry.get("slug")),
        private=bool(entry.get("private")),
        mediatype=normalize_media_type(entry.get("mediatype")),
        user_id=_int_or_none(entry.get("user_id")),
        user_name=_str_or_none(entry.get("user_name")),
        item_count=_int_or_none(entry.get("items")),
        likes=_int_or_none(entry.get("likes")),
        raw=entry,
    )


class MdbListClient:
    """Minimal MDBList client with documented endpoints and typed errors."""

    def __init__(
        self,
        api_key: str,
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
        if not api_key:
            raise ValueError("API key MDBList mancante.")
        self.base_url = base_url.rstrip("/")
        self.max_retry_wait_seconds = max_retry_wait_seconds
        self.max_retries = max(1, max_retries)
        self.backoff_base_seconds = max(0.0, backoff_base_seconds)
        self.backoff_max_seconds = max(0.0, backoff_max_seconds)
        self.jitter_ratio = min(max(0.0, jitter_ratio), 1.0)
        self._sleep = sleep
        self._rng = rng
        self._api_key = api_key
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=timeout, follow_redirects=False)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> MdbListClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def _delay(self, attempt: int) -> float:
        return backoff_delay(
            attempt,
            base_seconds=self.backoff_base_seconds,
            max_seconds=self.backoff_max_seconds,
            jitter_ratio=self.jitter_ratio,
            rng=self._rng,
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        retry_429: bool = False,
        retry_transient: bool = False,
    ) -> httpx.Response:
        query = dict(params or {})
        query["apikey"] = self._api_key
        url = f"{self.base_url}{path}"
        attempts = self.max_retries if (retry_429 or retry_transient) else 1
        for attempt in range(1, attempts + 1):
            record_api_call("mdblist")
            try:
                response = self._client.request(
                    method,
                    url,
                    params=query,
                    json=json_body,
                    headers={"Accept": "application/json"},
                )
            except httpx.TimeoutException as exc:
                if retry_transient and attempt < attempts:
                    self._sleep(self._delay(attempt))
                    continue
                raise MdbListTimeout(f"Timeout MDBList su {path}.") from exc
            except httpx.ConnectError as exc:
                if retry_transient and attempt < attempts:
                    self._sleep(self._delay(attempt))
                    continue
                raise MdbListRequestError(f"Connessione MDBList fallita su {path}.") from exc
            except httpx.HTTPError as exc:
                if retry_transient and attempt < attempts:
                    self._sleep(self._delay(attempt))
                    continue
                raise MdbListRequestError(f"Errore di rete MDBList su {path}.") from exc
            if response.status_code == 429:
                wait = retry_after_seconds(response)
                if (
                    retry_429
                    and attempt < attempts
                    and wait is not None
                    and wait <= self.max_retry_wait_seconds
                ):
                    self._sleep(wait)
                    continue
                raise MdbListRateLimitError(
                    f"MDBList rate limit su {path}.", retry_after_seconds=wait
                )
            if response.status_code in (401,):
                raise MdbListAuthError(f"MDBList ha rifiutato la API key su {path}.")
            if response.status_code == 403:
                raise MdbListPermissionError(f"MDBList ha negato l'accesso a {path}.")
            if response.status_code == 404:
                raise MdbListNotFoundError(f"Risorsa MDBList non trovata: {path}.")
            if response.status_code >= 500:
                if retry_transient and attempt < attempts:
                    self._sleep(self._delay(attempt))
                    continue
                raise MdbListServerError(f"MDBList ha risposto {response.status_code} su {path}.")
            if response.status_code >= 400:
                raise MdbListRequestError(f"MDBList ha risposto {response.status_code} su {path}.")
            return response
        raise MdbListRateLimitError(  # pragma: no cover - loop always returns or raises
            f"MDBList rate limit su {path}."
        )

    @staticmethod
    def _json(response: httpx.Response, path: str) -> Any:
        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError as exc:
            raise MdbListSchemaError(f"Payload MDBList non JSON su {path}.") from exc

    def _json_dict(self, response: httpx.Response, path: str) -> dict[str, Any]:
        payload = self._json(response, path)
        if not isinstance(payload, dict):
            raise MdbListSchemaError(f"Payload MDBList inatteso su {path}.")
        return payload

    def get_user(self) -> MdbListUser:
        """Return the authenticated account (ownership check for targets)."""
        path = "/user"
        payload = self._json_dict(
            self._request("GET", path, retry_429=True, retry_transient=True), path
        )
        user_raw = payload.get("user")
        user: dict[str, Any] = user_raw if isinstance(user_raw, dict) else payload
        return MdbListUser(
            id=_int_or_none(user.get("id")),
            user_name=_str_or_none(user.get("user_name")) or _str_or_none(user.get("username")),
            raw=payload,
        )

    def get_list(self, list_id: int | str) -> MdbListList:
        path = f"/lists/{list_id}"
        payload = self._json(self._request("GET", path, retry_429=True, retry_transient=True), path)
        # The live API returns a one-element array; older mocks/docs use an object.
        if isinstance(payload, list):
            if not payload:
                raise MdbListSchemaError(f"Lista MDBList vuota su {path}.")
            payload = payload[0]
        if not isinstance(payload, dict):
            raise MdbListSchemaError(f"Payload MDBList inatteso su {path}.")
        parsed = _parse_list(payload)
        if parsed is None:
            raise MdbListSchemaError(f"Lista MDBList senza id su {path}.")
        return parsed

    def get_items(
        self,
        list_id: int | str,
        *,
        cursor: str | None = None,
        offset: int | None = None,
        limit: int = DEFAULT_PAGE_LIMIT,
        sort: str | None = None,
        order: str | None = None,
        extended: str | None = None,
    ) -> MdbListItemPage:
        """Read one page.

        The live API currently paginates with ``offset``/``limit`` and
        ``pagination.has_more``; older builds used an opaque ``next_cursor``.
        Both are supported. A numeric cursor is treated as an offset.
        """
        path = f"/lists/{list_id}/items"
        params: dict[str, Any] = {"limit": max(1, min(limit, MAX_PAGE_LIMIT))}
        if offset is not None:
            params["offset"] = max(0, offset)
        elif cursor:
            if cursor.isdigit():
                params["offset"] = int(cursor)
            else:
                params["cursor"] = cursor
        if sort:
            params["sort"] = sort
        if order:
            params["order"] = order
        if extended:
            params["extended"] = extended
        response = self._request("GET", path, params=params, retry_429=True, retry_transient=True)
        payload = self._json_dict(response, path)
        items: list[MdbListListItem] = []
        for key in ("movies", "shows", "seasons", "episodes"):
            mediatype = normalize_media_type(key[:-1])
            if mediatype is None:  # pragma: no cover - keys are fixed
                continue
            for entry in payload.get(key) or []:
                parsed = _parse_item(entry, mediatype)
                if parsed is not None:
                    items.append(parsed)
        pagination = payload.get("pagination")
        next_cursor = None
        pagination_has_more: bool | None = None
        if isinstance(pagination, dict):
            next_cursor = _str_or_none(pagination.get("next_cursor"))
            raw_pagination_has_more = pagination.get("has_more")
            if isinstance(raw_pagination_has_more, bool):
                pagination_has_more = raw_pagination_has_more
            if next_cursor is None and pagination_has_more:
                page_offset = _int_or_none(pagination.get("offset"))
                if page_offset is None:
                    page_offset = offset if offset is not None else 0
                page_limit = _int_or_none(pagination.get("limit")) or params["limit"]
                next_cursor = str(page_offset + page_limit)
        if next_cursor is None:
            next_cursor = _str_or_none(payload.get("next_cursor"))
        raw_has_more = response.headers.get("x-has-more")
        header_has_more = (
            raw_has_more.strip().lower() == "true" if raw_has_more is not None else None
        )
        has_more = (
            pagination_has_more
            if pagination_has_more is not None
            else (header_has_more if header_has_more is not None else next_cursor is not None)
        )
        if has_more and next_cursor is None:
            raise MdbListSchemaError(
                f"X-Has-More attivo senza next_cursor su {path}: lettura incompleta."
            )
        return MdbListItemPage(
            items=tuple(items),
            next_cursor=next_cursor,
            has_more=has_more,
            raw=payload,
        )

    def iter_items(
        self,
        list_id: int | str,
        *,
        limit: int = DEFAULT_PAGE_LIMIT,
        sort: str | None = None,
        order: str | None = None,
        extended: str | None = None,
        max_pages: int = 1000,
    ) -> Iterator[MdbListListItem]:
        """Yield every item, following ``next_cursor`` until it is absent."""
        cursor: str | None = None
        seen: set[str] = set()
        for _ in range(max_pages):
            page = self.get_items(
                list_id,
                cursor=cursor,
                limit=limit,
                sort=sort,
                order=order,
                extended=extended,
            )
            yield from page.items
            if not page.has_more or page.next_cursor is None:
                return
            if page.next_cursor in seen:
                raise MdbListSchemaError("Cursore MDBList ripetuto: lettura incompleta.")
            seen.add(page.next_cursor)
            cursor = page.next_cursor
        raise MdbListSchemaError(f"Limite di {max_pages} pagine MDBList raggiunto.")

    def create_list(self, name: str, *, private: bool = False) -> MdbListList:
        path = "/lists/user/add"
        response = self._request("POST", path, json_body={"name": name, "private": private})
        payload = self._json_dict(response, path)
        list_id = _int_or_none(payload.get("id"))
        if list_id is None:
            raise MdbListSchemaError(f"Lista creata senza id su {path}.")
        return MdbListList(
            id=list_id,
            name=_str_or_none(payload.get("name")) or name,
            slug=_str_or_none(payload.get("slug")),
            private=private,
            raw=payload,
        )

    def update_list(
        self,
        list_id: int | str,
        *,
        name: str | None = None,
        private: bool | None = None,
    ) -> MdbListList:
        """Update list metadata (``PUT /lists/{id}``); never touches items."""
        if name is None and private is None:
            raise ValueError("Nessun metadato da aggiornare.")
        path = f"/lists/{list_id}"
        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if private is not None:
            body["private"] = private
        payload = self._json_dict(self._request("PUT", path, json_body=body), path)
        parsed_id = _int_or_none(payload.get("id"))
        if parsed_id is None:
            raise MdbListSchemaError(f"Lista aggiornata senza id su {path}.")
        return MdbListList(
            id=parsed_id,
            name=_str_or_none(payload.get("name")) or name or "",
            private=bool(payload.get("private", private)),
            raw=payload,
        )

    def _mutate(
        self,
        list_id: int | str,
        action: str,
        *,
        movies: Sequence[MdbListId] = (),
        shows: Sequence[MdbListId] = (),
        seasons: Sequence[MdbListId] = (),
        episodes: Sequence[MdbListId] = (),
    ) -> MdbListMutationResult:
        if action not in ("add", "remove"):  # pragma: no cover - internal guard
            raise ValueError(f"Azione MDBList non valida: {action}")
        path = f"/lists/{list_id}/items/{action}"
        body: dict[str, Any] = {}
        for key, values in (
            ("movies", movies),
            ("shows", shows),
            ("seasons", seasons),
            ("episodes", episodes),
        ):
            if values:
                body[key] = [value.as_payload() for value in values]
        if not body:
            raise ValueError("Nessun elemento da inviare a MDBList.")
        payload = self._json_dict(
            self._request("POST", path, json_body=body, retry_429=False), path
        )
        return MdbListMutationResult(
            added=_counts(payload.get("added")),
            removed=_counts(payload.get("removed")),
            existing=_counts(payload.get("existing")),
            not_found=_counts(payload.get("not_found")),
            raw=payload,
        )

    def add_items(
        self,
        list_id: int | str,
        *,
        movies: Sequence[MdbListId] = (),
        shows: Sequence[MdbListId] = (),
        seasons: Sequence[MdbListId] = (),
        episodes: Sequence[MdbListId] = (),
    ) -> MdbListMutationResult:
        return self._mutate(
            list_id,
            "add",
            movies=movies,
            shows=shows,
            seasons=seasons,
            episodes=episodes,
        )

    def remove_items(
        self,
        list_id: int | str,
        *,
        movies: Sequence[MdbListId] = (),
        shows: Sequence[MdbListId] = (),
        seasons: Sequence[MdbListId] = (),
        episodes: Sequence[MdbListId] = (),
    ) -> MdbListMutationResult:
        return self._mutate(
            list_id,
            "remove",
            movies=movies,
            shows=shows,
            seasons=seasons,
            episodes=episodes,
        )

    def reorder(
        self,
        list_id: int | str,
        items: Sequence[tuple[str, MdbListId]],
        *,
        position: str | None = None,
        after: tuple[str, MdbListId] | None = None,
        before: tuple[str, MdbListId] | None = None,
    ) -> MdbListReorderResult:
        """Reorder up to 1.000 items. The caller chunks larger lists."""
        if not items:
            raise ValueError("Nessun elemento da riordinare.")
        if len(items) > MAX_REORDER_ITEMS:
            raise ValueError(f"MDBList accetta al massimo {MAX_REORDER_ITEMS} elementi.")
        path = f"/lists/{list_id}/items/reorder"
        body: dict[str, Any] = {
            "items": [
                {"mediatype": mediatype.lower(), "ids": ids.as_payload()}
                for mediatype, ids in items
            ]
        }
        if after is not None:
            body["after"] = {
                "mediatype": after[0].lower(),
                "ids": after[1].as_payload(),
            }
        elif before is not None:
            body["before"] = {
                "mediatype": before[0].lower(),
                "ids": before[1].as_payload(),
            }
        else:
            body["position"] = position or "top"
        payload = self._json_dict(
            self._request("POST", path, json_body=body, retry_429=False), path
        )
        return MdbListReorderResult(
            updated=_int_or_none(payload.get("updated")) or 0,
            not_found=_int_or_none(payload.get("not_found")) or 0,
            raw=payload,
        )
