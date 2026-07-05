"""Worker helpers for Stylebook cleanup AI review runs."""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextvars import copy_context
from datetime import UTC, datetime
from typing import Any

from agate_utils.llm import call_llm
from backfield_db import (
    BackfieldProject,
    StylebookCleanupAiProposal,
    StylebookCleanupAiReview,
    StylebookLocationCanonical,
    StylebookOrganizationCanonical,
    StylebookPersonCanonical,
    SubstrateLocation,
    SubstrateLocationMention,
    SubstrateLocationMentionOccurrence,
    SubstrateOrganization,
    SubstrateOrganizationMention,
    SubstrateOrganizationMentionOccurrence,
    SubstratePerson,
    SubstratePersonMention,
    SubstratePersonMentionOccurrence,
)
from backfield_entities.activity import EVENT_AI_REVIEW_COMPLETED, log_stylebook_activity_safe
from backfield_entities.quality.cleanup_ai_review import (
    MAX_MENTION_SAMPLES_IN_PROMPT,
    CleanupAiProposalDraft,
    CleanupClusterMember,
    build_cluster_partition_prompt,
    build_proposals_from_partition,
    cluster_id_for_member_ids,
    parse_cluster_partition_response,
)
from sqlmodel import Session, col, func, select

from worker.substrate.ai_review_cancel import ai_review_status_is_cancelled, load_review_status
from worker.substrate.canonical.llm_call_policy import (
    ADJUDICATION_LLM_MAX_RETRIES,
    ADJUDICATION_LLM_TIMEOUT_S,
)
from worker.substrate.canonical.parallel_llm import canonical_adjudication_max_concurrent

_MAX_MENTION_TEXT_LEN = 120


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


def _normalize_mention_text(text: str) -> str:
    cleaned = " ".join(str(text).split())
    if len(cleaned) <= _MAX_MENTION_TEXT_LEN:
        return cleaned
    return cleaned[: _MAX_MENTION_TEXT_LEN - 3].rstrip() + "..."


def _accumulate_sample_texts(
    bucket: dict[str, list[str]],
    *,
    canonical_id: str | None,
    mention_text: str | None,
) -> None:
    if canonical_id is None:
        return
    normalized = _normalize_mention_text(mention_text or "")
    if not normalized:
        return
    key = str(canonical_id)
    existing = bucket.setdefault(key, [])
    if normalized in existing:
        return
    if len(existing) >= MAX_MENTION_SAMPLES_IN_PROMPT:
        return
    existing.append(normalized)


def _sample_mention_texts_for_person_canonicals(
    session: Session,
    *,
    project_ids: list[int],
    canonical_ids: list[str],
) -> dict[str, tuple[str, ...]]:
    if not project_ids or not canonical_ids:
        return {}
    rows = session.exec(
        select(
            SubstratePerson.stylebook_person_canonical_id,
            SubstratePersonMentionOccurrence.mention_text,
        )
        .select_from(SubstratePersonMentionOccurrence)
        .join(
            SubstratePersonMention,
            SubstratePersonMention.id == SubstratePersonMentionOccurrence.person_mention_id,
        )
        .join(SubstratePerson, SubstratePerson.id == SubstratePersonMention.person_id)
        .where(
            col(SubstratePerson.project_id).in_(project_ids),
            col(SubstratePerson.stylebook_person_canonical_id).in_(canonical_ids),
            SubstratePersonMention.deleted == False,  # noqa: E712
            SubstratePersonMentionOccurrence.suppressed == False,  # noqa: E712
        )
        .order_by(col(SubstratePersonMentionOccurrence.id).desc())
    ).all()
    bucket: dict[str, list[str]] = {}
    for canonical_id, mention_text in rows:
        _accumulate_sample_texts(bucket, canonical_id=str(canonical_id), mention_text=mention_text)
    return {key: tuple(values) for key, values in bucket.items()}


