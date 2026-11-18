"""Planner and threshold unit tests (no DB, no network)."""

from __future__ import annotations

import uuid

import pytest

from app.db.models import CollectionSnapshot, SyncBinding
from app.integrations.mdblist.models import MdbListListItem
from app.services.planning import (
    MediaKey,
    SourceItem,
    build_media_key,
    plan_sync,
    reorder_chunks,
    snapshot_hash_for,
)
from app.services.thresholds import (
    ThresholdPolicy,
    auto_apply_allowed,
    evaluate_thresholds,
)


def _binding(**overrides: object) -> SyncBinding:
    values: dict[str, object] = {
        "collection_id": uuid.uuid4(),
        "target_id": uuid.uuid4(),
        "media_type": "MOVIE",
        "mode": "MIRROR",
        "schedule_cron": "",
        "timezone": "Europe/Rome",
        "is_enabled": False,
        "max_removal_absolute": 50,
        "max_removal_percent": 10.0,
        "max_addition_percent": 50.0,
        "preserve_order": False,
        "reorder_enabled": True,
        "require_manual_review": True,
        "schedule_policy": "AUTO_APPLY_IF_SAFE",
        "auto_apply_max_removals": 5,
        "auto_apply_max_removal_ratio": 2.0,
        "max_plan_age_minutes": 60,
    }
    values.update(overrides)
    return SyncBinding(**values)  # type: ignore[arg-type]


def _snapshot(**overrides: object) -> CollectionSnapshot:
    values: dict[str, object] = {
        "collection_id": uuid.uuid4(),
        "status": "COMPLETE",
        "quality": "CLEAN",
        "is_valid": True,
        "items_count": 2,
        "resolved_count": 2,
        "unresolved_count": 0,
        "duplicate_count": 0,
        "error_count": 0,
    }
    values.update(overrides)
    return CollectionSnapshot(**values)  # type: ignore[arg-type]


def _source(tmdb_id: int, media_type: str = "MOVIE") -> SourceItem:
    return SourceItem(
        media_type=media_type,
        tmdb_id=tmdb_id,
        imdb_id=None,
        media_id=uuid.uuid4(),
        resolution_status="RESOLVED",
    )


def _remote(tmdb_id: int, media_type: str = "MOVIE") -> MdbListListItem:
    return MdbListListItem(mediatype=media_type, tmdb_id=tmdb_id, title=f"T{tmdb_id}")


def test_media_key_prefers_tmdb_and_keeps_media_type() -> None:
    assert build_media_key("MOVIE", 603, "tt0133093") == MediaKey("MOVIE", "tmdb", "603")
    assert build_media_key("SHOW", None, "tt0417299") == MediaKey("SHOW", "imdb", "tt0417299")
    assert build_media_key("MOVIE", None, None) is None
    # The same numeric id for a movie and a show is two different keys.
    assert build_media_key("MOVIE", 10, None) != build_media_key("SHOW", 10, None)


def test_mirror_plan_adds_and_removes() -> None:
    plan = plan_sync(
        mode="MIRROR",
        snapshot=_snapshot(),
        source_items=[_source(1), _source(2)],
        remote_items=[_remote(2), _remote(3)],
        binding=_binding(),
        policy_version="v1",
    )
    assert [key.value for key in plan.to_add] == ["1"]
    assert [key.value for key in plan.to_remove] == ["3"]
    assert [key.value for key in plan.unchanged] == ["2"]
    assert plan.blocked is False
    assert plan.plan_hash


def test_append_only_never_removes() -> None:
    plan = plan_sync(
        mode="APPEND_ONLY",
        snapshot=_snapshot(),
        source_items=[_source(1)],
        remote_items=[_remote(2), _remote(3)],
        binding=_binding(mode="APPEND_ONLY"),
        policy_version="v1",
    )
    assert [key.value for key in plan.to_add] == ["1"]
    assert plan.to_remove == ()
    assert plan.blocked is False


def test_unresolved_source_items_are_skipped_and_block_mirror() -> None:
    unresolved = SourceItem(
        media_type="MOVIE",
        tmdb_id=None,
        imdb_id=None,
        media_id=None,
        resolution_status="UNRESOLVED",
    )
    snapshot = _snapshot(unresolved_count=1, is_valid=False, quality="WARNINGS")
    mirror = plan_sync(
        mode="MIRROR",
        snapshot=snapshot,
        source_items=[_source(1), unresolved],
        remote_items=[],
        binding=_binding(),
        policy_version="v1",
    )
    assert mirror.blocked is True
    assert mirror.block_reason == "SNAPSHOT_NOT_VALID_FOR_MIRROR"
    assert len(mirror.unresolved) == 1

    append = plan_sync(
        mode="APPEND_ONLY",
        snapshot=snapshot,
        source_items=[_source(1), unresolved],
        remote_items=[],
        binding=_binding(mode="APPEND_ONLY"),
        policy_version="v1",
    )
    assert append.blocked is False
    assert [key.value for key in append.to_add] == ["1"]
    assert "UNRESOLVED_ITEMS_SKIPPED" in append.warnings


def test_empty_and_incomplete_snapshots_are_blocked() -> None:
    empty = plan_sync(
        mode="MIRROR",
        snapshot=_snapshot(items_count=0, is_valid=False, quality="ANOMALY"),
        source_items=[],
        remote_items=[_remote(1)],
        binding=_binding(),
        policy_version="v1",
    )
    assert empty.blocked is True
    assert empty.block_reason == "SNAPSHOT_EMPTY"

    incomplete = plan_sync(
        mode="APPEND_ONLY",
        snapshot=_snapshot(status="INCOMPLETE", is_valid=False, quality="ANOMALY"),
        source_items=[_source(1)],
        remote_items=[],
        binding=_binding(mode="APPEND_ONLY"),
        policy_version="v1",
    )
    assert incomplete.blocked is True
    assert incomplete.block_reason == "SNAPSHOT_INCOMPLETE"


