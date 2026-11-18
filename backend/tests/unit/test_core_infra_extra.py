"""Locks and API counters: Redis fallback and orphan sweep."""

from __future__ import annotations

import redis

from app.core import locks, metrics


class FakePipeline:
    def __init__(self):
        self.values: list[str] = []

    def incr(self, key):
        self.values.append(f"incr:{key}")

    def expire(self, key, ttl):
        self.values.append(f"expire:{key}:{ttl}")

    def execute(self):
        self.values.append("execute")


class FakeRedis:
    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.deleted: list[object] = []

    def set(self, *args, **kwargs):
        if self.fail:
            raise redis.RedisError("down")
        return True

    def eval(self, *args, **kwargs):
        if self.fail:
            raise redis.RedisError("down")
        return 1

    def pipeline(self):
        if self.fail:
            raise redis.RedisError("down")
        return FakePipeline()

    def mget(self, *args):
        if self.fail:
            raise redis.RedisError("down")
        return [2, 3]

    def scan_iter(self, *args, **kwargs):
        if self.fail:
            raise redis.RedisError("down")
        return ["mdbup:dispatch:target:one", "mdbup:dispatch:target:bad"]

    def delete(self, *keys):
        self.deleted.extend(keys)
        return len(keys)


def test_dispatch_lock_memory_and_release_token() -> None:
    lock = locks.DispatchLock("", namespace="test")
    token = lock.acquire("target")
    assert token is not None
    assert lock.acquire("target") is None
    lock.release("target", "wrong")
    assert lock.acquire("target") is None
    lock.release("target", token)
    assert lock.acquire("target") is not None


def test_dispatch_lock_redis_failure_falls_back(monkeypatch) -> None:
    lock = locks.DispatchLock("redis://x")
    monkeypatch.setattr(lock, "_redis_client", lambda: FakeRedis(fail=True))
    token = lock.acquire("fallback")
    assert token is not None
    lock.release("fallback", token)
    assert lock.acquire("fallback") is not None


def test_sweep_orphan_dispatch_locks() -> None:
    fake = FakeRedis()
    removed = locks.sweep_orphan_dispatch_locks(
        "", is_active=lambda target: target == "one", client=fake
    )
    assert removed == 1
    assert locks.sweep_orphan_dispatch_locks("", is_active=lambda _: False, client=None) == 0


def test_api_counter_memory_and_redis(monkeypatch) -> None:
    counter = metrics.ApiCallCounter("")
    counter.record("tmdb")
    assert counter.snapshot("tmdb")["today"] == 1
    counter.reset()

    fake = FakeRedis()
    counter = metrics.ApiCallCounter("redis://x")
    monkeypatch.setattr(counter, "_redis_client", lambda: fake)
    counter.record("tmdb")
    assert counter.snapshot("tmdb") == {"hour": 2, "today": 3}
    counter.reset()

    broken = metrics.ApiCallCounter("redis://x")
    monkeypatch.setattr(broken, "_redis_client", lambda: FakeRedis(fail=True))
    broken.record("tmdb")
    assert broken.snapshot("tmdb")["today"] == 1
    broken.reset()


def test_api_usage_snapshot_and_reset(monkeypatch) -> None:
    counter = metrics.ApiCallCounter("")
    counter.record("justwatch")
    counter.record("justwatch_cache_hit")
    counter.record("justwatch_cache_miss")
    monkeypatch.setattr(metrics, "get_counter", lambda: counter)
    usage = metrics.api_usage_snapshot()
    assert usage["justwatch"]["today"] == 1
    assert usage["justwatch"]["cache_hits"] == 1
    metrics.reset_api_usage()


def test_dispatch_lock_redis_success(monkeypatch) -> None:
    fake = FakeRedis()
    lock = locks.DispatchLock("redis://x", namespace="test")
    monkeypatch.setattr(locks.redis.Redis, "from_url", lambda *a, **k: fake)
    token = lock.acquire("key")
    assert token is not None
    lock.release("key", token)


def test_orphan_sweep_redis_error() -> None:
    class Broken:
        def scan_iter(self, *args, **kwargs):
            raise redis.RedisError("down")

    assert locks.sweep_orphan_dispatch_locks("", is_active=lambda _: False, client=Broken()) == 0


def test_api_counter_constructor_uses_redis(monkeypatch) -> None:
    fake = FakeRedis()
    monkeypatch.setattr(metrics.redis.Redis, "from_url", lambda *a, **k: fake)
    counter = metrics.ApiCallCounter("redis://x")
    counter.record("tmdb")
    assert counter.snapshot("tmdb") == {"hour": 2, "today": 3}
    counter.reset()


def test_backoff_delay_branches() -> None:
    from app.core import retry

    assert retry.backoff_delay(1, base_seconds=0, max_seconds=10) == 0
    assert retry.backoff_delay(2, base_seconds=1, max_seconds=10, jitter_ratio=0) == 2
    assert 0 < retry.backoff_delay(1, base_seconds=1, max_seconds=10, jitter_ratio=0.5) <= 1.5
    try:
        retry.backoff_delay(0, base_seconds=1, max_seconds=10)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")
