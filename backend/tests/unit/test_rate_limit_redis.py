"""Persistent Redis rate limiting and lockout."""

from __future__ import annotations

import time
from typing import Any

from app.core.security import RateLimiter


class _FakePipeline:
    def __init__(self, store: dict[str, Any]) -> None:
        self.store = store
        self.ops: list[tuple[str, str]] = []

    def incr(self, key: str) -> None:
        self.ops.append(("incr", key))

    def ttl(self, key: str) -> None:
        self.ops.append(("ttl", key))

    def execute(self) -> list[Any]:
        values: list[Any] = []
        for op, key in self.ops:
            if op == "incr":
                self.store[key] = int(self.store.get(key, 0)) + 1
                values.append(self.store[key])
            else:
                values.append(self._ttl(key))
        return values

    def _ttl(self, key: str) -> int:
        expiry = self.store.get(f"{key}:expiry")
        if expiry is None:
            return -1
        remaining = int(float(expiry) - time.monotonic())
        return max(0, remaining)


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, Any] = {}

    def ttl(self, key: str) -> int:
        expiry = self.store.get(f"{key}:expiry")
        if expiry is None:
            return -2
        return max(0, int(float(expiry) - time.monotonic()))

    def pipeline(self) -> _FakePipeline:
        return _FakePipeline(self.store)

    def expire(self, key: str, seconds: int) -> None:
        self.store[f"{key}:expiry"] = time.monotonic() + seconds

    def set(self, key: str, value: str, *, ex: int | None = None, nx: bool = False) -> bool:
        if nx and key in self.store:
            return False
        self.store[key] = value
        if ex is not None:
            self.store[f"{key}:expiry"] = time.monotonic() + ex
        return True

    def delete(self, *keys: str) -> int:
        removed = 0
        for key in keys:
            if key in self.store:
                removed += 1
                self.store.pop(key, None)
        return removed


def test_rate_limit_is_shared_across_limiter_instances() -> None:
    redis = _FakeRedis()
    first = RateLimiter(client=redis)  # type: ignore[arg-type]
    second = RateLimiter(client=redis)  # type: ignore[arg-type]
    for _ in range(5):
        assert first.check("login:1.2.3.4:user@example.com", limit=5, window_seconds=60).allowed
    denied = second.check("login:1.2.3.4:user@example.com", limit=5, window_seconds=60)
    assert denied.allowed is False
    assert denied.retry_after_seconds > 0
    first.reset("login:1.2.3.4:user@example.com")
    assert second.check("login:1.2.3.4:user@example.com", limit=5, window_seconds=60).allowed


def test_lockout_survives_a_new_limiter_instance() -> None:
    redis = _FakeRedis()
    first = RateLimiter(client=redis)  # type: ignore[arg-type]
    for _ in range(5):
        first.check("login:key", limit=5, window_seconds=60, lockout_seconds=120)
    denied = first.check("login:key", limit=5, window_seconds=60, lockout_seconds=120)
    assert denied.allowed is False
    assert denied.retry_after_seconds >= 100
    second = RateLimiter(client=redis)  # type: ignore[arg-type]
    still_denied = second.check("login:key", limit=5, window_seconds=60, lockout_seconds=120)
    assert still_denied.allowed is False
    assert still_denied.retry_after_seconds >= 100
