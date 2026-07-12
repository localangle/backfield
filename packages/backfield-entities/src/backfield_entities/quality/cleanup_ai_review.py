"""AI-assisted duplicate-cluster cleanup review (prompt + proposal construction)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from backfield_entities.entities.location.link_identity import location_merge_pair_blocked

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


def _entity_specific_partition_rules(check_id: str) -> str:
    if check_id == "duplicate-organizations":
        return (
            "- Treat the identity question as: do these labels name the same durable "
            "institution, office, campaign, team, company, union, agency, or organized body?\n"
            "- For organizations, merge aliases that name the same durable body even when one "
            "label is longer, includes an honorific, or includes a person's full name while "
            "another uses surname only.\n"
            "- Presidential, gubernatorial, mayoral, agency, campaign, team, committee, and "
            "administration labels should be merged when the labels clearly refer to the same "
            "body (for example, \"President Donald Trump's administration\" and "
            "\"President Trump's administration\").\n"
            "- Type or wording differences are not enough to keep records separate when the "
            "story mentions are compatible aliases for the same organization.\n"
            "- Keep separate only when the labels indicate distinct organizations, chapters, "
            "offices, teams, corporate entities, or time-bounded bodies.\n"
        )
    if check_id == "duplicate-people":
        return (
            "- Treat the identity question as: do these labels name the same individual human "
            "or public/stage-name person entity?\n"
            "- For people, athletes/public figures can change teams, titles, or roles over time; "
            "those changes alone do not imply a different person.\n"
            "- Merge nicknames, stage names, first/last-name variants, and fuller/shorter name "
            "forms only when the surrounding evidence supports the same person.\n"
            "- Prefer separate groups when evidence suggests different individuals with similar "
            "names.\n"
        )
    if check_id == "duplicate-locations":
        return (
            "- Treat the identity question as: do these labels identify the same real-world "
            "place, address, venue, natural feature, jurisdiction, district, or geography?\n"
            "- For locations, merge alternate labels, casing variants, suffix variants, and "
            "formatted-address variants only when they identify the same place.\n"
            "- Keep separate different branches, campuses, buildings, addresses, neighborhoods, "
            "jurisdictions, administrative levels, or similarly named places.\n"
            "- Do not merge a container geography with a finer-grained child place unless the "
            "labels are clearly two names for the same entity.\n"
            "- Never merge a specific venue, business, building, or point of interest into the "
            "city, town, neighborhood, or region that merely contains it. Labels like "
            "'<Venue>, Chicago, IL' name the venue, not the city; sharing a city/state tail is "
            "not evidence of identity.\n"
        )
    return ""


def _entity_specific_task_description(check_id: str) -> str:
    if check_id == "duplicate-people":
        return (
            "Decide which records refer to the same person and which are different people "
            "(namesakes, similarly named public figures, or unrelated matches)."
        )
    if check_id == "duplicate-organizations":
        return (
            "Decide which records refer to the same organization and which are different "
            "organizations (distinct bodies, chapters, offices, teams, companies, or unrelated "
            "matches)."
        )
    if check_id == "duplicate-locations":
        return (
            "Decide which records refer to the same location and which are different locations "
            "(distinct places, branches, addresses, jurisdictions, or unrelated matches)."
        )
    return (
        "Decide which records refer to the same real-world entity and which are different "
        "entities (namesakes, homonyms, or unrelated matches)."
    )


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
    task_description = _entity_specific_task_description(check_id)
    return (
        f"You are reviewing a cleanup cluster of possible duplicate {entity_label} records.\n"
        "Each record below is a canonical catalog row grouped because names look similar.\n"
        f"{task_description}\n\n"
        "Rules:\n"
        "- Partition every listed id into one or more groups.\n"
        "- Records in the same group should be merged into one canonical record.\n"
        "- Records in different groups should be kept separate.\n"
        "- Use mention_texts (how the entity appears in stories) to distinguish "
        "same-identity aliases from distinct entities of the same type.\n"
        f"{_entity_specific_partition_rules(check_id)}"
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


def _location_merge_group_blocked(
    group_members: list[CleanupClusterMember],
    *,
    keeper_id: str,
) -> bool:
    """True when any member pairs with the keeper across incompatible place kinds."""
    keeper = next((member for member in group_members if str(member.id) == keeper_id), None)
    if keeper is None:
        return False
    for member in group_members:
        if str(member.id) == keeper_id:
            continue
        if location_merge_pair_blocked(
            source_label=str(member.label),
            source_location_type=member.location_type,
            target_label=str(keeper.label),
            target_location_type=keeper.location_type,
        ):
            return True
    return False


def build_proposals_from_partition(
    *,
    check_id: str,
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
            # Never propose merging incompatible place kinds (e.g. a venue into its
            # containing city); leave those groups for manual review instead.
            if check_id == "duplicate-locations" and _location_merge_group_blocked(
                group_members, keeper_id=keeper_id
            ):
                continue
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
