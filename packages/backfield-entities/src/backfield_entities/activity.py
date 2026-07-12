"""Stylebook activity event taxonomy and write helpers."""

from __future__ import annotations

import logging
from typing import Any, Literal

from backfield_db import StylebookActivity
from sqlmodel import Session

logger = logging.getLogger(__name__)

ActorType = Literal["user", "system", "agent"]
ActivitySource = Literal[
    "manual_ui",
    "cleanup_check",
    "cleanup_ai",
    "candidate_ai",
    "ingest_pipeline",
    "connections",
    "system",
]
EntityType = Literal["location", "person", "organization", "check", "connection", "stylebook"]

EVENT_CANONICAL_CREATED = "canonical_created"
EVENT_CANONICAL_UPDATED = "canonical_updated"
EVENT_CANONICAL_DELETED = "canonical_deleted"
EVENT_CANONICAL_MERGED = "canonical_merged"
EVENT_SUBSTRATE_LINKED = "substrate_linked"
EVENT_SUBSTRATE_UNLINKED = "substrate_unlinked"
EVENT_CONNECTION_CREATED = "connection_created"
EVENT_CONNECTION_UPDATED = "connection_updated"
EVENT_CONNECTION_DELETED = "connection_deleted"
EVENT_CLEANUP_KEEP = "cleanup_keep"
EVENT_CLEANUP_KEEP_SEPARATE = "cleanup_keep_separate"
EVENT_CLEANUP_DELETE = "cleanup_delete"
EVENT_CLEANUP_MERGE = "cleanup_merge"
EVENT_AI_REVIEW_STARTED = "ai_review_started"
EVENT_AI_REVIEW_COMPLETED = "ai_review_completed"
EVENT_AI_REVIEW_APPLIED = "ai_review_applied"


def log_stylebook_activity(
    session: Session,
    *,
    stylebook_id: int,
    source: ActivitySource | str,
    event_type: str,
    actor_type: ActorType | str = "system",
    actor_user_id: int | None = None,
    project_id: int | None = None,
    entity_type: EntityType | str | None = None,
    entity_id: str | None = None,
    entity_label: str | None = None,
    related_entity_type: EntityType | str | None = None,
    related_entity_id: str | None = None,
    related_entity_label: str | None = None,
    payload_json: dict[str, Any] | None = None,
) -> StylebookActivity:
    row = StylebookActivity(
        stylebook_id=int(stylebook_id),
        project_id=int(project_id) if project_id is not None else None,
        actor_type=str(actor_type),
        actor_user_id=int(actor_user_id) if actor_user_id is not None else None,
        source=str(source),
        event_type=str(event_type),
        entity_type=str(entity_type) if entity_type is not None else None,
        entity_id=str(entity_id) if entity_id is not None else None,
        entity_label=str(entity_label) if entity_label is not None else None,
        related_entity_type=(
            str(related_entity_type) if related_entity_type is not None else None
        ),
        related_entity_id=str(related_entity_id) if related_entity_id is not None else None,
        related_entity_label=(
            str(related_entity_label) if related_entity_label is not None else None
        ),
        payload_json=payload_json,
    )
    session.add(row)
    return row


def log_stylebook_activity_safe(session: Session, **kwargs: Any) -> None:
    try:
        log_stylebook_activity(session, **kwargs)
    except Exception:
        logger.warning(
            "Failed to append stylebook activity event",
            exc_info=True,
            extra={
                "stylebook_id": kwargs.get("stylebook_id"),
                "event_type": kwargs.get("event_type"),
                "source": kwargs.get("source"),
            },
        )
