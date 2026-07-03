"""Tests for persisted cleanup check run helpers."""

from __future__ import annotations

from backfield_db import StylebookCleanupCheckResult
from backfield_entities.quality.check_runs import (
    CleanupCheckItem,
    CleanupRunScope,
    cleanup_scope_hash,
    is_result_dismissed,
)


def test_cleanup_scope_hash_is_stable_for_same_scope() -> None:
    scope = CleanupRunScope(
        stylebook_id=1,
        organization_id=2,
        check_id="duplicate-locations",
        full_threshold=0.84,
        head_threshold=0.75,
        project_ids=None,
        project_slug=None,
    )
    assert cleanup_scope_hash(scope) == cleanup_scope_hash(scope)


def test_cleanup_scope_hash_changes_with_project_scope() -> None:
    base = CleanupRunScope(
        stylebook_id=1,
        organization_id=2,
        check_id="missing-geometry-locations",
        full_threshold=0.84,
        head_threshold=0.75,
        project_ids=None,
        project_slug=None,
    )
    scoped = CleanupRunScope(
        stylebook_id=1,
        organization_id=2,
        check_id="missing-geometry-locations",
        full_threshold=0.84,
        head_threshold=0.75,
        project_ids=(10,),
        project_slug="demo",
    )
    assert cleanup_scope_hash(base) != cleanup_scope_hash(scoped)


def test_is_result_dismissed_for_cluster_and_list() -> None:
    cluster = StylebookCleanupCheckResult(
        run_id="run-1",
        stylebook_id=1,
        check_id="duplicate-people",
        ordinal=0,
        item_kind="cluster",
        item_key="a:2",
        pair_keys_json=["a|b"],
    )
    assert is_result_dismissed(cluster, dismissed_keys=set()) is False
    assert is_result_dismissed(cluster, dismissed_keys={"a|b"}) is True

    list_row = StylebookCleanupCheckResult(
        run_id="run-1",
        stylebook_id=1,
        check_id="missing-geometry-locations",
        ordinal=0,
        item_kind="list",
        item_key="loc-1",
        pair_keys_json=["loc-1"],
    )
    assert is_result_dismissed(list_row, dismissed_keys={"loc-1"}) is True


def test_cleanup_check_item_shape_for_cluster() -> None:
    item = CleanupCheckItem(
        item_kind="cluster",
        item_key="abc:2",
        label="City Hall",
        canonical_ids=["abc", "def"],
        pair_keys=["abc|def"],
        payload={},
        searchable_text="city hall",
    )
    assert item.item_kind == "cluster"
    assert item.pair_keys == ["abc|def"]
