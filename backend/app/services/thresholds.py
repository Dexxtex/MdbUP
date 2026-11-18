"""Safety thresholds for removals and additions.

Thresholds are evaluated against the *remote* list size, except when the remote
list is empty: in that case the addition ratio is 1.0 (the whole snapshot would
be added), which still requires approval under the default policy. The dry-run
always shows the plan and the breached threshold; it never applies anything.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.db.models import SyncBinding


@dataclass(frozen=True)
class ThresholdPolicy:
    max_removal_absolute: int = 50
    max_removal_percent: float = 10.0
    max_addition_percent: float = 50.0
    require_manual_review: bool = True
    auto_apply_max_removals: int = 5
    auto_apply_max_removal_ratio: float = 2.0

    @classmethod
    def from_binding(cls, binding: SyncBinding) -> ThresholdPolicy:
        return cls(
            max_removal_absolute=int(binding.max_removal_absolute),
            max_removal_percent=float(binding.max_removal_percent),
            max_addition_percent=float(binding.max_addition_percent),
            require_manual_review=bool(binding.require_manual_review),
            auto_apply_max_removals=int(binding.auto_apply_max_removals),
            auto_apply_max_removal_ratio=float(binding.auto_apply_max_removal_ratio),
        )


@dataclass(frozen=True)
class ThresholdResult:
    breached: bool
    reasons: tuple[str, ...]
    removal_ratio: float
    addition_ratio: float
    observed_removals: int
    observed_additions: int
    remote_count: int
    max_removal_absolute: int
    max_removal_percent: float
    max_addition_percent: float
    require_manual_review: bool

    @property
    def primary_reason(self) -> str | None:
        return self.reasons[0] if self.reasons else None


def evaluate_thresholds(
    *,
    to_add_count: int,
    to_remove_count: int,
    remote_count: int,
    policy: ThresholdPolicy,
) -> ThresholdResult:
    """Evaluate absolute and percentage limits for one plan."""
    if remote_count == 0:
        addition_ratio = 1.0 if to_add_count else 0.0
    else:
        addition_ratio = to_add_count / remote_count
    removal_ratio = to_remove_count / max(remote_count, 1)

    reasons: list[str] = []
    if to_remove_count > policy.max_removal_absolute:
        reasons.append("REMOVAL_ABSOLUTE_EXCEEDED")
    if removal_ratio > policy.max_removal_percent / 100:
        reasons.append("REMOVAL_PERCENT_EXCEEDED")
    if addition_ratio > policy.max_addition_percent / 100:
        reasons.append("ADDITION_PERCENT_EXCEEDED")

    return ThresholdResult(
        breached=bool(reasons),
        reasons=tuple(reasons),
        removal_ratio=removal_ratio,
        addition_ratio=addition_ratio,
        observed_removals=to_remove_count,
        observed_additions=to_add_count,
        remote_count=remote_count,
        max_removal_absolute=policy.max_removal_absolute,
        max_removal_percent=policy.max_removal_percent,
        max_addition_percent=policy.max_addition_percent,
        require_manual_review=policy.require_manual_review,
    )


def auto_apply_allowed(
    *,
    to_remove_count: int,
    removal_ratio: float,
    policy: ThresholdPolicy,
) -> bool:
    """``AUTO_APPLY_IF_SAFE`` only applies small removals without review."""
    return (
        to_remove_count <= policy.auto_apply_max_removals
        and removal_ratio * 100 <= policy.auto_apply_max_removal_ratio
    )


def threshold_summary(result: ThresholdResult) -> dict[str, object]:
    """JSON-safe view persisted in ``sync_run.summary`` and shown in the UI."""
    return {
        "breached": result.breached,
        "reasons": list(result.reasons),
        "removal_ratio": round(result.removal_ratio, 6),
        "addition_ratio": round(result.addition_ratio, 6),
        "observed_removals": result.observed_removals,
        "observed_additions": result.observed_additions,
        "remote_count": result.remote_count,
        "max_removal_absolute": result.max_removal_absolute,
        "max_removal_percent": result.max_removal_percent,
        "max_addition_percent": result.max_addition_percent,
    }
