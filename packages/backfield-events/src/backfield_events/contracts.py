"""Versioned event envelope and payload contracts."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Literal

from backfield_db import BackfieldEvent
from pydantic import BaseModel

from backfield_events.config import public_api_base_url

EVENT_SCHEMA_VERSION = 1

RUN_COMPLETED_EVENT = "agate.run.completed"
ARTICLE_CREATED_EVENT = "agate.article.created"
ARTICLE_UPDATED_EVENT = "agate.article.updated"
CANONICAL_CREATED_EVENT = "stylebook.canonical.created"
CANONICAL_UPDATED_EVENT = "stylebook.canonical.updated"
CANONICAL_DELETED_EVENT = "stylebook.canonical.deleted"
CANONICAL_MERGED_EVENT = "stylebook.canonical.merged"
CANONICAL_EVIDENCE_CHANGED_EVENT = "stylebook.canonical.evidence.changed"
#: Synthetic verification event; delivery-only, never enters the public feed.
WEBHOOK_TEST_EVENT = "backfield.webhook.test"

RunOutcome = Literal["succeeded", "failed"]
CompletionReason = Literal["completed", "error", "cancelled"]

#: Why an article.updated event fired.
ArticleChange = Literal["reprocessed", "metadata"]

#: ``backfield_event.entity_type`` values for canonical events.
CanonicalEntityType = Literal["location", "person", "organization"]


class RunCompletedCounts(BaseModel):
    total: int
    succeeded: int
    failed: int


class RunCompletedData(BaseModel):
    """Typed payload stored in ``backfield_event.payload_json`` for run completion."""

    outcome: RunOutcome
    completion_reason: CompletionReason
    #: Normalized failure category (never raw provider error text); None on success.
    failure_category: str | None = None
    counts: RunCompletedCounts
    article_count: int


class ArticleCreatedData(BaseModel):
    """Payload for ``agate.article.created``."""

    headline: str | None = None


class ArticleUpdatedData(BaseModel):
    """Payload for ``agate.article.updated``.

    ``reprocessed`` fires on every re-persistence even when nothing changed
    (consumers alerting on "your article was reprocessed" depend on that);
    ``content_changed`` lets consumers filter for substantive edits.
    """

    headline: str | None = None
    change: ArticleChange
    content_changed: bool | None = None


class CanonicalEventData(BaseModel):
    """Payload for ``stylebook.canonical.created|updated|deleted``."""

    label: str | None = None


class CanonicalMergedData(BaseModel):
    """Payload for ``stylebook.canonical.merged``.

    The event's entity scope is the source canonical (the ID consumers may
    hold, which no longer resolves); ``merged_into`` carries the surviving
    target.
    """

    label: str | None = None
    merged_into: str


class CanonicalEvidenceChangedData(BaseModel):
    """Payload for ``stylebook.canonical.evidence.changed``.

    Coalesced per canonical per transaction; ``change`` reflects the first
    recorded cause when several occur together.
    """

    label: str | None = None
    change: str


class EventFlowRef(BaseModel):
    id: str | None
    name: str | None


class EventRunRef(BaseModel):
    id: str | None
    attempt: int | None
    url: str | None


class EventLinks(BaseModel):
    run: str | None = None
    articles: str | None = None
    article: str | None = None
    entity: str | None = None


#: Maps ``backfield_event.entity_type`` to its public route segment.
ENTITY_PATH_SEGMENTS = {
    "location": "locations",
    "person": "people",
    "organization": "organizations",
}


class EventEnvelope(BaseModel):
    """The versioned representation shared by webhook bodies and the event feed."""

    id: str
    sequence: int
    type: str
    schema_version: int
    occurred_at: datetime
    project: str
    flow: EventFlowRef
    run: EventRunRef
    data: dict[str, object]
    links: EventLinks


def normalize_run_outcome(
    *,
    status: str,
    cancelled: bool,
) -> tuple[RunOutcome, CompletionReason]:
    """Map an internal terminal run status to the public outcome contract."""
    if status == "succeeded":
        return "succeeded", "completed"
    if cancelled:
        return "failed", "cancelled"
    return "failed", "error"


def envelope_from_event(event: BackfieldEvent, *, project_slug: str) -> EventEnvelope:
    """Rebuild the delivery/feed envelope from a stored event row."""
    payload: dict[str, object] = json.loads(event.payload_json)
    base = public_api_base_url()
    project_url = f"{base}/public/v1/projects/{project_slug}"
    run_url = None
    articles_url = None
    if event.run_id:
        run_url = f"{project_url}/runs/{event.run_id}"
        articles_url = f"{run_url}/articles"
        if event.execution_attempt is not None:
            articles_url = f"{articles_url}?attempt={event.execution_attempt}"
    article_url = None
    if event.article_id is not None:
        article_url = f"{project_url}/articles/{event.article_id}"
    entity_url = None
    segment = ENTITY_PATH_SEGMENTS.get(event.entity_type or "")
    if segment and event.entity_id:
        entity_url = f"{project_url}/{segment}/{event.entity_id}"
    return EventEnvelope(
        id=event.event_uuid,
        sequence=int(event.id or 0),
        type=event.event_type,
        schema_version=event.schema_version,
        occurred_at=event.occurred_at,
        project=project_slug,
        flow=EventFlowRef(id=event.graph_id, name=event.graph_name),
        run=EventRunRef(id=event.run_id, attempt=event.execution_attempt, url=run_url),
        data=payload,
        links=EventLinks(
            run=run_url,
            articles=articles_url,
            article=article_url,
            entity=entity_url,
        ),
    )
