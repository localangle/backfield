"""Stylebook cleanup AI review endpoints."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from backfield_db import (
    BackfieldAiModelConfig,
    StylebookCleanupAiProposal,
    StylebookCleanupAiReview,
    StylebookLocationCanonical,
    StylebookOrganizationCanonical,
    StylebookPersonCanonical,
)
from backfield_entities.entities.location.merge import merge_location_canonical_into
from backfield_entities.entities.organization.merge import merge_organization_canonical_into
from backfield_entities.entities.person.merge import merge_person_canonical_into
from backfield_entities.quality.checks import cleanup_check_by_id
from backfield_entities.quality.dismissals import dismiss_pair
from celery import Celery
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import Session, col, select

from stylebook_api.deps import get_auth, get_session
from stylebook_api.semantic_reindex import enqueue_semantic_reindex_for_entity
from stylebook_api.stylebook_permissions import require_stylebook_edit_access
from stylebook_api.stylebook_scope import require_stylebook_by_slug_in_auth_org

router = APIRouter(prefix="/v1/stylebooks", tags=["stylebook-cleanup"])

celery_app = Celery(
    "agate_worker",
    broker=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
)


def _celery_queue() -> str:
    return str(os.environ.get("CELERY_QUEUE", "agate"))


def _created_by_user_id(auth: dict[str, Any]) -> int | None:
    if auth.get("type") != "session" or auth.get("user") is None:
        return None
    return int(auth["user"].id)  # type: ignore[union-attr]


class CleanupAiModelOut(BaseModel):
    id: str
    name: str
    provider_model_id: str


class CleanupAiModelsResponse(BaseModel):
    models: list[CleanupAiModelOut]


class StartCleanupAiReviewBody(BaseModel):
    check_id: str = Field(min_length=1)
    provider_model_id: str = Field(min_length=1)
    ai_model_config_id: str | None = None


class CleanupAiReviewOut(BaseModel):
    id: str
    stylebook_id: int
    check_id: str
    status: str
    provider_model_id: str
    ai_model_config_id: str | None = None
    cluster_count: int = 0
    processed_cluster_count: int = 0
    proposal_count: int = 0
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_row(cls, row: StylebookCleanupAiReview) -> CleanupAiReviewOut:
        return cls(
            id=str(row.id),
            stylebook_id=int(row.stylebook_id),
            check_id=str(row.check_id),
            status=str(row.status),
            provider_model_id=str(row.provider_model_id),
            ai_model_config_id=row.ai_model_config_id,
            cluster_count=int(row.cluster_count),
            processed_cluster_count=int(row.processed_cluster_count),
            proposal_count=int(row.proposal_count),
            error_message=row.error_message,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


class CleanupAiProposalOut(BaseModel):
    id: str
    review_id: str
    check_id: str
    cluster_id: str
    action: Literal["merge", "keep_separate"]
    target_canonical_id: str | None = None
    member_ids: list[str]
    confidence: float
    rationale: str | None = None
    status: str

    @classmethod
    def from_row(cls, row: StylebookCleanupAiProposal) -> CleanupAiProposalOut:
        member_ids = row.member_ids_json if isinstance(row.member_ids_json, list) else []
        return cls(
            id=str(row.id),
            review_id=str(row.review_id),
            check_id=str(row.check_id),
            cluster_id=str(row.cluster_id),
            action=str(row.action),  # type: ignore[arg-type]
            target_canonical_id=row.target_canonical_id,
            member_ids=[str(member_id) for member_id in member_ids],
            confidence=float(row.confidence),
            rationale=row.rationale,
            status=str(row.status),
        )


class CleanupAiProposalsResponse(BaseModel):
    proposals: list[CleanupAiProposalOut]


class CleanupAiProposalActionResponse(BaseModel):
    id: str
    status: str
    message: str


def _require_cluster_check(check_id: str) -> None:
    check = cleanup_check_by_id(check_id)
    if check is None or check.kind != "cluster":
        raise HTTPException(status_code=400, detail="check_id must be a duplicate cluster check")


def _validate_model_selection(
    session: Session,
    *,
    organization_id: int,
    provider_model_id: str,
    ai_model_config_id: str | None,
) -> None:
    if ai_model_config_id:
        row = session.get(BackfieldAiModelConfig, ai_model_config_id)
        if (
            row is None
            or int(row.organization_id) != organization_id
            or str(row.status) != "active"
        ):
            raise HTTPException(status_code=400, detail="Invalid AI model selection")
        if str(row.provider_model_id) != provider_model_id.strip():
            raise HTTPException(status_code=400, detail="Model id mismatch for selected config")


def _canonical_exists(
    session: Session,
    *,
    check_id: str,
    stylebook_id: int,
    canonical_id: str,
) -> bool:
    if check_id == "duplicate-people":
        row = session.get(StylebookPersonCanonical, canonical_id)
    elif check_id == "duplicate-organizations":
        row = session.get(StylebookOrganizationCanonical, canonical_id)
    else:
        row = session.get(StylebookLocationCanonical, canonical_id)
    return row is not None and int(row.stylebook_id) == stylebook_id


def _apply_merge_proposal(
    session: Session,
    *,
    check_id: str,
    stylebook_id: int,
    organization_id: int,
    target_canonical_id: str,
    member_ids: list[str],
) -> int:
    relinked_total = 0
    for member_id in member_ids:
        if member_id == target_canonical_id:
            continue
        if check_id == "duplicate-people":
            result = merge_person_canonical_into(
                session,
                stylebook_id=stylebook_id,
                organization_id=organization_id,
                source_canonical_id=member_id,
                target_canonical_id=target_canonical_id,
                provenance="stylebook_cleanup_ai_review",
            )
            entity_type = "person"
        elif check_id == "duplicate-organizations":
            result = merge_organization_canonical_into(
                session,
                stylebook_id=stylebook_id,
                organization_id=organization_id,
                source_canonical_id=member_id,
                target_canonical_id=target_canonical_id,
                provenance="stylebook_cleanup_ai_review",
            )
            entity_type = "organization"
        else:
            result = merge_location_canonical_into(
                session,
                stylebook_id=stylebook_id,
                organization_id=organization_id,
                source_canonical_id=member_id,
                target_canonical_id=target_canonical_id,
                provenance="stylebook_cleanup_ai_review",
            )
            entity_type = "location"
        relinked_total += int(result.relinked_substrate_count)
        for project_id, entity_id in result.relinked_substrates:
            enqueue_semantic_reindex_for_entity(
                session,
                project_id=project_id,
                entity_type=entity_type,
                entity_id=entity_id,
            )
    return relinked_total


def _proposal_members_still_valid(
    session: Session,
    *,
    proposal: StylebookCleanupAiProposal,
    stylebook_id: int,
) -> bool:
    member_ids = proposal.member_ids_json if isinstance(proposal.member_ids_json, list) else []
    check_id = str(proposal.check_id)
    for member_id in member_ids:
        if not _canonical_exists(
            session,
            check_id=check_id,
            stylebook_id=stylebook_id,
            canonical_id=str(member_id),
        ):
            return False
    if proposal.action == "merge" and proposal.target_canonical_id:
        if not _canonical_exists(
            session,
            check_id=check_id,
            stylebook_id=stylebook_id,
            canonical_id=str(proposal.target_canonical_id),
        ):
            return False
    return True


@router.get("/{stylebook_slug}/cleanup/ai-models", response_model=CleanupAiModelsResponse)
def list_cleanup_ai_models(
    stylebook_slug: str,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> CleanupAiModelsResponse:
    sb = require_stylebook_by_slug_in_auth_org(session, auth=auth, stylebook_slug=stylebook_slug)
    rows = session.exec(
        select(BackfieldAiModelConfig)
        .where(
            BackfieldAiModelConfig.organization_id == int(sb.organization_id),
            BackfieldAiModelConfig.status == "active",
        )
        .order_by(BackfieldAiModelConfig.name)
    ).all()
    models: list[CleanupAiModelOut] = []
    for row in rows:
        caps = row.capabilities_json if isinstance(row.capabilities_json, list) else []
        cap_set = {str(cap).strip().lower() for cap in caps}
        if cap_set and not (cap_set & {"text", "json"}):
            continue
        if row.id is None:
            continue
        models.append(
            CleanupAiModelOut(
                id=str(row.id),
                name=str(row.name),
                provider_model_id=str(row.provider_model_id),
            )
        )
    return CleanupAiModelsResponse(models=models)


@router.post("/{stylebook_slug}/cleanup/ai-review", response_model=CleanupAiReviewOut)
def start_cleanup_ai_review(
    stylebook_slug: str,
    body: StartCleanupAiReviewBody,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> CleanupAiReviewOut:
    require_stylebook_edit_access(session, auth=auth, stylebook_slug=stylebook_slug)
    sb = require_stylebook_by_slug_in_auth_org(session, auth=auth, stylebook_slug=stylebook_slug)
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    _require_cluster_check(body.check_id)
    _validate_model_selection(
        session,
        organization_id=int(sb.organization_id),
        provider_model_id=body.provider_model_id,
        ai_model_config_id=body.ai_model_config_id,
    )
    review = StylebookCleanupAiReview(
        id=str(uuid.uuid4()),
        stylebook_id=int(sb.id),
        check_id=body.check_id.strip(),
        status="queued",
        provider_model_id=body.provider_model_id.strip(),
        ai_model_config_id=body.ai_model_config_id,
        created_by_user_id=_created_by_user_id(auth),
    )
    session.add(review)
    session.commit()
    session.refresh(review)
    celery_app.send_task(
        "worker.tasks.execute_cleanup_ai_review",
        args=[str(review.id)],
        queue=_celery_queue(),
    )
    return CleanupAiReviewOut.from_row(review)


@router.post(
    "/{stylebook_slug}/cleanup/ai-review/{review_id}/cancel",
    response_model=CleanupAiReviewOut,
)
def cancel_cleanup_ai_review(
    stylebook_slug: str,
    review_id: str,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> CleanupAiReviewOut:
    require_stylebook_edit_access(session, auth=auth, stylebook_slug=stylebook_slug)
    sb = require_stylebook_by_slug_in_auth_org(session, auth=auth, stylebook_slug=stylebook_slug)
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    review = session.get(StylebookCleanupAiReview, review_id)
    if review is None or int(review.stylebook_id) != int(sb.id):
        raise HTTPException(status_code=404, detail="AI review not found")
    if review.status not in ("queued", "running"):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Cannot stop review with status '{review.status}'. "
                "Only queued or running reviews can be stopped."
            ),
        )
    review.status = "cancelled"
    review.error_message = None
    review.updated_at = datetime.now(UTC)
    session.add(review)
    session.commit()
    session.refresh(review)
    return CleanupAiReviewOut.from_row(review)


@router.get("/{stylebook_slug}/cleanup/ai-review/latest", response_model=CleanupAiReviewOut | None)
def get_latest_cleanup_ai_review(
    stylebook_slug: str,
    check_id: str = Query(min_length=1),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> CleanupAiReviewOut | None:
    sb = require_stylebook_by_slug_in_auth_org(session, auth=auth, stylebook_slug=stylebook_slug)
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    row = session.exec(
        select(StylebookCleanupAiReview)
        .where(
            StylebookCleanupAiReview.stylebook_id == int(sb.id),
            StylebookCleanupAiReview.check_id == check_id.strip(),
        )
        .order_by(col(StylebookCleanupAiReview.created_at).desc())
    ).first()
    if row is None:
        return None
    return CleanupAiReviewOut.from_row(row)


@router.get("/{stylebook_slug}/cleanup/ai-review/{review_id}", response_model=CleanupAiReviewOut)
def get_cleanup_ai_review(
    stylebook_slug: str,
    review_id: str,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> CleanupAiReviewOut:
    sb = require_stylebook_by_slug_in_auth_org(session, auth=auth, stylebook_slug=stylebook_slug)
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    review = session.get(StylebookCleanupAiReview, review_id)
    if review is None or int(review.stylebook_id) != int(sb.id):
        raise HTTPException(status_code=404, detail="AI review not found")
    return CleanupAiReviewOut.from_row(review)


@router.get(
    "/{stylebook_slug}/cleanup/ai-review/{review_id}/proposals",
    response_model=CleanupAiProposalsResponse,
)
def list_cleanup_ai_proposals(
    stylebook_slug: str,
    review_id: str,
    status: str | None = Query(default="pending"),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> CleanupAiProposalsResponse:
    sb = require_stylebook_by_slug_in_auth_org(session, auth=auth, stylebook_slug=stylebook_slug)
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    review = session.get(StylebookCleanupAiReview, review_id)
    if review is None or int(review.stylebook_id) != int(sb.id):
        raise HTTPException(status_code=404, detail="AI review not found")
    query = select(StylebookCleanupAiProposal).where(
        StylebookCleanupAiProposal.review_id == review_id,
    )
    if status:
        query = query.where(StylebookCleanupAiProposal.status == status.strip())
    rows = session.exec(query.order_by(StylebookCleanupAiProposal.created_at)).all()
    return CleanupAiProposalsResponse(
        proposals=[CleanupAiProposalOut.from_row(row) for row in rows],
    )


@router.post(
    "/{stylebook_slug}/cleanup/ai-review/proposals/{proposal_id}/accept",
    response_model=CleanupAiProposalActionResponse,
)
def accept_cleanup_ai_proposal(
    stylebook_slug: str,
    proposal_id: str,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> CleanupAiProposalActionResponse:
    require_stylebook_edit_access(session, auth=auth, stylebook_slug=stylebook_slug)
    sb = require_stylebook_by_slug_in_auth_org(session, auth=auth, stylebook_slug=stylebook_slug)
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    proposal = session.get(StylebookCleanupAiProposal, proposal_id)
    if proposal is None or int(proposal.stylebook_id) != int(sb.id):
        raise HTTPException(status_code=404, detail="Proposal not found")
    if proposal.status != "pending":
        raise HTTPException(status_code=409, detail=f"Proposal is already {proposal.status}")

    stylebook_id = int(sb.id)
    if not _proposal_members_still_valid(session, proposal=proposal, stylebook_id=stylebook_id):
        proposal.status = "stale"
        proposal.resolved_at = datetime.now(UTC)
        proposal.resolved_by_user_id = _created_by_user_id(auth)
        session.add(proposal)
        session.commit()
        return CleanupAiProposalActionResponse(
            id=str(proposal.id),
            status="stale",
            message="Proposal is stale; one or more records changed.",
        )

    member_ids = [
        str(member_id)
        for member_id in (
            proposal.member_ids_json if isinstance(proposal.member_ids_json, list) else []
        )
    ]
    check_id = str(proposal.check_id)
    user_id = _created_by_user_id(auth)

    try:
        if proposal.action == "merge":
            target_id = str(proposal.target_canonical_id or "")
            if not target_id:
                raise HTTPException(status_code=400, detail="Merge proposal missing target")
            relinked = _apply_merge_proposal(
                session,
                check_id=check_id,
                stylebook_id=stylebook_id,
                organization_id=int(sb.organization_id),
                target_canonical_id=target_id,
                member_ids=member_ids,
            )
            message = f"Merged records into keeper ({relinked} linked records moved)."
        elif proposal.action == "keep_separate":
            if len(member_ids) != 2:
                raise HTTPException(
                    status_code=400,
                    detail="Keep-separate proposal requires a pair",
                )
            dismiss_pair(
                session,
                stylebook_id=stylebook_id,
                check_id=check_id,
                left_id=member_ids[0],
                right_id=member_ids[1],
                created_by_user_id=user_id,
            )
            message = "Marked pair as not duplicates."
        else:
            raise HTTPException(status_code=400, detail="Unknown proposal action")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    proposal.status = "applied"
    proposal.resolved_at = datetime.now(UTC)
    proposal.resolved_by_user_id = user_id
    session.add(proposal)
    session.commit()
    return CleanupAiProposalActionResponse(
        id=str(proposal.id),
        status="applied",
        message=message,
    )


@router.post(
    "/{stylebook_slug}/cleanup/ai-review/proposals/{proposal_id}/reject",
    response_model=CleanupAiProposalActionResponse,
)
def reject_cleanup_ai_proposal(
    stylebook_slug: str,
    proposal_id: str,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> CleanupAiProposalActionResponse:
    require_stylebook_edit_access(session, auth=auth, stylebook_slug=stylebook_slug)
    sb = require_stylebook_by_slug_in_auth_org(session, auth=auth, stylebook_slug=stylebook_slug)
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    proposal = session.get(StylebookCleanupAiProposal, proposal_id)
    if proposal is None or int(proposal.stylebook_id) != int(sb.id):
        raise HTTPException(status_code=404, detail="Proposal not found")
    if proposal.status != "pending":
        raise HTTPException(status_code=409, detail=f"Proposal is already {proposal.status}")
    proposal.status = "rejected"
    proposal.resolved_at = datetime.now(UTC)
    proposal.resolved_by_user_id = _created_by_user_id(auth)
    session.add(proposal)
    session.commit()
    return CleanupAiProposalActionResponse(
        id=str(proposal.id),
        status="rejected",
        message="Proposal rejected.",
    )
