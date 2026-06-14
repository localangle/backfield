"""GET /public/v1/projects/{project_slug}/mentions/{entity_type}/{mention_id}."""

from __future__ import annotations

from backfield_db import BackfieldProject
from backfield_entities.public.article_hub import PublicEntityMentionType
from backfield_entities.public.mentions import PublicMentionDetailOut, get_public_mention
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from core_api.deps import get_session
from core_api.routers.public.deps import get_public_project
from core_api.routers.public.mentions.helpers import resolve_public_mentions_scope

router = APIRouter()


def _parse_entity_type_path(value: str) -> PublicEntityMentionType:
    normalized = value.strip().lower()
    if normalized not in ("location", "person", "organization"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mention not found")
    return normalized  # type: ignore[return-value]


@router.get("/{entity_type}/{mention_id}", response_model=PublicMentionDetailOut)
def get_project_mention(
    entity_type: str,
    mention_id: int,
    project: BackfieldProject = Depends(get_public_project),
    session: Session = Depends(get_session),
) -> PublicMentionDetailOut:
    """Return one mention with full occurrence evidence and article context."""
    typed_entity = _parse_entity_type_path(entity_type)
    item = get_public_mention(
        session,
        project_id=resolve_public_mentions_scope(project),
        entity_type=typed_entity,
        mention_id=mention_id,
    )
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mention not found")
    return item
