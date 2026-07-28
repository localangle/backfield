"""GET /public/v1/projects/{project_slug}/organizations/{organization_id}/connections."""

from __future__ import annotations

from backfield_db import BackfieldProject
from backfield_entities.public.connections import (
    PublicConnectionEntityType,
    PublicConnectionOut,
)
from backfield_entities.public.organizations import get_public_organization
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session

from core_api.deps import get_session
from core_api.routers.public.deps import get_public_project
from core_api.routers.public.entities.connections import public_entity_connections_response
from core_api.routers.public.entities.organizations.helpers import (
    parse_organization_id,
    resolve_public_organizations_scope,
)
from core_api.routers.public.schemas import PaginatedResponse

router = APIRouter()


@router.get(
    "/{organization_id}/connections",
    response_model=PaginatedResponse[PublicConnectionOut],
)
def list_project_organization_connections(
    organization_id: str,
    project: BackfieldProject = Depends(get_public_project),
    session: Session = Depends(get_session),
    to_entity_type: PublicConnectionEntityType | None = Query(None),
    nature: str | None = Query(None),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> PaginatedResponse[PublicConnectionOut]:
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
    return public_entity_connections_response(
        session,
        project_id=project_id,
        stylebook_id=stylebook_id,
        entity_type="organization",
        entity_id=parsed_id,
        to_entity_type=to_entity_type,
        nature=nature,
        limit=limit,
        offset=offset,
    )
