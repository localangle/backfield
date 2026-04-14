"""Run creation and status."""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

from api.deps import get_auth, get_session
from backfield_auth.gate import require_project_access, visible_project_ids
from backfield_db import AgateGraph, AgateRun
from celery import Celery
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc
from sqlmodel import Session, select

router = APIRouter(prefix="/runs", tags=["runs"])

celery_app = Celery(
    "agate_worker",
    broker=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
)


class RunCreate(BaseModel):
    graph_id: str


class RunOut(BaseModel):
    id: str
    graph_id: str
    project_id: int
    status: str
    result: dict | list | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


def _graph_project_id(session: Session, graph_id: str) -> int:
    g = session.get(AgateGraph, graph_id)
    return g.project_id if g else 0


@router.post("", response_model=RunOut)
def create_run(
    body: RunCreate,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
):
    g = session.get(AgateGraph, body.graph_id)
    if not g:
        raise HTTPException(404, "Graph not found")
    require_project_access(session, auth, int(g.project_id))
    run = AgateRun(graph_id=g.id, status="pending")
    session.add(run)
    session.commit()
    session.refresh(run)
    celery_app.send_task(
        "worker.tasks.execute_agate_run",
        args=[run.id],
        queue=os.environ.get("CELERY_QUEUE", "agate"),
    )
    return RunOut(
        id=run.id,
        graph_id=run.graph_id,
        project_id=g.project_id,
        status=run.status,
        created_at=run.created_at,
        updated_at=run.updated_at,
    )


@router.get("", response_model=list[RunOut])
def list_runs(
    graph_id: str | None = None,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
):
    if graph_id:
        g = session.get(AgateGraph, graph_id)
        if not g:
            raise HTTPException(404, "Graph not found")
        require_project_access(session, auth, int(g.project_id))
    q = select(AgateRun).order_by(desc(AgateRun.created_at))
    if graph_id:
        q = q.where(AgateRun.graph_id == graph_id)
    rows = session.exec(q).all()
    visible = visible_project_ids(session, auth)
    if visible is not None:
        allowed = set(visible)
        rows = [r for r in rows if _graph_project_id(session, r.graph_id) in allowed]
    out: list[RunOut] = []
    for r in rows:
        result = None
        if r.result_json:
            try:
                result = json.loads(r.result_json)
            except json.JSONDecodeError:
                result = {"raw": r.result_json}
        out.append(
            RunOut(
                id=r.id,
                graph_id=r.graph_id,
                project_id=_graph_project_id(session, r.graph_id),
                status=r.status,
                result=result,
                error_message=r.error_message,
                created_at=r.created_at,
                updated_at=r.updated_at,
            )
        )
    return out


@router.get("/{run_id}", response_model=RunOut)
def get_run(
    run_id: str,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
):
    r = session.get(AgateRun, run_id)
    if not r:
        raise HTTPException(404, "Run not found")
    pid = _graph_project_id(session, r.graph_id)
    if pid:
        require_project_access(session, auth, pid)
    result = None
    if r.result_json:
        try:
            result = json.loads(r.result_json)
        except json.JSONDecodeError:
            result = {"raw": r.result_json}
    return RunOut(
        id=r.id,
        graph_id=r.graph_id,
        project_id=_graph_project_id(session, r.graph_id),
        status=r.status,
        result=result,
        error_message=r.error_message,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )
