"""GET /public/v1/projects/{project_slug}/mentions/facets."""

from __future__ import annotations

from backfield_db import BackfieldProject
from backfield_entities.public.mentions import (
    PublicMentionFacetsOut,
    get_public_mention_facets,
)
from fastapi import APIRouter, Depends
from sqlmodel import Session

from core_api.deps import get_session
from core_api.routers.public.deps import get_public_project
from core_api.routers.public.mentions.helpers import resolve_public_mentions_scope

router = APIRouter()


@router.get("/facets", response_model=PublicMentionFacetsOut)
def get_project_mention_facets(
    project: BackfieldProject = Depends(get_public_project),
    session: Session = Depends(get_session),
) -> PublicMentionFacetsOut:
    """Return distinct entity types, natures, and type values for mention search filters."""
    return get_public_mention_facets(
        session,
        project_id=resolve_public_mentions_scope(project),
    )
