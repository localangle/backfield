"""Helpers for manual-edit semantic re-index enqueue (Issue 8)."""

from __future__ import annotations

from typing import Any

from backfield_db import SubstrateLocationMention, SubstratePersonMention
from sqlmodel import Session, col, select

from backfield_stylebook.semantic_indexing.contracts import SemanticBuilderEntityType
from backfield_stylebook.semantic_indexing.reindex_contract import SemanticReindexScope

_PERSON_ENTITY_PATCH_FIELDS = frozenset(
    {"name", "title", "affiliation", "public_figure", "person_type", "sort_key"}
)
_PERSON_MENTION_PATCH_FIELDS = frozenset({"role_in_story", "nature", "nature_secondary_tags"})
_LOCATION_ENTITY_PATCH_FIELDS = frozenset({"name", "location_type", "formatted_address"})


def person_patch_affects_semantic_index(body: Any) -> bool:
    """True when a person PATCH body can change semantic document content."""
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        return False
    if set(fields.keys()) & (_PERSON_ENTITY_PATCH_FIELDS | _PERSON_MENTION_PATCH_FIELDS):
        if set(fields.keys()) == {"sort_key"}:
            return False
        return True
    return False


def person_patch_entity_fields_changed(body: Any) -> bool:
    fields = body.model_dump(exclude_unset=True)
    if "name" in fields:
        return True
    return bool(set(fields.keys()) & (_PERSON_ENTITY_PATCH_FIELDS - {"sort_key"}))


def location_patch_affects_semantic_index(body: Any) -> bool:
    """True when a location PATCH body can change semantic document content."""
    fields = body.model_dump(exclude_unset=True)
    return bool(set(fields.keys()) & _LOCATION_ENTITY_PATCH_FIELDS)


def active_article_ids_for_person(session: Session, *, person_id: int) -> list[int]:
    rows = session.exec(
        select(SubstratePersonMention.article_id).where(
            SubstratePersonMention.person_id == person_id,
            col(SubstratePersonMention.deleted).is_(False),
        )
    ).all()
    return sorted({int(row) for row in rows})


def active_article_ids_for_location(session: Session, *, location_id: int) -> list[int]:
    rows = session.exec(
        select(SubstrateLocationMention.article_id).where(
            SubstrateLocationMention.location_id == location_id,
            col(SubstrateLocationMention.deleted).is_(False),
        )
    ).all()
    return sorted({int(row) for row in rows})


def semantic_reindex_scopes_for_entity(
    session: Session,
    *,
    project_id: int,
    entity_type: SemanticBuilderEntityType,
    entity_id: int,
    article_id: int | None = None,
) -> tuple[SemanticReindexScope, ...]:
    """Build article scopes for one entity; optional single-article filter."""
    if article_id is not None:
        return (
            SemanticReindexScope(
                project_id=project_id,
                article_id=article_id,
                entity_type=entity_type,
            ),
        )
    if entity_type == "person":
        article_ids = active_article_ids_for_person(session, person_id=entity_id)
    else:
        article_ids = active_article_ids_for_location(session, location_id=entity_id)
    return tuple(
        SemanticReindexScope(
            project_id=project_id,
            article_id=aid,
            entity_type=entity_type,
        )
        for aid in article_ids
    )
