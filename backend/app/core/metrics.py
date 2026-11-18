"""Lightweight outbound API call counters (Redis with in-memory fallback)."""

from __future__ import annotations

import threading
from datetime import UTC, datetime

import redis

from app.core.logging import get_logger

logger = get_logger(__name__)


class ApiCallCounter:
    def __init__(self, redis_url: str = "", *, namespace: str = "mdbup:api_calls") -> None:
        self._redis_url = redis_url
        self._namespace = namespace
        self._client: redis.Redis | None = None
        self._redis_unavailable = False
        self._memory: dict[str, int] = {}
        self._guard = threading.Lock()

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

    @staticmethod
    def _keys(provider: str, now: datetime) -> tuple[str, str]:
        return (
            f"{provider}:hour:{now:%Y%m%d%H}",
            f"{provider}:day:{now:%Y%m%d}",
        )

    def record(self, provider: str) -> None:
        now = datetime.now(UTC)
        hour_key, day_key = self._keys(provider, now)
        client = self._redis_client()
        if client is not None:
            try:
                pipeline = client.pipeline()
                pipeline.incr(f"{self._namespace}:{hour_key}")
                pipeline.expire(f"{self._namespace}:{hour_key}", 7200)
                pipeline.incr(f"{self._namespace}:{day_key}")
                pipeline.expire(f"{self._namespace}:{day_key}", 172800)
                pipeline.execute()
                return
            except redis.RedisError as exc:
                self._redis_unavailable = True
                logger.warning("api_counter_redis_unavailable", error=str(exc))
        with self._guard:
            self._memory[hour_key] = self._memory.get(hour_key, 0) + 1
            self._memory[day_key] = self._memory.get(day_key, 0) + 1

    def snapshot(self, provider: str) -> dict[str, int]:
        now = datetime.now(UTC)
        hour_key, day_key = self._keys(provider, now)
        client = self._redis_client()
        if client is not None:
            try:
                hour, day = client.mget(
                    f"{self._namespace}:{hour_key}",
                    f"{self._namespace}:{day_key}",
                )
                return {"hour": int(hour or 0), "today": int(day or 0)}
            except redis.RedisError as exc:
                self._redis_unavailable = True
                logger.warning("api_counter_read_failed", error=str(exc))
        with self._guard:
            return {
                "hour": self._memory.get(hour_key, 0),
                "today": self._memory.get(day_key, 0),
            }

    def reset(self) -> None:
        with self._guard:
            self._memory.clear()
        client = self._redis_client()
        if client is not None:
            try:
                keys = list(client.scan_iter(f"{self._namespace}:*"))
                if keys:
                    client.delete(*keys)
            except redis.RedisError:
                self._redis_unavailable = True


_counter: ApiCallCounter | None = None
_counter_guard = threading.Lock()


def get_counter() -> ApiCallCounter:
    global _counter
    with _counter_guard:
        if _counter is None:
            import os

            _counter = ApiCallCounter(os.environ.get("REDIS_URL", ""))
        return _counter


def record_api_call(provider: str) -> None:
    get_counter().record(provider)


def api_usage_snapshot() -> dict[str, dict[str, int]]:
    counter = get_counter()
    return {
        "tmdb": counter.snapshot("tmdb"),
        "mdblist": counter.snapshot("mdblist"),
    }


def reset_api_usage() -> None:
    global _counter
    with _counter_guard:
        if _counter is not None:
            _counter.reset()
        _counter = None
