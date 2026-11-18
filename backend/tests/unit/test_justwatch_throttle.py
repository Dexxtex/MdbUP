"""JustWatch throttle: one request per second across client instances."""

from __future__ import annotations

import pytest

from app.integrations.justwatch import client as client_module
from app.integrations.justwatch.client import JustWatchClient, RequestPacer

BASE = "https://apis.justwatch.com/graphql"


class _FakeClock:
    """Monotonic clock advanced by the fake sleep, so no test waits for real."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def test_pacer_enforces_the_interval_between_calls() -> None:
    clock = _FakeClock()
    pacer = RequestPacer(monotonic=clock.monotonic, sleep=clock.sleep)

    pacer.wait(1.0)
    clock.now = 0.25
    pacer.wait(1.0)

    assert clock.sleeps == [pytest.approx(0.75)]


def test_pacer_ignores_a_zero_interval() -> None:
    clock = _FakeClock()
    pacer = RequestPacer(monotonic=clock.monotonic, sleep=clock.sleep)

    pacer.wait(0.0)
    pacer.wait(0.0)

    assert clock.sleeps == []


def test_two_clients_share_the_process_pacer(monkeypatch) -> None:
    """Two worker tasks build their own client; the interval must be process-wide."""
    clock = _FakeClock()
    shared = RequestPacer(monotonic=clock.monotonic, sleep=clock.sleep)
    monkeypatch.setattr(client_module, "_PROCESS_PACER", shared)
    first = JustWatchClient(BASE, min_interval_seconds=1.0)
    second = JustWatchClient(BASE, min_interval_seconds=1.0)

    first._throttle()
    clock.now = 0.4
    second._throttle()

    assert clock.sleeps == [pytest.approx(0.6)]


def test_injected_clock_keeps_a_private_pacer(monkeypatch) -> None:
    """Tests that inject a clock never touch the process-wide pacer."""
    monkeypatch.setattr(client_module, "_PROCESS_PACER", RequestPacer())
    client = JustWatchClient(
        BASE, min_interval_seconds=1.0, sleep=lambda _s: None, monotonic=lambda: 0.0
    )

    assert client._pacer is not client_module._PROCESS_PACER
