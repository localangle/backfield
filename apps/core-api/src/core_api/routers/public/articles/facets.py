"""GET /public/v1/projects/{project_slug}/articles/facets."""

from __future__ import annotations

from backfield_db import BackfieldProject
from backfield_entities.public.article_facets import (
    PublicArticleFacetsOut,
    get_public_article_facets,
)
from fastapi import APIRouter, Depends
from sqlmodel import Session

from core_api.deps import get_session
from core_api.routers.public.deps import get_public_project

router = APIRouter()


@router.get("/facets", response_model=PublicArticleFacetsOut)
def get_project_article_facets(
    project: BackfieldProject = Depends(get_public_project),
    session: Session = Depends(get_session),
) -> PublicArticleFacetsOut:
    """Return distinct authors, sources, and metadata categories for search filters."""
    return get_public_article_facets(
        session,
        project_id=int(project.id),  # type: ignore[arg-type]
    )
