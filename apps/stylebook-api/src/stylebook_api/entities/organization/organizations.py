"""Project-scoped substrate organizations (Stylebook review, ``project_slug``)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from backfield_auth.gate import require_project_access
from backfield_db import SubstrateOrganization
from backfield_entities.entities.organization.persist import (
    link_substrate_to_canonical_atomic,
    unlink_substrate_from_canonical,
)
from backfield_entities.entities.organization.types import (
    ORGANIZATION_NATURE_VALUES,
    normalize_organization_type,
    organization_identity_fingerprint,
)
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, col, select

from stylebook_api.catalog_scope import StylebookSlugQuery
from stylebook_api.deps import get_auth, get_session
from stylebook_api.helpers.project_scope import project_by_slug, require_stylebook_id

router = APIRouter(prefix="/v1", tags=["organizations"])


def _project_by_slug(session: Session, slug: str):
    return project_by_slug(session, slug)


def _require_stylebook_id(
    session: Session,
    project,
    stylebook_slug: str | None = None,
) -> int:
    return require_stylebook_id(session, project, stylebook_slug=stylebook_slug)


class LinkCanonicalBody(BaseModel):
    stylebook_organization_canonical_id: UUID


class LinkCanonicalResponse(BaseModel):
    changed: bool


def _manual_organization_type(value: str | None) -> str | None:
    return normalize_organization_type(value)


@router.post("/organizations/{organization_id}/unlink-canonical")
def unlink_substrate_from_canonical_route(
    organization_id: int,
    project_slug: str = Query(...),
    stylebook_slug: StylebookSlugQuery = None,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> dict[str, str]:
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    stylebook_id = _require_stylebook_id(session, proj, stylebook_slug)
    organization = session.get(SubstrateOrganization, organization_id)
    if organization is None or int(organization.project_id) != int(proj.id):
        raise HTTPException(status_code=404, detail="Organization not found")
    try:
        unlink_substrate_from_canonical(
            session,
            stylebook_id=stylebook_id,
            organization=organization,
            provenance="stylebook_ui_unlink",
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    session.commit()
    return {"message": "unlinked"}


@router.post(
    "/organizations/{organization_id}/link-canonical",
    response_model=LinkCanonicalResponse,
)
def link_substrate_to_canonical_route(
    organization_id: int,
    body: LinkCanonicalBody,
    project_slug: str = Query(...),
    stylebook_slug: StylebookSlugQuery = None,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> LinkCanonicalResponse:
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    stylebook_id = _require_stylebook_id(session, proj, stylebook_slug)
    organization = session.get(SubstrateOrganization, organization_id)
    if organization is None or int(organization.project_id) != int(proj.id):
        raise HTTPException(status_code=404, detail="Organization not found")
    try:
        changed = link_substrate_to_canonical_atomic(
            session,
            stylebook_id=stylebook_id,
            organization=organization,
            target_canonical_id=str(body.stylebook_organization_canonical_id),
            provenance="stylebook_ui_link",
        )
    except ValueError as e:
        msg = str(e)
        if "not in this stylebook" in msg:
            raise HTTPException(status_code=400, detail=msg) from e
        raise HTTPException(status_code=409, detail=msg) from e
    session.commit()
    return LinkCanonicalResponse(changed=changed)


def _normalize_organization_name(name: str) -> str:
    return " ".join(name.strip().lower().split())


class SubstrateOrganizationResponse(BaseModel):
    id: int
    name: str
    organization_type: str | None = None
    status: str
    canonical_link_status: str | None = None
    stylebook_organization_canonical_id: str | None = None


@router.get("/organizations/{organization_id}", response_model=SubstrateOrganizationResponse)
def get_substrate_organization(
    organization_id: int,
    project_slug: str = Query(...),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> SubstrateOrganizationResponse:
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    organization = session.get(SubstrateOrganization, organization_id)
    if organization is None or int(organization.project_id) != int(proj.id):
        raise HTTPException(status_code=404, detail="Organization not found")
    return SubstrateOrganizationResponse(
        id=int(organization.id),  # type: ignore[arg-type]
        name=str(organization.name),
        organization_type=organization.organization_type,
        status=str(organization.status),
        canonical_link_status=str(organization.canonical_link_status or ""),
        stylebook_organization_canonical_id=organization.stylebook_organization_canonical_id,
    )


class PatchSubstrateOrganizationBody(BaseModel):
    name: str | None = None
    organization_type: str | None = None
    role_in_story: str | None = None
    nature: str | None = None
    nature_secondary_tags: list[str] | None = None


@router.patch("/organizations/{organization_id}", response_model=SubstrateOrganizationResponse)
def patch_substrate_organization(
    organization_id: int,
    body: PatchSubstrateOrganizationBody,
    project_slug: str = Query(...),
    article_id: int | None = Query(None, ge=1),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> SubstrateOrganizationResponse:
    """Update a substrate organization (and optional article mention editorial fields)."""
    from backfield_db import SubstrateOrganizationMention

    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    organization = session.get(SubstrateOrganization, organization_id)
    if organization is None or int(organization.project_id) != int(proj.id):
        raise HTTPException(status_code=404, detail="Organization not found")

    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="name cannot be empty")
        organization.name = name
        organization.normalized_name = _normalize_organization_name(name)
    if body.organization_type is not None:
        organization.organization_type = _manual_organization_type(
            body.organization_type.strip() or None
        )

    organization.identity_fingerprint = organization_identity_fingerprint(
        normalized_name=str(organization.normalized_name),
        organization_type=organization.organization_type,
    )
    session.add(organization)

    if article_id is not None:
        mention = session.exec(
            select(SubstrateOrganizationMention).where(
                SubstrateOrganizationMention.article_id == article_id,
                SubstrateOrganizationMention.organization_id == organization_id,
                col(SubstrateOrganizationMention.deleted).is_(False),
            )
        ).first()
        if mention is not None:
            if body.role_in_story is not None:
                mention.role_in_story = body.role_in_story.strip() or None
            if body.nature is not None:
                nature = body.nature.strip().lower()
                mention.nature = nature if nature in ORGANIZATION_NATURE_VALUES else "other"
            if body.nature_secondary_tags is not None:
                tags = [
                    t.strip().lower()
                    for t in body.nature_secondary_tags
                    if isinstance(t, str) and t.strip()
                ]
                mention.nature_secondary_tags_json = [
                    t for t in tags if t in ORGANIZATION_NATURE_VALUES
                ] or None
            mention.edited = True
            session.add(mention)

    session.commit()
    session.refresh(organization)
    return SubstrateOrganizationResponse(
        id=int(organization.id),  # type: ignore[arg-type]
        name=str(organization.name),
        organization_type=organization.organization_type,
        status=str(organization.status),
        canonical_link_status=str(organization.canonical_link_status or ""),
        stylebook_organization_canonical_id=organization.stylebook_organization_canonical_id,
    )
