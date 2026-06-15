"""GET /public/v1/projects/{project_slug}/organizations/{organization_id}/connections."""

from __future__ import annotations

from backfield_db import BackfieldProject
from backfield_entities.public.connections import (
    PublicConnectionOut,
    list_public_entity_connections,
)
from backfield_entities.public.organizations import get_public_organization
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session

from core_api.deps import get_session
from core_api.routers.public.deps import get_public_project
from core_api.routers.public.entities.organizations.helpers import (
    parse_organization_id,
    resolve_public_organizations_scope,
)

router = APIRouter()


class PublicOrganizationConnectionsOut(BaseModel):
    organization_id: str
    connections: list[PublicConnectionOut]


@router.get("/{organization_id}/connections", response_model=PublicOrganizationConnectionsOut)
def list_project_organization_connections(
    organization_id: str,
    project: BackfieldProject = Depends(get_public_project),
    session: Session = Depends(get_session),
) -> PublicOrganizationConnectionsOut:
    """Return Stylebook connections involving this canonical organization."""
    stylebook_id, project_id = resolve_public_organizations_scope(session, project)
    parsed_id = parse_organization_id(organization_id)
    organization = get_public_organization(
        session,
        stylebook_id=stylebook_id,
        project_id=project_id,
        organization_id=parsed_id,
    )
    if organization is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    connections = list_public_entity_connections(
        session,
        project_id=project_id,
        stylebook_id=stylebook_id,
        entity_type="organization",
        entity_id=parsed_id,
    )
    return PublicOrganizationConnectionsOut(
        organization_id=organization.id,
        connections=connections,
    )