def _sample_mention_texts_for_organization_canonicals(
    session: Session,
    *,
    project_ids: list[int],
    canonical_ids: list[str],
) -> dict[str, tuple[str, ...]]:
    if not project_ids or not canonical_ids:
        return {}
    rows = session.exec(
        select(
            SubstrateOrganization.stylebook_organization_canonical_id,
            SubstrateOrganizationMentionOccurrence.mention_text,
        )
        .select_from(SubstrateOrganizationMentionOccurrence)
        .join(
            SubstrateOrganizationMention,
            SubstrateOrganizationMention.id
            == SubstrateOrganizationMentionOccurrence.organization_mention_id,
        )
        .join(
            SubstrateOrganization,
            SubstrateOrganization.id == SubstrateOrganizationMention.organization_id,
        )
        .where(
            col(SubstrateOrganization.project_id).in_(project_ids),
            col(SubstrateOrganization.stylebook_organization_canonical_id).in_(canonical_ids),
            SubstrateOrganizationMention.deleted == False,  # noqa: E712
            SubstrateOrganizationMentionOccurrence.suppressed == False,  # noqa: E712
        )
        .order_by(col(SubstrateOrganizationMentionOccurrence.id).desc())
    ).all()
    bucket: dict[str, list[str]] = {}
    for canonical_id, mention_text in rows:
        _accumulate_sample_texts(bucket, canonical_id=str(canonical_id), mention_text=mention_text)
    return {key: tuple(values) for key, values in bucket.items()}


