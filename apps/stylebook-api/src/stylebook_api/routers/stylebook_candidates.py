"""Combined candidate inboxes for projects assigned to a Stylebook."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

from backfield_db import (
    BackfieldProject,
    SubstrateLocation,
    SubstrateOrganization,
    SubstratePerson,
)
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, or_
from sqlmodel import Session, col, func, select

from stylebook_api.deps import get_auth, get_session
from stylebook_api.entities.location import candidates as location_candidates
from stylebook_api.entities.organization import candidates as organization_candidates
from stylebook_api.entities.person import candidates as person_candidates
from stylebook_api.stylebook_scope import (
    optional_project_filter_to_ids,
    require_stylebook_by_slug_in_auth_org,
)

router = APIRouter(prefix="/v1/stylebooks", tags=["stylebook-candidates"])

CandidateEntityType = Literal["locations", "people", "organizations"]


class CandidateProjectCount(BaseModel):
    project_id: int
    project_slug: str
    project_name: str
    count: int


class CandidateCountResponse(BaseModel):
    total: int
    projects: list[CandidateProjectCount]


class PaginatedCandidatesResponse(BaseModel):
    candidates: list[dict[str, Any]]
    total: int
    has_next: bool
    has_prev: bool


class CandidateTypesResponse(BaseModel):
    types: list[str]


def _candidate_spec(
    entity_type: CandidateEntityType,
) -> tuple[type[Any], Callable[..., list[Any]], Callable[[Any], dict[str, Any]], Any]:
    if entity_type == "locations":
        return (
            SubstrateLocation,
            location_candidates.open_candidate_filters,
            location_candidates.serialize_candidate,
            col(SubstrateLocation.normalized_name),
        )
    if entity_type == "people":
        return (
            SubstratePerson,
            person_candidates.open_candidate_filters,
            person_candidates.serialize_candidate,
            person_candidates.candidate_sort_key(),
        )
    return (
        SubstrateOrganization,
        organization_candidates.open_candidate_filters,
        organization_candidates.serialize_candidate,
        organization_candidates.candidate_sort_key(),
    )


def _candidate_filters(
    *,
    entity_type: CandidateEntityType,
    project_ids: list[int],
    status: str,
    q: str | None,
    type_filter: str | None,
    needs_review: bool | None,
) -> tuple[type[Any], list[Any], Callable[[Any], dict[str, Any]], Any]:
    model, open_filters, serializer, sort_column = _candidate_spec(entity_type)
    if not project_ids:
        return model, [col(model.id).is_(None)], serializer, sort_column
    filter_builder = (
        {
            "locations": location_candidates.deferred_candidate_filters,
            "people": person_candidates.deferred_candidate_filters,
            "organizations": organization_candidates.deferred_candidate_filters,
        }[entity_type]
        if status == "deferred"
        else open_filters
    )
    project_filters = []
    for project_id in project_ids:
        kwargs: dict[str, Any] = {"q": q, "type_filter": type_filter}
        if status == "open":
            kwargs["needs_review"] = needs_review
        project_filters.append(and_(*filter_builder(project_id, **kwargs)))
    return model, [or_(*project_filters)], serializer, sort_column


def _scope(
    session: Session,
    *,
    auth: dict[str, Any],
    stylebook_slug: str,
    project_slug: str | None,
) -> tuple[list[int], dict[int, BackfieldProject]]:
    stylebook = require_stylebook_by_slug_in_auth_org(
        session,
        auth=auth,
        stylebook_slug=stylebook_slug,
    )
    assert stylebook.id is not None
    project_ids = optional_project_filter_to_ids(
        session,
        auth=auth,
        project_slug=project_slug,
        organization_id=int(stylebook.organization_id),
        stylebook_id=int(stylebook.id),
    )
    projects = {
        int(project.id): project
        for project in session.exec(
            select(BackfieldProject).where(col(BackfieldProject.id).in_(project_ids))
        ).all()
        if project.id is not None
    }
    return project_ids, projects


def _validate_status(status: str) -> None:
    if status not in ("open", "deferred"):
        raise HTTPException(status_code=400, detail="Only status=open or deferred is supported")


@router.get(
    "/{stylebook_slug}/candidates/{entity_type}",
    response_model=PaginatedCandidatesResponse,
)
def list_candidates(
    stylebook_slug: str,
    entity_type: CandidateEntityType,
    project_slug: str | None = Query(None),
    status: str = Query("open"),
    q: str | None = Query(None),
    type_filter: str | None = Query(None),
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
    needs_review: bool | None = Query(None),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> PaginatedCandidatesResponse:
    _validate_status(status)
    project_ids, projects = _scope(
        session,
        auth=auth,
        stylebook_slug=stylebook_slug,
        project_slug=project_slug,
    )
    model, filters, serializer, sort_column = _candidate_filters(
        entity_type=entity_type,
        project_ids=project_ids,
        status=status,
        q=q,
        type_filter=type_filter,
        needs_review=needs_review,
    )
    total = int(session.scalar(select(func.count()).select_from(model).where(*filters)) or 0)
    rows = session.exec(
        select(model)
        .where(*filters)
        .order_by(sort_column.asc(), col(model.id).asc())
        .offset(offset)
        .limit(limit)
    ).all()
    candidates: list[dict[str, Any]] = []
    for row in rows:
        project = projects[int(row.project_id)]
        payload = serializer(row)
        payload.update(project_slug=project.slug, project_name=project.name)
        candidates.append(payload)
    return PaginatedCandidatesResponse(
        candidates=candidates,
        total=total,
        has_next=offset + len(candidates) < total,
        has_prev=offset > 0,
    )


@router.get(
    "/{stylebook_slug}/candidates/{entity_type}/count",
    response_model=CandidateCountResponse,
)
def count_candidates(
    stylebook_slug: str,
    entity_type: CandidateEntityType,
    project_slug: str | None = Query(None),
    status: str = Query("open"),
    q: str | None = Query(None),
    type_filter: str | None = Query(None),
    needs_review: bool | None = Query(None),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> CandidateCountResponse:
    _validate_status(status)
    project_ids, projects = _scope(
        session,
        auth=auth,
        stylebook_slug=stylebook_slug,
        project_slug=project_slug,
    )
    model, filters, _, _ = _candidate_filters(
        entity_type=entity_type,
        project_ids=project_ids,
        status=status,
        q=q,
        type_filter=type_filter,
        needs_review=needs_review,
    )
    rows = session.exec(
        select(model.project_id, func.count())
        .where(*filters)
        .group_by(model.project_id)
    ).all()
    counts_by_project = {int(project_id): int(count) for project_id, count in rows}
    project_counts = [
        CandidateProjectCount(
            project_id=project_id,
            project_slug=project.slug,
            project_name=project.name,
            count=counts_by_project.get(project_id, 0),
        )
        for project_id, project in sorted(projects.items(), key=lambda item: item[1].name.lower())
    ]
    return CandidateCountResponse(
        total=sum(project.count for project in project_counts),
        projects=project_counts,
    )


@router.get(
    "/{stylebook_slug}/candidates/{entity_type}/types",
    response_model=CandidateTypesResponse,
)
def list_candidate_types(
    stylebook_slug: str,
    entity_type: CandidateEntityType,
    project_slug: str | None = Query(None),
    status: str = Query("open"),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> CandidateTypesResponse:
    _validate_status(status)
    project_ids, _ = _scope(
        session,
        auth=auth,
        stylebook_slug=stylebook_slug,
        project_slug=project_slug,
    )
    model, filters, _, _ = _candidate_filters(
        entity_type=entity_type,
        project_ids=project_ids,
        status=status,
        q=None,
        type_filter=None,
        needs_review=None,
    )
    type_column = {
        "locations": SubstrateLocation.location_type,
        "people": SubstratePerson.person_type,
        "organizations": SubstrateOrganization.organization_type,
    }[entity_type]
    rows = session.exec(
        select(func.distinct(type_column)).where(
            *filters,
            col(type_column).is_not(None),
            func.length(func.trim(type_column)) > 0,
        )
    ).all()
    return CandidateTypesResponse(
        types=sorted({str(value).strip() for value in rows if value is not None})
    )
