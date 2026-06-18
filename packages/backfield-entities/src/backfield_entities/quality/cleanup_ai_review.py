"""AI-assisted duplicate-cluster cleanup review (prompt + proposal construction)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

CleanupAiAction = Literal["merge", "keep_separate"]

MAX_MENTION_SAMPLES_IN_PROMPT = 6


@dataclass(frozen=True)
class CleanupClusterMember:
    id: str
    label: str
    linked_substrate_count: int
    mention_count: int
    sample_mention_texts: tuple[str, ...] = ()
    person_type: str | None = None
    title: str | None = None
    affiliation: str | None = None
    public_figure: bool | None = None
    organization_type: str | None = None
    location_type: str | None = None
    formatted_address: str | None = None


@dataclass(frozen=True)
class CleanupAiProposalDraft:
    cluster_id: str
    action: CleanupAiAction
    target_canonical_id: str | None
    member_ids: tuple[str, ...]
    confidence: float
    rationale: str | None


@dataclass(frozen=True)
class CleanupClusterPartitionGroup:
    member_ids: tuple[str, ...]
    confidence: float
    rationale: str | None


def cluster_id_for_member_ids(member_ids: list[str]) -> str:
    sorted_ids = sorted({member_id for member_id in member_ids if member_id})
    if not sorted_ids:
        return "0:0"
    return f"{sorted_ids[0]}:{len(sorted_ids)}"


def choose_keeper_member_id(members: list[CleanupClusterMember]) -> str:
    if not members:
        raise ValueError("choose_keeper_member_id requires at least one member")
    ranked = sorted(
        members,
        key=lambda member: (
            -int(member.linked_substrate_count),
            -int(member.mention_count),
            str(member.id),
        ),
    )
    return str(ranked[0].id)


def _member_by_id(members: list[CleanupClusterMember]) -> dict[str, CleanupClusterMember]:
    return {str(member.id): member for member in members}


def _format_member_line(check_id: str, member: CleanupClusterMember) -> str:
    parts = [
        f"id={member.id}",
        f"label={member.label!r}",
        f"linked={member.linked_substrate_count}",
        f"mentions={member.mention_count}",
    ]
    if check_id == "duplicate-people":
        if member.person_type:
            parts.append(f"person_type={member.person_type!r}")
        if member.title:
            parts.append(f"title={member.title!r}")
        if member.affiliation:
            parts.append(f"affiliation={member.affiliation!r}")
        if member.public_figure is not None:
            parts.append(f"public_figure={member.public_figure}")
    elif check_id == "duplicate-organizations":
        if member.organization_type:
            parts.append(f"organization_type={member.organization_type!r}")
    elif check_id == "duplicate-locations":
        if member.location_type:
            parts.append(f"location_type={member.location_type!r}")
        if member.formatted_address:
            parts.append(f"formatted_address={member.formatted_address!r}")
    if member.sample_mention_texts:
        samples = member.sample_mention_texts[:MAX_MENTION_SAMPLES_IN_PROMPT]
        shown = ", ".join(repr(text) for text in samples)
        parts.append(f"mention_texts=[{shown}]")
    return "- " + " ".join(parts)


def build_cluster_partition_prompt(
    *,
    check_id: str,
    members: list[CleanupClusterMember],
) -> str:
    entity_label = {
        "duplicate-people": "person",
        "duplicate-organizations": "organization",
        "duplicate-locations": "location",
    }.get(check_id, "entity")
    member_lines = "\n".join(_format_member_line(check_id, member) for member in members)
    member_ids = sorted({member.id for member in members})
    return (
        f"You are reviewing a cleanup cluster of possible duplicate {entity_label} records.\n"
        "Each record below is a canonical catalog row grouped because names look similar.\n"
        "Decide which records refer to the same real-world entity and which are different "
        "entities (namesakes, homonyms, or unrelated matches).\n\n"
        "Rules:\n"
        "- Partition every listed id into one or more groups.\n"
        "- Records in the same group should be merged into one canonical record.\n"
        "- Records in different groups should be kept separate.\n"
        "- For athletes/public figures, team or role changes over time "
        "do not imply a different person.\n"
        "- Prefer separate groups when evidence suggests different individuals "
        "with similar names.\n"
        "- Use mention_texts (how the entity appears in stories) to distinguish "
        "namesakes from the same real-world entity.\n"
        "- Every id must appear in exactly one group.\n\n"
        f"Member ids: {member_ids}\n\n"
        f"{member_lines}\n\n"
        "Return JSON only:\n"
        '{"groups":[{"member_ids":["uuid",...],"confidence":0.0-1.0,'
        '"rationale":"short string"},...]}'
    )


def parse_cluster_partition_response(
    data: dict[str, Any] | None,
    *,
    valid_member_ids: set[str],
) -> list[CleanupClusterPartitionGroup] | None:
    if data is None:
        return None
    raw_groups = data.get("groups")
    if not isinstance(raw_groups, list):
        return None
    seen: set[str] = set()
    groups: list[CleanupClusterPartitionGroup] = []
    for raw in raw_groups:
        if not isinstance(raw, dict):
            return None
        raw_ids = raw.get("member_ids")
        if not isinstance(raw_ids, list) or not raw_ids:
            return None
        member_ids = tuple(
            sorted({str(member_id).strip() for member_id in raw_ids if str(member_id).strip()})
        )
        if not member_ids:
            return None
        if not set(member_ids).issubset(valid_member_ids):
            return None
        if seen.intersection(member_ids):
            return None
        seen.update(member_ids)
        conf_raw = raw.get("confidence", 0.0)
        try:
            confidence = float(conf_raw)
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))
        rationale = str(raw.get("rationale") or "").strip() or None
        groups.append(
            CleanupClusterPartitionGroup(
                member_ids=member_ids,
                confidence=confidence,
                rationale=rationale,
            )
        )
    if seen != valid_member_ids:
        return None
    return groups


def build_proposals_from_partition(
    *,
    cluster_id: str,
    members: list[CleanupClusterMember],
    groups: list[CleanupClusterPartitionGroup],
) -> list[CleanupAiProposalDraft]:
    if len(groups) <= 0:
        return []
    by_id = _member_by_id(members)
    proposals: list[CleanupAiProposalDraft] = []

    for group in groups:
        group_members = [by_id[member_id] for member_id in group.member_ids if member_id in by_id]
        if len(group_members) >= 2:
            keeper_id = choose_keeper_member_id(group_members)
            proposals.append(
                CleanupAiProposalDraft(
                    cluster_id=cluster_id,
                    action="merge",
                    target_canonical_id=keeper_id,
                    member_ids=group.member_ids,
                    confidence=group.confidence,
                    rationale=group.rationale,
                )
            )

    if len(groups) >= 2:
        for left_index, left_group in enumerate(groups):
            for right_group in groups[left_index + 1 :]:
                for left_id in left_group.member_ids:
                    for right_id in right_group.member_ids:
                        pair = tuple(sorted((left_id, right_id)))
                        proposals.append(
                            CleanupAiProposalDraft(
                                cluster_id=cluster_id,
                                action="keep_separate",
                                target_canonical_id=None,
                                member_ids=pair,
                                confidence=min(left_group.confidence, right_group.confidence),
                                rationale=(
                                    left_group.rationale
                                    if left_group.rationale == right_group.rationale
                                    else None
                                ),
                            )
                        )
    return proposals