def _sample_mention_texts_for_location_canonicals(
    session: Session,
    *,
    project_ids: list[int],
    canonical_ids: list[str],
) -> dict[str, tuple[str, ...]]:
    if not project_ids or not canonical_ids:
        return {}
    rows = session.exec(
        select(
            SubstrateLocation.stylebook_location_canonical_id,
            SubstrateLocationMentionOccurrence.mention_text,
        )
        .select_from(SubstrateLocationMentionOccurrence)
        .join(
            SubstrateLocationMention,
            SubstrateLocationMention.id == SubstrateLocationMentionOccurrence.location_mention_id,
        )
        .join(SubstrateLocation, SubstrateLocation.id == SubstrateLocationMention.location_id)
        .where(
            col(SubstrateLocation.project_id).in_(project_ids),
            col(SubstrateLocation.stylebook_location_canonical_id).in_(canonical_ids),
            SubstrateLocationMention.deleted == False,  # noqa: E712
            SubstrateLocationMentionOccurrence.suppressed == False,  # noqa: E712
        )
        .order_by(col(SubstrateLocationMentionOccurrence.id).desc())
    ).all()
    bucket: dict[str, list[str]] = {}
    for canonical_id, mention_text in rows:
        _accumulate_sample_texts(bucket, canonical_id=str(canonical_id), mention_text=mention_text)
    return {key: tuple(values) for key, values in bucket.items()}


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
        sample_texts = _sample_mention_texts_for_person_canonicals(
            session, project_ids=project_ids, canonical_ids=sorted_ids
        )
        return [
            CleanupClusterMember(
                id=str(row.id),
                label=str(row.label),
                linked_substrate_count=linked.get(str(row.id), 0),
                mention_count=mentions.get(str(row.id), 0),
                sample_mention_texts=sample_texts.get(str(row.id), ()),
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
        sample_texts = _sample_mention_texts_for_organization_canonicals(
            session, project_ids=project_ids, canonical_ids=sorted_ids
        )
        return [
            CleanupClusterMember(
                id=str(row.id),
                label=str(row.label),
                linked_substrate_count=linked.get(str(row.id), 0),
                mention_count=mentions.get(str(row.id), 0),
                sample_mention_texts=sample_texts.get(str(row.id), ()),
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
    sample_texts = _sample_mention_texts_for_location_canonicals(
        session, project_ids=project_ids, canonical_ids=sorted_ids
    )
    return [
        CleanupClusterMember(
            id=str(row.id),
            label=str(row.label),
            linked_substrate_count=linked.get(str(row.id), 0),
            mention_count=mentions.get(str(row.id), 0),
            sample_mention_texts=sample_texts.get(str(row.id), ()),
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


def _cleanup_ai_review_is_cancelled(engine: Any, review_id: str) -> bool:
    status = load_review_status(engine, model=StylebookCleanupAiReview, review_id=review_id)
    return ai_review_status_is_cancelled(status)


def _persist_cluster_proposals(
    engine: Any,
    *,
    review_id: str,
    stylebook_id: int,
    check_id: str,
    drafts: list[CleanupAiProposalDraft],
    processed_cluster_count: int,
    proposal_count: int,
) -> None:
    if _cleanup_ai_review_is_cancelled(engine, review_id):
        return
    with Session(engine) as session:
        review = session.get(StylebookCleanupAiReview, review_id)
        if review is None or ai_review_status_is_cancelled(str(review.status)):
            return
        for draft in drafts:
            session.add(
                proposal_draft_to_row(
                    review_id=review_id,
                    stylebook_id=stylebook_id,
                    check_id=check_id,
                    draft=draft,
                )
            )
        review.processed_cluster_count = processed_cluster_count
        review.proposal_count = proposal_count
        review.updated_at = datetime.now(UTC)
        session.add(review)
        session.commit()


def _mark_cleanup_review_succeeded(engine: Any, *, review_id: str) -> None:
    with Session(engine) as session:
        review = session.get(StylebookCleanupAiReview, review_id)
        if review is None or ai_review_status_is_cancelled(str(review.status)):
            return
        review.status = "succeeded"
        review.updated_at = datetime.now(UTC)
        log_stylebook_activity_safe(
            session,
            stylebook_id=int(review.stylebook_id),
            actor_type="system",
            source="cleanup_ai",
            event_type=EVENT_AI_REVIEW_COMPLETED,
            entity_type="check",
            entity_id=str(review.check_id),
            payload_json={
                "review_id": str(review.id),
                "cluster_count": int(review.cluster_count),
                "processed_cluster_count": int(review.processed_cluster_count),
                "proposal_count": int(review.proposal_count),
                "status": "succeeded",
            },
        )
        session.add(review)
        session.commit()


def run_cleanup_review_clusters(
    engine: Any,
    *,
    review_id: str,
    check_id: str,
    stylebook_id: int,
    members_by_cluster: list[list[CleanupClusterMember]],
    model: str,
    model_config_id: str | None,
) -> None:
    """Run cluster LLM calls in parallel and persist progress after each cluster finishes."""
    if _cleanup_ai_review_is_cancelled(engine, review_id):
        return
    if not members_by_cluster:
        _mark_cleanup_review_succeeded(engine, review_id=review_id)
        return

    max_workers = canonical_adjudication_max_concurrent()
    processed_cluster_count = 0
    proposal_count = 0

    def _task(members: list[CleanupClusterMember]) -> list[CleanupAiProposalDraft]:
        if _cleanup_ai_review_is_cancelled(engine, review_id):
            return []
        return propose_for_cluster(
            check_id=check_id,
            members=members,
            model=model,
            model_config_id=model_config_id,
        )

    if max_workers <= 1 or len(members_by_cluster) <= 1:
        for members in members_by_cluster:
            if _cleanup_ai_review_is_cancelled(engine, review_id):
                return
            drafts = _task(members)
            processed_cluster_count += 1
            proposal_count += len(drafts)
            _persist_cluster_proposals(
                engine,
                review_id=review_id,
                stylebook_id=stylebook_id,
                check_id=check_id,
                drafts=drafts,
                processed_cluster_count=processed_cluster_count,
                proposal_count=proposal_count,
            )
    else:
        workers = min(max_workers, len(members_by_cluster))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            future_to_members = {
                pool.submit(copy_context().run, _task, members): members
                for members in members_by_cluster
            }
            for future in as_completed(future_to_members):
                if _cleanup_ai_review_is_cancelled(engine, review_id):
                    break
                drafts = future.result()
                processed_cluster_count += 1
                proposal_count += len(drafts)
                _persist_cluster_proposals(
                    engine,
                    review_id=review_id,
                    stylebook_id=stylebook_id,
                    check_id=check_id,
                    drafts=drafts,
                    processed_cluster_count=processed_cluster_count,
                    proposal_count=proposal_count,
                )

    if not _cleanup_ai_review_is_cancelled(engine, review_id):
        _mark_cleanup_review_succeeded(engine, review_id=review_id)
