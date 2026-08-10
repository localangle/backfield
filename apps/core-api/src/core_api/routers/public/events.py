"""GET /public/v1/projects/{project_slug}/events — durable project event feed."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from backfield_db import BackfieldEvent, BackfieldProject

# Import from the package root so every DomainEvent subclass is registered
# before we validate type filters against the registry.
from backfield_events import event_type_is_registered
from backfield_events.contracts import envelope_from_event
from backfield_events.cursor import (
    EVENT_RETENTION_DAYS,
    CursorError,
    CursorExpiredError,
    decode_event_cursor,
    encode_event_cursor,
)
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlmodel import Session, col, select

from core_api.deps import get_session
from core_api.routers.public.deps import get_public_project

router = APIRouter(prefix="/projects/{project_slug}/events", tags=["public-events"])


class PublicEventFlowOut(BaseModel):
    id: str | None
    name: str | None


class PublicEventRunOut(BaseModel):
    id: str | None
    attempt: int | None
    url: str | None


class PublicEventLinksOut(BaseModel):
    run: str | None = None
    articles: str | None = None
    article: str | None = None
    entity: str | None = None


class PublicEventEntityOut(BaseModel):
    """Canonical entity scope for stylebook events."""

    type: str | None = None
    id: str | None = None


class PublicEventOut(BaseModel):
    """Versioned event envelope; ``data`` holds the type-specific payload."""

    id: str
    cursor: str
    type: str
    schema_version: int
    occurred_at: datetime
    flow: PublicEventFlowOut
    run: PublicEventRunOut
    article_id: int | None
    entity: PublicEventEntityOut
    data: dict[str, object]
    links: PublicEventLinksOut


class PublicEventsOut(BaseModel):
    items: list[PublicEventOut]
    next_cursor: str | None
    retention_days: int


def list_public_events(
    cursor: str | None = Query(
        default=None,
        description="Opaque forward cursor from a previous response item.",
    ),
    flow_id: list[str] | None = Query(
        default=None,
        description="Limit to events from these flows (repeatable).",
    ),
    type: list[str] | None = Query(
        default=None,
        description="Limit to these event types (repeatable), e.g. agate.run.completed.",
    ),
    limit: int = Query(default=25, ge=1, le=100),
    project: BackfieldProject = Depends(get_public_project),
    session: Session = Depends(get_session),
) -> PublicEventsOut:
    """Immutable, ascending project event feed retained for 90 days.

    Consumers recover missed webhook deliveries by replaying the feed from
    their last processed cursor. A cursor older than the retention window
    returns a ``cursor_expired`` error; restart without a cursor.
    """
    after_sequence = 0
    if cursor:
        try:
            after_sequence = decode_event_cursor(cursor)
        except CursorExpiredError as e:
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail=str(e),
            ) from e
        except CursorError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Malformed cursor",
            ) from e

    retention_floor = datetime.now(UTC) - timedelta(days=EVENT_RETENTION_DAYS)
    stmt = (
        select(BackfieldEvent)
        .where(
            BackfieldEvent.project_id == int(project.id),
            BackfieldEvent.is_test == False,  # noqa: E712
            col(BackfieldEvent.id) > after_sequence,
            col(BackfieldEvent.created_at) >= retention_floor,
        )
        .order_by(col(BackfieldEvent.id).asc())
        .limit(limit)
    )
    if flow_id:
        cleaned = [value.strip() for value in flow_id if value.strip()]
        if cleaned:
            stmt = stmt.where(col(BackfieldEvent.graph_id).in_(cleaned))
    if type:
        cleaned_types = [value.strip() for value in type if value.strip()]
        for event_type in cleaned_types:
            if not event_type_is_registered(event_type):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Unknown event type: {event_type}",
                )
        if cleaned_types:
            stmt = stmt.where(col(BackfieldEvent.event_type).in_(cleaned_types))

    events = list(session.exec(stmt).all())
    items: list[PublicEventOut] = []
    for event in events:
        envelope = envelope_from_event(event, project_slug=project.slug)
        created = event.created_at if event.created_at.tzinfo else event.created_at.replace(
            tzinfo=UTC
        )
        items.append(
            PublicEventOut(
                id=envelope.id,
                cursor=encode_event_cursor(sequence=int(event.id or 0), created_at=created),
                type=envelope.type,
                schema_version=envelope.schema_version,
                occurred_at=envelope.occurred_at,
                flow=PublicEventFlowOut(id=envelope.flow.id, name=envelope.flow.name),
                run=PublicEventRunOut(
                    id=envelope.run.id,
                    attempt=envelope.run.attempt,
                    url=envelope.run.url,
                ),
                article_id=event.article_id,
                entity=PublicEventEntityOut(type=event.entity_type, id=event.entity_id),
                data=envelope.data,
                links=PublicEventLinksOut(
                    run=envelope.links.run,
                    articles=envelope.links.articles,
                    article=envelope.links.article,
                    entity=envelope.links.entity,
                ),
            )
        )

    next_cursor = items[-1].cursor if items else None
    return PublicEventsOut(
        items=items,
        next_cursor=next_cursor,
        retention_days=EVENT_RETENTION_DAYS,
    )


router.get(
    "",
    response_model=PublicEventsOut,
    responses={
        410: {
            "description": "Cursor predates the event retention window.",
        }
    },
)(list_public_events)
