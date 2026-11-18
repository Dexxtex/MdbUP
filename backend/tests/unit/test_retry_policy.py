"""Retry backoff/jitter and write-throttle unit tests."""

from __future__ import annotations

import random

from app.services.sync import WriteThrottle, next_delay


def test_retry_after_has_precedence() -> None:
    assert next_delay(1, 12.5) == 12.5
    assert next_delay(5, 0.0) == 0.0


def test_backoff_grows_and_is_capped_with_jitter() -> None:
    rng = random.Random(7)
    delays = [next_delay(attempt, None, rng=rng) for attempt in range(1, 9)]
    # Jitter is applied after the cap, so the ceiling is 30 * 1.2.
    assert all(0 < delay <= 36 for delay in delays)
    assert delays[0] < delays[-1]


def test_write_throttle_waits_when_budget_is_exhausted() -> None:
    sleeps: list[float] = []
    throttle = WriteThrottle(capacity=10, window_seconds=300)
    throttle.acquire(10, sleep=sleeps.append)
    assert sleeps == []
    throttle.acquire(1, sleep=sleeps.append)
    assert len(sleeps) == 1
    assert sleeps[0] > 0
