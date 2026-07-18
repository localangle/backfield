"""GET /public/v1/projects/{project_slug}/runs/{run_id}."""

from __future__ import annotations

from backfield_db import AgateGraph, AgateRun, BackfieldProject
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlmodel import Session

from core_api.deps import get_session
from core_api.routers.public.deps import get_public_project
from core_api.routers.public.runs.create import INITIAL_POLL_SECONDS
from core_api.routers.public.runs.helpers import public_run_snapshot
from core_api.routers.public.runs.schemas import PublicRunOut

router = APIRouter()


def get_public_run(
    run_id: str,
    response: Response,
    project: BackfieldProject = Depends(get_public_project),
    session: Session = Depends(get_session),
) -> PublicRunOut:
    run = session.get(AgateRun, run_id.strip())
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    graph = session.get(AgateGraph, run.graph_id)
    if graph is None or int(graph.project_id) != int(project.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    if run.status in ("pending", "running"):
        response.headers["Retry-After"] = str(INITIAL_POLL_SECONDS)
    return public_run_snapshot(session, run=run, graph=graph)
