"""GET /public/v1/projects/{project_slug}/runs/{run_id}/articles."""

from __future__ import annotations

from backfield_db import AgateGraph, AgateRun, AgateRunOutputArticle, BackfieldProject
from backfield_entities.public.articles import PublicArticleOut, public_articles_for_ids
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import Session, col, select

from core_api.deps import get_session
from core_api.routers.public.deps import get_public_project
from core_api.routers.public.schemas import PaginationOut

router = APIRouter()


class PublicRunArticlesOut(BaseModel):
    """Articles persisted by one run execution attempt (immutable per attempt)."""

    run_id: str
    attempt: int
    latest_attempt: int
    items: list[PublicArticleOut]
    pagination: PaginationOut


def _resolve_run(session: Session, project: BackfieldProject, run_id: str) -> AgateRun:
    run = session.get(AgateRun, run_id.strip())
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    graph = session.get(AgateGraph, run.graph_id)
    if graph is None or int(graph.project_id) != int(project.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return run


def list_public_run_articles(
    run_id: str,
    attempt: int | None = Query(
        default=None,
        ge=1,
        description="Execution attempt to read; defaults to the latest attempt with output.",
    ),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    project: BackfieldProject = Depends(get_public_project),
    session: Session = Depends(get_session),
) -> PublicRunArticlesOut:
    """Articles persisted by a run, scoped to one immutable execution attempt.

    Partial outputs are exposed even when the run outcome was failed.
    """
    run = _resolve_run(session, project, run_id)
    latest_attempt = int(run.execution_attempt or 1)

    if attempt is not None and attempt > latest_attempt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Run attempt not found",
        )

    selected_attempt = attempt
    if selected_attempt is None:
        recorded = session.exec(
            select(func.max(AgateRunOutputArticle.execution_attempt)).where(
                AgateRunOutputArticle.run_id == run.id
            )
        ).one()
        selected_attempt = int(recorded) if recorded is not None else latest_attempt

    base_filter = (
        AgateRunOutputArticle.run_id == run.id,
        AgateRunOutputArticle.execution_attempt == selected_attempt,
    )
    total = int(
        session.exec(
            select(func.count()).select_from(AgateRunOutputArticle).where(*base_filter)
        ).one()
    )
    article_ids = [
        int(row)
        for row in session.exec(
            select(AgateRunOutputArticle.article_id)
            .where(*base_filter)
            .order_by(col(AgateRunOutputArticle.id))
            .offset(offset)
            .limit(limit)
        ).all()
    ]
    items = public_articles_for_ids(
        session,
        project_id=int(project.id),
        article_ids=article_ids,
    )
    return PublicRunArticlesOut(
        run_id=run.id,
        attempt=selected_attempt,
        latest_attempt=latest_attempt,
        items=items,
        pagination=PaginationOut(limit=limit, offset=offset, total=total),
    )
