"""Article lifecycle events emitted when persisted articles are created or change.

Call sites run inside the same open transaction as the article write: DBOutput
persistence (created / reprocessed) and the Agate review article-metadata
handlers (metadata). Both resolve run context here so emission stays a
one-liner at the call site.
"""

from __future__ import annotations

from backfield_db import AgateGraph, AgateRun, BackfieldProject
from sqlmodel import Session

from backfield_events.contracts import (
    ARTICLE_CREATED_EVENT,
    ARTICLE_UPDATED_EVENT,
    ArticleChange,
    ArticleCreatedData,
    ArticleUpdatedData,
)
from backfield_events.events import DomainEvent, EventScope, record_event
from backfield_events.recording import RecordedEvent


class _ArticleEventBase(DomainEvent):
    flow_scoped = True

    organization_id: int
    project_id: int
    graph_id: str
    graph_name: str
    run_id: str
    execution_attempt: int | None
    article_id: int

    def scopes(self, session: Session) -> list[EventScope]:
        return [
            EventScope(
                organization_id=self.organization_id,
                project_id=self.project_id,
                graph_id=self.graph_id,
                graph_name=self.graph_name,
                run_id=self.run_id,
                execution_attempt=self.execution_attempt,
                article_id=self.article_id,
            )
        ]

    def coalesce_key(self, scope: EventScope) -> tuple[object, ...]:
        return (self.event_type, scope.project_id, self.article_id)


class ArticleCreated(_ArticleEventBase):
    """An article was persisted for the first time."""

    event_type = ARTICLE_CREATED_EVENT

    data: ArticleCreatedData

    def payload(self) -> dict[str, object]:
        return self.data.model_dump()


class ArticleUpdated(_ArticleEventBase):
    """An existing article was re-persisted or its metadata changed."""

    event_type = ARTICLE_UPDATED_EVENT

    data: ArticleUpdatedData

    def payload(self) -> dict[str, object]:
        return self.data.model_dump()


def record_article_created(
    session: Session,
    *,
    run_id: str,
    article_id: int,
    headline: str | None,
) -> tuple[RecordedEvent, ...]:
    """Record ``agate.article.created`` in the caller's open transaction."""
    context = _run_context(session, run_id)
    if context is None:
        return ()
    run, graph, project = context
    return record_event(
        session,
        ArticleCreated(
            organization_id=project.organization_id,
            project_id=int(project.id or 0),
            graph_id=graph.id,
            graph_name=graph.name,
            run_id=run.id,
            execution_attempt=run.execution_attempt,
            article_id=article_id,
            data=ArticleCreatedData(headline=headline),
        ),
    )


def record_article_updated(
    session: Session,
    *,
    run_id: str,
    article_id: int,
    headline: str | None,
    change: ArticleChange,
    content_changed: bool | None = None,
) -> tuple[RecordedEvent, ...]:
    """Record ``agate.article.updated`` in the caller's open transaction."""
    context = _run_context(session, run_id)
    if context is None:
        return ()
    run, graph, project = context
    return record_event(
        session,
        ArticleUpdated(
            organization_id=project.organization_id,
            project_id=int(project.id or 0),
            graph_id=graph.id,
            graph_name=graph.name,
            run_id=run.id,
            execution_attempt=run.execution_attempt,
            article_id=article_id,
            data=ArticleUpdatedData(
                headline=headline,
                change=change,
                content_changed=content_changed,
            ),
        ),
    )


def _run_context(
    session: Session,
    run_id: str,
) -> tuple[AgateRun, AgateGraph, BackfieldProject] | None:
    run = session.get(AgateRun, run_id)
    if run is None:
        return None
    graph = session.get(AgateGraph, run.graph_id)
    if graph is None:
        return None
    project = session.get(BackfieldProject, graph.project_id)
    if project is None:
        return None
    return run, graph, project
