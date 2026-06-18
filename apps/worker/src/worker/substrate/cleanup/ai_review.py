"""Worker helpers for Stylebook cleanup AI review runs."""

from __future__ import annotations

import json
import os
from typing import Any

from agate_utils.llm import call_llm
from backfield_db import (
    BackfieldProject,
    StylebookCleanupAiProposal,
    StylebookLocationCanonical,
    StylebookOrganizationCanonical,
    StylebookPersonCanonical,
    SubstrateLocation,
    SubstrateLocationMention,
    SubstrateOrganization,
    SubstrateOrganizationMention,
    SubstratePerson,
    SubstratePersonMention,
)
from backfield_entities.quality.cleanup_ai_review import (
    CleanupAiProposalDraft,
    CleanupClusterMember,
    build_cluster_partition_prompt,
    build_proposals_from_partition,
    cluster_id_for_member_ids,
    parse_cluster_partition_response,
)
from sqlmodel import Session, col, func, select

from worker.substrate.canonical.llm_call_policy import (
    ADJUDICATION_LLM_MAX_RETRIES,
    ADJUDICATION_LLM_TIMEOUT_S,
)


def _organization_project_ids(session: Session, *, organization_id: int) -> list[int]:
    rows = session.exec(
        select(BackfieldProject.id).where(BackfieldProject.organization_id == organization_id)
    ).all()
    return [int(row) for row in rows if row is not None]


def _mention_counts_for_persons(
    session: Session,
    *,
    project_ids: list[int],
    canonical_ids: list[str],
) -> dict[str, int]:
    if not project_ids or not canonical_ids:
        return {}
    rows = session.exec(
        select(
            SubstratePerson.stylebook_person_canonical_id,
            func.count(col(SubstratePersonMention.id)),
        )
        .select_from(SubstratePersonMention)
        .join(SubstratePerson, SubstratePerson.id == SubstratePersonMention.person_id)
        .where(
            col(SubstratePerson.project_id).in_(project_ids),
            col(SubstratePerson.stylebook_person_canonical_id).in_(canonical_ids),
            SubstratePersonMention.deleted == False,  # noqa: E712
        )
        .group_by(SubstratePerson.stylebook_person_canonical_id)
    ).all()
    return {str(cid): int(cnt) for cid, cnt in rows if cid is not None}


def _linked_counts_for_persons(
    session: Session,
    *,
    project_ids: list[int],
    canonical_ids: list[str],
) -> dict[str, int]:
    if not project_ids or not canonical_ids:
        return {}
    rows = session.exec(
        select(
            SubstratePerson.stylebook_person_canonical_id,
            func.count(col(SubstratePerson.id)),
        )
        .where(
            col(SubstratePerson.project_id).in_(project_ids),
            col(SubstratePerson.stylebook_person_canonical_id).in_(canonical_ids),
        )
        .group_by(SubstratePerson.stylebook_person_canonical_id)
    ).all()
    return {str(cid): int(cnt) for cid, cnt in rows if cid is not None}


def _mention_counts_for_organizations(
    session: Session,
    *,
    project_ids: list[int],
    canonical_ids: list[str],
) -> dict[str, int]:
    if not project_ids or not canonical_ids:
        return {}
    rows = session.exec(
        select(
            SubstrateOrganization.stylebook_organization_canonical_id,
            func.count(col(SubstrateOrganizationMention.id)),
        )
        .select_from(SubstrateOrganizationMention)
        .join(
            SubstrateOrganization,
            SubstrateOrganization.id == SubstrateOrganizationMention.organization_id,
        )
        .where(
            col(SubstrateOrganization.project_id).in_(project_ids),
            col(SubstrateOrganization.stylebook_organization_canonical_id).in_(canonical_ids),
            SubstrateOrganizationMention.deleted == False,  # noqa: E712
        )
        .group_by(SubstrateOrganization.stylebook_organization_canonical_id)
    ).all()
    return {str(cid): int(cnt) for cid, cnt in rows if cid is not None}


def _linked_counts_for_organizations(
    session: Session,
    *,
    project_ids: list[int],
    canonical_ids: list[str],
) -> dict[str, int]:
    if not project_ids or not canonical_ids:
        return {}
    rows = session.exec(
        select(
            SubstrateOrganization.stylebook_organization_canonical_id,
            func.count(col(SubstrateOrganization.id)),
        )
        .where(
            col(SubstrateOrganization.project_id).in_(project_ids),
            col(SubstrateOrganization.stylebook_organization_canonical_id).in_(canonical_ids),
        )
        .group_by(SubstrateOrganization.stylebook_organization_canonical_id)
    ).all()
    return {str(cid): int(cnt) for cid, cnt in rows if cid is not None}


def _mention_counts_for_locations(
    session: Session,
    *,
    project_ids: list[int],
    canonical_ids: list[str],
) -> dict[str, int]:
    if not project_ids or not canonical_ids:
        return {}
    rows = session.exec(
        select(
            SubstrateLocation.stylebook_location_canonical_id,
            func.count(col(SubstrateLocationMention.id)),
        )
        .select_from(SubstrateLocationMention)
        .join(SubstrateLocation, SubstrateLocation.id == SubstrateLocationMention.location_id)
        .where(
            col(SubstrateLocation.project_id).in_(project_ids),
            col(SubstrateLocation.stylebook_location_canonical_id).in_(canonical_ids),
            SubstrateLocationMention.deleted == False,  # noqa: E712
        )
        .group_by(SubstrateLocation.stylebook_location_canonical_id)
    ).all()
    return {str(cid): int(cnt) for cid, cnt in rows if cid is not None}


