"""GET /public/v1/projects/{project_slug}/organizations/{organization_id}."""

from __future__ import annotations

from backfield_db import BackfieldProject
from backfield_entities.public.organizations import PublicOrganizationOut, get_public_organization
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from core_api.deps import get_session
from core_api.routers.public.deps import get_public_project
from core_api.routers.public.entities.organizations.helpers import (
    parse_organization_id,
    resolve_public_organizations_scope,
)

router = APIRouter()


@router.get("/{organization_id}", response_model=PublicOrganizationOut)
def get_project_organization(
    organization_id: str,
    project: BackfieldProject = Depends(get_public_project),
    session: Session = Depends(get_session),
) -> PublicOrganizationOut:
    """Return one canonical organization by UUID."""
    stylebook_id, project_id = resolve_public_organizations_scope(session, project)
    organization = get_public_organization(
        session,
        stylebook_id=stylebook_id,
        project_id=project_id,
        organization_id=parse_organization_id(organization_id),
    )
    if organization is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return organization
