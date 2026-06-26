"""POST /public/v1/projects/{project_slug}/runs."""

from __future__ import annotations

from typing import Any

from agate_runtime.run_trigger import trigger_agate_run
from backfield_db import AgateGraph, BackfieldProject
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from core_api.deps import get_session
from core_api.routers.public.deps import get_public_project, require_scope
from core_api.routers.public.runs.helpers import run_item_counts
from core_api.routers.public.runs.schemas import (
    PublicRunCountsOut,
    PublicRunCreateIn,
    PublicRunOut,
)
from core_api.run_enqueue import enqueue_worker_task

router = APIRouter()


def create_public_run(
    body: PublicRunCreateIn,
    project: BackfieldProject = Depends(get_public_project),
    _auth: dict[str, Any] = Depends(require_scope("runs:trigger")),
    session: Session = Depends(get_session),
) -> PublicRunOut:
    graph = session.get(AgateGraph, body.graph_id.strip())
    if graph is None or int(graph.project_id) != int(project.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Graph not found")
    if not graph.public_run_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Graph is not enabled for public run trigger.",
        )

    try:
        triggered = trigger_agate_run(
            session,
            graph=graph,
            inputs=body.inputs,  # type: ignore[arg-type]
            replace_article_geography_on_persist=False,
            enqueue=enqueue_worker_task,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    run = triggered.run
    total, pending, running, succeeded, failed = run_item_counts(session, run=run, graph=graph)
    return PublicRunOut(
        run_id=run.id,
        status=run.status,
        counts=PublicRunCountsOut(
            total=total,
            pending=pending,
            running=running,
            succeeded=succeeded,
            failed=failed,
        ),
        created_at=run.created_at,
        updated_at=run.updated_at,
        error_message=run.error_message,
    )
