"""Versioned event envelope and payload contracts."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Literal

from backfield_db import AgateGraph, AgateRun, BackfieldEvent, BackfieldProject
from pydantic import BaseModel

from backfield_events.config import public_api_base_url

EVENT_SCHEMA_VERSION = 1

RUN_COMPLETED_EVENT = "agate.run.completed"
#: Synthetic verification event; delivery-only, never enters the public feed.
WEBHOOK_TEST_EVENT = "backfield.webhook.test"

RunOutcome = Literal["succeeded", "failed"]
CompletionReason = Literal["completed", "error", "cancelled"]


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


def build_run_completed_envelope(
    *,
    event_uuid: str,
    sequence: int,
    occurred_at: datetime,
    project_slug: str,
    graph_id: str | None,
    graph_name: str | None,
    run_id: str | None,
    execution_attempt: int | None,
    data: RunCompletedData,
) -> EventEnvelope:
    base = public_api_base_url()
    run_url = None
    articles_url = None
    if run_id:
        run_url = f"{base}/public/v1/projects/{project_slug}/runs/{run_id}"
        articles_url = f"{run_url}/articles"
        if execution_attempt is not None:
            articles_url = f"{articles_url}?attempt={execution_attempt}"
    return EventEnvelope(
        id=event_uuid,
        sequence=sequence,
        type=RUN_COMPLETED_EVENT,
        schema_version=EVENT_SCHEMA_VERSION,
        occurred_at=occurred_at,
        project=project_slug,
        flow=EventFlowRef(id=graph_id, name=graph_name),
        run=EventRunRef(id=run_id, attempt=execution_attempt, url=run_url),
        data=data.model_dump(),
        links=EventLinks(run=run_url, articles=articles_url),
    )


def envelope_from_event(event: BackfieldEvent, *, project_slug: str) -> EventEnvelope:
    """Rebuild the delivery/feed envelope from a stored event row."""
    payload: dict[str, object] = json.loads(event.payload_json)
    base = public_api_base_url()
    run_url = None
    articles_url = None
    if event.run_id:
        run_url = f"{base}/public/v1/projects/{project_slug}/runs/{event.run_id}"
        articles_url = f"{run_url}/articles"
        if event.execution_attempt is not None:
            articles_url = f"{articles_url}?attempt={event.execution_attempt}"
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
        links=EventLinks(run=run_url, articles=articles_url),
    )


def run_scope_for_event(
    *,
    run: AgateRun,
    graph: AgateGraph,
    project: BackfieldProject,
) -> dict[str, object]:
    """Convenience scope kwargs shared by event recording call sites."""
    return {
        "organization_id": project.organization_id,
        "project_id": int(project.id or 0),
        "graph_id": graph.id,
        "graph_name": graph.name,
        "run_id": run.id,
        "execution_attempt": run.execution_attempt,
    }
