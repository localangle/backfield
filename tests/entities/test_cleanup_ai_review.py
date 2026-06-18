"""Tests for cleanup AI review prompt and proposal construction."""

from __future__ import annotations

from backfield_entities.quality.cleanup_ai_review import (
    CleanupClusterMember,
    build_cluster_partition_prompt,
    build_proposals_from_partition,
    choose_keeper_member_id,
    cluster_id_for_member_ids,
    parse_cluster_partition_response,
)


def test_cluster_id_for_member_ids() -> None:
    assert cluster_id_for_member_ids(["b", "a"]) == "a:2"


def test_choose_keeper_prefers_linked_substrate_count() -> None:
    members = [
        CleanupClusterMember(
            id="a",
            label="A",
            linked_substrate_count=1,
            mention_count=0,
        ),
        CleanupClusterMember(
            id="b",
            label="B",
            linked_substrate_count=5,
            mention_count=1,
        ),
    ]
    assert choose_keeper_member_id(members) == "b"


def test_build_cluster_partition_prompt_includes_person_fields() -> None:
    prompt = build_cluster_partition_prompt(
        check_id="duplicate-people",
        members=[
            CleanupClusterMember(
                id="person-1",
                label="Jane Doe",
                linked_substrate_count=2,
                mention_count=3,
                sample_mention_texts=("Jane Doe homered", "Doe went 2-for-4"),
                person_type="athlete",
                affiliation="Cubs",
            ),
            CleanupClusterMember(
                id="person-2",
                label="Jane Doe",
                linked_substrate_count=0,
                mention_count=1,
                affiliation="White Sox",
            ),
        ],
    )
    assert "duplicate-people" not in prompt
    assert "person-1" in prompt
    assert "athlete" in prompt
    assert "Jane Doe homered" in prompt
    assert "Partition every listed id" in prompt


def test_parse_cluster_partition_response_requires_full_cover() -> None:
    valid = {"person-1", "person-2"}
    parsed = parse_cluster_partition_response(
        {
            "groups": [
                {
                    "member_ids": ["person-1", "person-2"],
                    "confidence": 0.95,
                    "rationale": "Same person",
                }
            ]
        },
        valid_member_ids=valid,
    )
    assert parsed is not None
    assert len(parsed) == 1
    assert parse_cluster_partition_response(
        {"groups": [{"member_ids": ["person-1"], "confidence": 0.5}]},
        valid_member_ids=valid,
    ) is None


def test_build_proposals_from_partition_merge_and_keep_separate() -> None:
    members = [
        CleanupClusterMember(id="a", label="A", linked_substrate_count=3, mention_count=1),
        CleanupClusterMember(id="b", label="B", linked_substrate_count=1, mention_count=1),
        CleanupClusterMember(id="c", label="C", linked_substrate_count=0, mention_count=0),
    ]
    groups = parse_cluster_partition_response(
        {
            "groups": [
                {"member_ids": ["a", "b"], "confidence": 0.92, "rationale": "Same"},
                {"member_ids": ["c"], "confidence": 0.88, "rationale": "Different"},
            ]
        },
        valid_member_ids={"a", "b", "c"},
    )
    assert groups is not None
    proposals = build_proposals_from_partition(
        cluster_id=cluster_id_for_member_ids(["a", "b", "c"]),
        members=members,
        groups=groups,
    )
    merge = next(proposal for proposal in proposals if proposal.action == "merge")
    assert merge.target_canonical_id == "a"
    assert merge.member_ids == ("a", "b")
    keep = [proposal for proposal in proposals if proposal.action == "keep_separate"]
    assert len(keep) == 2
    assert {tuple(proposal.member_ids) for proposal in keep} == {("a", "c"), ("b", "c")}