def test_remote_duplicates_and_unmapped_remote_are_reported_not_removed() -> None:
    plan = plan_sync(
        mode="MIRROR",
        snapshot=_snapshot(items_count=1),
        source_items=[_source(1)],
        remote_items=[
            _remote(2),
            _remote(2),
            MdbListListItem(mediatype="MOVIE", tmdb_id=None, imdb_id=None, title="?"),
        ],
        binding=_binding(),
        policy_version="v1",
    )
    assert [key.value for key in plan.remote_duplicates] == ["2"]
    assert len(plan.unmapped_remote) == 1
    # The duplicate key is removed once, not twice.
    assert [key.value for key in plan.to_remove] == ["2"]
    assert "REMOTE_DUPLICATES" in plan.warnings
    assert "UNMAPPED_REMOTE_ITEMS" in plan.warnings


def test_suppressed_media_is_not_planned() -> None:
    suppressed = SourceItem(
        media_type="MOVIE",
        tmdb_id=9,
        imdb_id=None,
        media_id=uuid.uuid4(),
        suppressed=True,
    )
    plan = plan_sync(
        mode="MIRROR",
        snapshot=_snapshot(items_count=1),
        source_items=[_source(1), suppressed],
        remote_items=[],
        binding=_binding(),
        policy_version="v1",
    )
    assert [key.value for key in plan.to_add] == ["1"]
    assert [key.value for key in plan.suppressed] == ["9"]
    assert "SUPPRESSED_MEDIA_SKIPPED" in plan.warnings


def test_plan_hash_is_stable_and_sensitive_to_mode() -> None:
    args = {
        "snapshot": _snapshot(),
        "source_items": [_source(1)],
        "remote_items": [],
        "binding": _binding(),
        "policy_version": "v1",
    }
    first = plan_sync(mode="MIRROR", **args)
    second = plan_sync(mode="MIRROR", **args)
    append = plan_sync(mode="APPEND_ONLY", **args)
    assert first.plan_hash == second.plan_hash
    assert first.plan_hash != append.plan_hash


def test_snapshot_hash_ignores_order() -> None:
    keys = [MediaKey("MOVIE", "tmdb", "1"), MediaKey("MOVIE", "tmdb", "2")]
    assert snapshot_hash_for(keys) == snapshot_hash_for(list(reversed(keys)))


def test_thresholds_absolute_percent_and_addition() -> None:
    policy = ThresholdPolicy(
        max_removal_absolute=5,
        max_removal_percent=10,
        max_addition_percent=50,
    )
    absolute = evaluate_thresholds(
        to_add_count=0, to_remove_count=6, remote_count=100, policy=policy
    )
    assert absolute.breached is True
    assert "REMOVAL_ABSOLUTE_EXCEEDED" in absolute.reasons

    percent = evaluate_thresholds(
        to_add_count=0, to_remove_count=11, remote_count=100, policy=policy
    )
    assert "REMOVAL_PERCENT_EXCEEDED" in percent.reasons

    addition = evaluate_thresholds(
        to_add_count=51, to_remove_count=0, remote_count=100, policy=policy
    )
    assert "ADDITION_PERCENT_EXCEEDED" in addition.reasons

    safe = evaluate_thresholds(to_add_count=10, to_remove_count=2, remote_count=100, policy=policy)
    assert safe.breached is False


def test_empty_remote_addition_ratio_requires_approval() -> None:
    policy = ThresholdPolicy()
    result = evaluate_thresholds(to_add_count=10, to_remove_count=0, remote_count=0, policy=policy)
    assert result.addition_ratio == 1.0
    assert result.breached is True


def test_auto_apply_only_for_small_removals() -> None:
    policy = ThresholdPolicy(auto_apply_max_removals=5, auto_apply_max_removal_ratio=2.0)
    assert auto_apply_allowed(to_remove_count=5, removal_ratio=0.02, policy=policy)
    assert not auto_apply_allowed(to_remove_count=6, removal_ratio=0.01, policy=policy)
    assert not auto_apply_allowed(to_remove_count=1, removal_ratio=0.03, policy=policy)


def test_reorder_chunking_and_needed_flag() -> None:
    keys = [MediaKey("MOVIE", "tmdb", str(index)) for index in range(1, 2501)]
    chunks = reorder_chunks(keys)
    assert [len(chunk) for chunk in chunks] == [1000, 1000, 500]
    assert chunks[0][0] == keys[0]
    assert chunks[-1][-1] == keys[-1]

    binding = _binding(preserve_order=True)
    plan = plan_sync(
        mode="MIRROR",
        snapshot=_snapshot(),
        source_items=[_source(2), _source(1)],
        remote_items=[_remote(1), _remote(2)],
        binding=binding,
        policy_version="v1",
    )
    assert plan.reorder_needed is True
    assert [key.value for key in plan.desired_order] == ["2", "1"]


@pytest.mark.parametrize("chunk_size", [0, -1])
def test_reorder_chunking_rejects_invalid_size(chunk_size: int) -> None:
    with pytest.raises(ValueError):
        reorder_chunks([MediaKey("MOVIE", "tmdb", "1")], chunk_size=chunk_size)
