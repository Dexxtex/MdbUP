"""Short-lived distributed locks for scheduling/dispatch decisions.

The sync executor already holds a PostgreSQL advisory lock for the whole run.
This lock is narrower: it serialises the *creation* of a run for a target so a
manual request and a Celery Beat tick cannot both pass the active-run check.
Redis is used when configured; the in-process fallback keeps tests and
single-process development working without a broker.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable

import redis

from app.core.logging import get_logger

logger = get_logger(__name__)

_MEMORY: dict[str, str] = {}
_MEMORY_GUARD = threading.Lock()

_RELEASE_LUA = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
end
return 0
"""


class DispatchLock:
    """Best-effort lock with TTL; never blocks indefinitely."""

    def __init__(
        self,
        redis_url: str = "",
        *,
        namespace: str = "mdbup:dispatch",
        ttl_seconds: int = 120,
    ) -> None:
        self._redis_url = redis_url
        self._namespace = namespace
        self._ttl_seconds = max(1, ttl_seconds)
        self._client: redis.Redis | None = None
        self._redis_unavailable = False

    def _redis_client(self) -> redis.Redis | None:
        if self._redis_unavailable or not self._redis_url:
            return None
        if self._client is None:
            self._client = redis.Redis.from_url(
                self._redis_url,
                socket_timeout=0.5,
                socket_connect_timeout=0.5,
                decode_responses=True,
            )
        return self._client

    def acquire(self, key: str) -> str | None:
        """Return a release token, or ``None`` when another owner holds the lock."""
        token = uuid.uuid4().hex
        client = self._redis_client()
        if client is not None:
            try:
                acquired = bool(
                    client.set(
                        f"{self._namespace}:{key}",
                        token,
                        nx=True,
                        ex=self._ttl_seconds,
                    )
                )
                return token if acquired else None
            except redis.RedisError as exc:
                self._redis_unavailable = True
                logger.warning("dispatch_lock_redis_unavailable", error=str(exc))
        with _MEMORY_GUARD:
            if key in _MEMORY:
                return None
            _MEMORY[key] = token
            return token

    def release(self, key: str, token: str) -> None:
        client = self._redis_client()
        if client is not None:
            try:
                client.eval(
                    _RELEASE_LUA,
                    1,
                    f"{self._namespace}:{key}",
                    token,
                )
                return
            except redis.RedisError as exc:
                self._redis_unavailable = True
                logger.warning("dispatch_lock_release_failed", error=str(exc))
        with _MEMORY_GUARD:
            if _MEMORY.get(key) == token:
                _MEMORY.pop(key, None)


def build_dispatch_lock(redis_url: str) -> DispatchLock:
    return DispatchLock(redis_url)


def sweep_orphan_dispatch_locks(
    redis_url: str,
    *,
    is_active: Callable[[str], bool],
    namespace: str = "mdbup:dispatch",
    client: redis.Redis | None = None,
) -> int:
    """Delete dispatch locks whose target no longer has an active run.

    Locks already have a TTL, but a container killed between ``acquire`` and
    ``release`` can leave a lock for up to two minutes. The maintenance sweep
    removes it immediately once the database says there is no active run.
    """
    if client is None:
        if not redis_url:
            return 0
        client = redis.Redis.from_url(
            redis_url,
            socket_timeout=1.0,
            socket_connect_timeout=1.0,
            decode_responses=True,
        )
    removed = 0
    try:
        for key in client.scan_iter(match=f"{namespace}:target:*", count=100):
            raw = str(key)
            target_id = raw.rsplit(":", 1)[-1]
            try:
                active = is_active(target_id)
            except Exception:  # pragma: no cover - defensive boundary
                active = True
            if not active:
                removed += int(client.delete(key) or 0)
    except redis.RedisError as exc:
        logger.warning("orphan_lock_sweep_failed", error=type(exc).__name__)
        return removed
    return removed
