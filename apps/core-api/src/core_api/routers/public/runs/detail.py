"""GET /public/v1/projects/{project_slug}/runs/{run_id}."""

from __future__ import annotations

from backfield_db import AgateGraph, AgateRun, BackfieldProject
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from core_api.deps import get_session
from core_api.routers.public.deps import get_public_project
from core_api.routers.public.runs.helpers import run_item_counts
from core_api.routers.public.runs.schemas import PublicRunCountsOut, PublicRunOut

router = APIRouter()


def get_public_run(
    run_id: str,
    project: BackfieldProject = Depends(get_public_project),
    session: Session = Depends(get_session),
) -> PublicRunOut:
    run = session.get(AgateRun, run_id.strip())
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    graph = session.get(AgateGraph, run.graph_id)
    if graph is None or int(graph.project_id) != int(project.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

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
