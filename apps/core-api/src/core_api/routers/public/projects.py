"""Public project metadata routes."""

from __future__ import annotations

from backfield_db import BackfieldProject, Stylebook
from backfield_entities.catalog.resolve import resolve_effective_stylebook_id_for_project
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session

from core_api.deps import get_session
from core_api.routers.public.deps import get_public_project

router = APIRouter(prefix="/projects", tags=["public-projects"])


class PublicProjectOut(BaseModel):
    id: int
    name: str
    slug: str
    stylebook_slug: str | None = None
    stylebook_name: str | None = None


def _stylebook_fields_for_project(
    session: Session, project: BackfieldProject
) -> tuple[str | None, str | None]:
    try:
        stylebook_id = resolve_effective_stylebook_id_for_project(session, project)
    except LookupError:
        return None, None
    stylebook = session.get(Stylebook, stylebook_id)
    if stylebook is None:
        return None, None
    return stylebook.slug, stylebook.name


@router.get("/{project_slug}", response_model=PublicProjectOut)
def get_public_project_metadata(
    project: BackfieldProject = Depends(get_public_project),
    session: Session = Depends(get_session),
) -> PublicProjectOut:
    """Return minimal project metadata for a public API consumer."""
    stylebook_slug, stylebook_name = _stylebook_fields_for_project(session, project)
    return PublicProjectOut(
        id=int(project.id),  # type: ignore[arg-type]
        name=project.name,
        slug=project.slug,
        stylebook_slug=stylebook_slug,
        stylebook_name=stylebook_name,
    )
