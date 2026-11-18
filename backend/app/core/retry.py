"""Bounded exponential backoff with jitter for outbound HTTP clients."""

from __future__ import annotations

import random


def backoff_delay(
    attempt: int,
    *,
    base_seconds: float,
    max_seconds: float,
    jitter_ratio: float = 0.0,
    rng: random.Random | None = None,
) -> float:
    """Delay before retry ``attempt`` (1-based), capped and optionally jittered."""
    if attempt < 1:
        raise ValueError("attempt deve essere >= 1")
    base = min(max(0.0, base_seconds) * (2 ** (attempt - 1)), max(0.0, max_seconds))
    if base <= 0 or jitter_ratio <= 0:
        return base
    ratio = min(max(0.0, jitter_ratio), 1.0)
    source = rng or random
    return base * source.uniform(1.0 - ratio, 1.0 + ratio)
