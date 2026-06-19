"""Stylebook candidate queue AI review endpoints."""

from __future__ import annotations

import os
import uuid
from datetime import datetime
from typing import Any, Literal

from backfield_auth.gate import require_project_access
from backfield_db import BackfieldAiModelConfig, BackfieldProject, StylebookCandidateAiReview
from backfield_entities.catalog.candidate_ai_review import count_open_candidates_for_review
from celery import Celery
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import Session, col, select

from stylebook_api.deps import get_auth, get_session
from stylebook_api.helpers.project_scope import project_by_slug as _project_by_slug
from stylebook_api.stylebook_permissions import require_stylebook_edit_access
from stylebook_api.stylebook_scope import require_stylebook_by_slug_in_auth_org

router = APIRouter(prefix="/v1/stylebooks", tags=["stylebook-candidates"])

celery_app = Celery(
    "agate_worker",
    broker=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
)

CandidateEntityType = Literal["person", "organization", "location"]


def _celery_queue() -> str:
    return str(os.environ.get("CELERY_QUEUE", "agate"))


def _created_by_user_id(auth: dict[str, Any]) -> int | None:
    if auth.get("type") != "session" or auth.get("user") is None:
        return None
    return int(auth["user"].id)  # type: ignore[union-attr]


class CandidateAiModelOut(BaseModel):
    id: str
    name: str
    provider_model_id: str


class CandidateAiModelsResponse(BaseModel):
    models: list[CandidateAiModelOut]


class StartCandidateAiReviewBody(BaseModel):
    entity_type: CandidateEntityType
    project_slug: str = Field(min_length=1)
    provider_model_id: str = Field(min_length=1)
    ai_model_config_id: str | None = None


class CandidateAiReviewOut(BaseModel):
    id: str
    stylebook_id: int
    project_id: int
    entity_type: str
    status: str
    provider_model_id: str
    ai_model_config_id: str | None = None
    candidate_count: int = 0
    processed_count: int = 0
    recommendation_count: int = 0
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_row(cls, row: StylebookCandidateAiReview) -> CandidateAiReviewOut:
        return cls(
            id=str(row.id),
            stylebook_id=int(row.stylebook_id),
            project_id=int(row.project_id),
            entity_type=str(row.entity_type),
            status=str(row.status),
            provider_model_id=str(row.provider_model_id),
            ai_model_config_id=row.ai_model_config_id,
            candidate_count=int(row.candidate_count),
            processed_count=int(row.processed_count),
            recommendation_count=int(row.recommendation_count),
            error_message=row.error_message,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


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


def _require_project_in_stylebook_org(
    session: Session,
    *,
    project_slug: str,
    organization_id: int,
    auth: dict[str, Any],
) -> BackfieldProject:
    proj = _project_by_slug(session, project_slug)
    if int(proj.organization_id) != organization_id:
        raise HTTPException(status_code=400, detail="Project is not in this organization")
    require_project_access(session, auth, int(proj.id))
    return proj


@router.get("/{stylebook_slug}/candidates/ai-models", response_model=CandidateAiModelsResponse)
def list_candidate_ai_models(
    stylebook_slug: str,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> CandidateAiModelsResponse:
    sb = require_stylebook_by_slug_in_auth_org(session, auth=auth, stylebook_slug=stylebook_slug)
    rows = session.exec(
        select(BackfieldAiModelConfig)
        .where(
            BackfieldAiModelConfig.organization_id == int(sb.organization_id),
            BackfieldAiModelConfig.status == "active",
        )
        .order_by(BackfieldAiModelConfig.name)
    ).all()
    models: list[CandidateAiModelOut] = []
    for row in rows:
        caps = row.capabilities_json if isinstance(row.capabilities_json, list) else []
        cap_set = {str(cap).strip().lower() for cap in caps}
        if cap_set and not (cap_set & {"text", "json"}):
            continue
        if row.id is None:
            continue
        models.append(
            CandidateAiModelOut(
                id=str(row.id),
                name=str(row.name),
                provider_model_id=str(row.provider_model_id),
            )
        )
    return CandidateAiModelsResponse(models=models)


@router.post("/{stylebook_slug}/candidates/ai-review", response_model=CandidateAiReviewOut)
def start_candidate_ai_review(
    stylebook_slug: str,
    body: StartCandidateAiReviewBody,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> CandidateAiReviewOut:
    require_stylebook_edit_access(session, auth=auth, stylebook_slug=stylebook_slug)
    sb = require_stylebook_by_slug_in_auth_org(session, auth=auth, stylebook_slug=stylebook_slug)
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    proj = _require_project_in_stylebook_org(
        session,
        project_slug=body.project_slug.strip(),
        organization_id=int(sb.organization_id),
        auth=auth,
    )
    _validate_model_selection(
        session,
        organization_id=int(sb.organization_id),
        provider_model_id=body.provider_model_id,
        ai_model_config_id=body.ai_model_config_id,
    )
    review = StylebookCandidateAiReview(
        id=str(uuid.uuid4()),
        stylebook_id=int(sb.id),
        project_id=int(proj.id),  # type: ignore[arg-type]
        entity_type=body.entity_type,
        status="queued",
        provider_model_id=body.provider_model_id.strip(),
        ai_model_config_id=body.ai_model_config_id,
        created_by_user_id=_created_by_user_id(auth),
        candidate_count=count_open_candidates_for_review(
            session,
            entity_type=body.entity_type,
            project_id=int(proj.id),  # type: ignore[arg-type]
        ),
    )
    session.add(review)
    session.commit()
    session.refresh(review)
    celery_app.send_task(
        "worker.tasks.execute_candidate_ai_review",
        args=[str(review.id)],
        queue=_celery_queue(),
    )
    return CandidateAiReviewOut.from_row(review)


@router.get(
    "/{stylebook_slug}/candidates/ai-review/latest",
    response_model=CandidateAiReviewOut | None,
)
def get_latest_candidate_ai_review(
    stylebook_slug: str,
    entity_type: CandidateEntityType = Query(),
    project_slug: str = Query(min_length=1),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> CandidateAiReviewOut | None:
    sb = require_stylebook_by_slug_in_auth_org(session, auth=auth, stylebook_slug=stylebook_slug)
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    proj = _require_project_in_stylebook_org(
        session,
        project_slug=project_slug.strip(),
        organization_id=int(sb.organization_id),
        auth=auth,
    )
    row = session.exec(
        select(StylebookCandidateAiReview)
        .where(
            StylebookCandidateAiReview.stylebook_id == int(sb.id),
            StylebookCandidateAiReview.project_id == int(proj.id),  # type: ignore[arg-type]
            StylebookCandidateAiReview.entity_type == entity_type,
        )
        .order_by(col(StylebookCandidateAiReview.created_at).desc())
        .limit(1)
    ).first()
    if row is None:
        return None
    return CandidateAiReviewOut.from_row(row)


@router.get(
    "/{stylebook_slug}/candidates/ai-review/{review_id}",
    response_model=CandidateAiReviewOut,
)
def get_candidate_ai_review(
    stylebook_slug: str,
    review_id: str,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> CandidateAiReviewOut:
    sb = require_stylebook_by_slug_in_auth_org(session, auth=auth, stylebook_slug=stylebook_slug)
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    review = session.get(StylebookCandidateAiReview, review_id)
    if review is None or int(review.stylebook_id) != int(sb.id):
        raise HTTPException(status_code=404, detail="Review not found")
    return CandidateAiReviewOut.from_row(review)
