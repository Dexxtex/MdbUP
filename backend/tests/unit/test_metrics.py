"""Outbound API counter (in-memory fallback in tests)."""

from __future__ import annotations

from app.core.metrics import api_usage_snapshot, record_api_call, reset_api_usage


def test_api_usage_counter_records_and_resets() -> None:
    reset_api_usage()
    record_api_call("tmdb")
    record_api_call("tmdb")
    record_api_call("mdblist")
    usage = api_usage_snapshot()
    assert usage["tmdb"]["hour"] == 2
    assert usage["tmdb"]["today"] == 2
    assert usage["mdblist"]["hour"] == 1
    reset_api_usage()
    assert api_usage_snapshot()["tmdb"]["today"] == 0