def _linked_counts_for_locations(
    session: Session,
    *,
    project_ids: list[int],
    canonical_ids: list[str],
) -> dict[str, int]:
    if not project_ids or not canonical_ids:
        return {}
    rows = session.exec(
        select(
            SubstrateLocation.stylebook_location_canonical_id,
            func.count(col(SubstrateLocation.id)),
        )
        .where(
            col(SubstrateLocation.project_id).in_(project_ids),
            col(SubstrateLocation.stylebook_location_canonical_id).in_(canonical_ids),
        )
        .group_by(SubstrateLocation.stylebook_location_canonical_id)
    ).all()
    return {str(cid): int(cnt) for cid, cnt in rows if cid is not None}


def load_cluster_members(
    session: Session,
    *,
    check_id: str,
    stylebook_id: int,
    organization_id: int,
    member_ids: list[str],
) -> list[CleanupClusterMember]:
    project_ids = _organization_project_ids(session, organization_id=organization_id)
    sorted_ids = sorted({member_id for member_id in member_ids if member_id})
    if check_id == "duplicate-people":
        rows = session.exec(
            select(StylebookPersonCanonical).where(
                StylebookPersonCanonical.stylebook_id == stylebook_id,
                col(StylebookPersonCanonical.id).in_(sorted_ids),
            )
        ).all()
        mentions = _mention_counts_for_persons(
            session, project_ids=project_ids, canonical_ids=sorted_ids
        )
        linked = _linked_counts_for_persons(
            session, project_ids=project_ids, canonical_ids=sorted_ids
        )
        return [
            CleanupClusterMember(
                id=str(row.id),
                label=str(row.label),
                linked_substrate_count=linked.get(str(row.id), 0),
                mention_count=mentions.get(str(row.id), 0),
                person_type=(row.person_type or "").strip() or None,
                title=(row.title or "").strip() or None,
                affiliation=(row.affiliation or "").strip() or None,
                public_figure=bool(row.public_figure) if row.public_figure is not None else None,
            )
            for row in rows
            if row.id is not None
        ]
    if check_id == "duplicate-organizations":
        rows = session.exec(
            select(StylebookOrganizationCanonical).where(
                StylebookOrganizationCanonical.stylebook_id == stylebook_id,
                col(StylebookOrganizationCanonical.id).in_(sorted_ids),
            )
        ).all()
        mentions = _mention_counts_for_organizations(
            session, project_ids=project_ids, canonical_ids=sorted_ids
        )
        linked = _linked_counts_for_organizations(
            session, project_ids=project_ids, canonical_ids=sorted_ids
        )
        return [
            CleanupClusterMember(
                id=str(row.id),
                label=str(row.label),
                linked_substrate_count=linked.get(str(row.id), 0),
                mention_count=mentions.get(str(row.id), 0),
                organization_type=(row.organization_type or "").strip() or None,
            )
            for row in rows
            if row.id is not None
        ]
    rows = session.exec(
        select(StylebookLocationCanonical).where(
            StylebookLocationCanonical.stylebook_id == stylebook_id,
            col(StylebookLocationCanonical.id).in_(sorted_ids),
        )
    ).all()
    mentions = _mention_counts_for_locations(
        session, project_ids=project_ids, canonical_ids=sorted_ids
    )
    linked = _linked_counts_for_locations(
        session, project_ids=project_ids, canonical_ids=sorted_ids
    )
    return [
        CleanupClusterMember(
            id=str(row.id),
            label=str(row.label),
            linked_substrate_count=linked.get(str(row.id), 0),
            mention_count=mentions.get(str(row.id), 0),
            location_type=(row.location_type or "").strip() or None,
            formatted_address=(row.formatted_address or "").strip() or None,
        )
        for row in rows
        if row.id is not None
    ]


def run_cluster_partition_llm(
    *,
    prompt: str,
    model: str,
    model_config_id: str | None,
) -> dict[str, Any] | None:
    try:
        raw = call_llm(
            prompt,
            model=model,
            force_json=True,
            temperature=0.0,
            max_retries=ADJUDICATION_LLM_MAX_RETRIES,
            timeout=ADJUDICATION_LLM_TIMEOUT_S,
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            model_config_id=model_config_id,
        )
        data = json.loads(raw)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    return data


def propose_for_cluster(
    *,
    check_id: str,
    members: list[CleanupClusterMember],
    model: str,
    model_config_id: str | None,
) -> list[CleanupAiProposalDraft]:
    if len(members) < 2:
        return []
    cluster_id = cluster_id_for_member_ids([member.id for member in members])
    prompt = build_cluster_partition_prompt(check_id=check_id, members=members)
    llm_data = run_cluster_partition_llm(
        prompt=prompt,
        model=model,
        model_config_id=model_config_id,
    )
    valid_ids = {member.id for member in members}
    groups = parse_cluster_partition_response(llm_data, valid_member_ids=valid_ids)
    if groups is None:
        return []
    return build_proposals_from_partition(
        cluster_id=cluster_id,
        members=members,
        groups=groups,
    )


def proposal_draft_to_row(
    *,
    review_id: str,
    stylebook_id: int,
    check_id: str,
    draft: CleanupAiProposalDraft,
) -> StylebookCleanupAiProposal:
    return StylebookCleanupAiProposal(
        review_id=review_id,
        stylebook_id=stylebook_id,
        check_id=check_id,
        cluster_id=draft.cluster_id,
        action=draft.action,
        target_canonical_id=draft.target_canonical_id,
        member_ids_json=list(draft.member_ids),
        confidence=float(draft.confidence),
        rationale=draft.rationale,
        status="pending",
    )
