"""Run creation and status."""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

from api.deps import get_auth, get_session
from backfield_auth.gate import require_project_access, visible_project_ids
from backfield_core.s3_batch import graph_spec_json_contains_s3_input
from backfield_db import AgateGraph, AgateProcessedItem, AgateRun, BackfieldProjectSecret
from backfield_db.crypto import decrypt_secret
from celery import Celery
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import asc, desc
from sqlmodel import Session, select

router = APIRouter(prefix="/runs", tags=["runs"])

_MAPBOX_SECRET_KEY = "MAPBOX_API_TOKEN"


def _mapbox_api_token_for_project(session: Session, project_id: int) -> str | None:
    """Decrypt MAPBOX_API_TOKEN for map UIs (browser-side Mapbox GL)."""
    if project_id <= 0:
        return None
    row = session.exec(
        select(BackfieldProjectSecret).where(
            BackfieldProjectSecret.project_id == project_id,
            BackfieldProjectSecret.key == _MAPBOX_SECRET_KEY,
        )
    ).first()
    if row is None:
        return None
    try:
        return decrypt_secret(row.value_encrypted)
    except (RuntimeError, ValueError):
        return None

celery_app = Celery(
    "agate_worker",
    broker=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
)


class RunCreate(BaseModel):
    graph_id: str


class ProcessedItemOut(BaseModel):
    """Row from ``agate_processed_item`` (S3 batch and future multi-item runs)."""

    id: int
    run_id: str
    source_file: str | None = None
    status: str
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class ProcessedItemDetailOut(BaseModel):
    """Single processed item for run detail / item drill-down."""

    id: int
    run_id: str
    source_file: str | None = None
    input: dict[str, Any]
    output: dict[str, Any] | None = None
    node_outputs: dict[str, Any] | None = None
    node_logs: dict[str, list[str]] | None = None
    status: str
    error: str | None = None
    created_at: datetime
    updated_at: datetime


class RunOut(BaseModel):
    id: str
    graph_id: str
    project_id: int
    status: str
    result: dict | list | None = None
    error_message: str | None = None
    mapbox_api_token: str | None = None
    created_at: datetime
    updated_at: datetime
    processed_items: list[ProcessedItemOut] = []


def _graph_project_id(session: Session, graph_id: str) -> int:
    g = session.get(AgateGraph, graph_id)
    return g.project_id if g else 0


def _processed_items_for_run(session: Session, run_id: str) -> list[ProcessedItemOut]:
    rows = list(
        session.exec(
            select(AgateProcessedItem)
            .where(AgateProcessedItem.run_id == run_id)
            .order_by(asc(AgateProcessedItem.id))
        ).all()
    )
    out: list[ProcessedItemOut] = []
    for row in rows:
        if row.id is None:
            continue
        out.append(
            ProcessedItemOut(
                id=int(row.id),
                run_id=row.run_id,
                source_file=row.source_file,
                status=row.status,
                error_message=row.error_message,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
        )
    return out


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
    task_name = (
        "worker.tasks.execute_s3_batch_setup"
        if graph_spec_json_contains_s3_input(g.spec_json)
        else "worker.tasks.execute_agate_run"
    )
    celery_app.send_task(
        task_name,
        args=[run.id],
        queue=os.environ.get("CELERY_QUEUE", "agate"),
    )
    return RunOut(
        id=run.id,
        graph_id=run.graph_id,
        project_id=g.project_id,
        status=run.status,
        mapbox_api_token=_mapbox_api_token_for_project(session, g.project_id),
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
        pid = _graph_project_id(session, r.graph_id)
        out.append(
            RunOut(
                id=r.id,
                graph_id=r.graph_id,
                project_id=pid,
                status=r.status,
                result=result,
                error_message=r.error_message,
                mapbox_api_token=_mapbox_api_token_for_project(session, pid),
                created_at=r.created_at,
                updated_at=r.updated_at,
            )
        )
    return out


@router.get("/{run_id}/items/{item_id}", response_model=ProcessedItemDetailOut)
def get_run_processed_item(
    run_id: str,
    item_id: int,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
):
    r = session.get(AgateRun, run_id)
    if not r:
        raise HTTPException(404, "Run not found")
    pid = _graph_project_id(session, r.graph_id)
    if pid:
        require_project_access(session, auth, pid)
    row = session.get(AgateProcessedItem, item_id)
    if row is None or row.run_id != run_id:
        raise HTTPException(404, "Processed item not found")

    input_obj: dict[str, Any] = {}
    if row.input_json:
        try:
            parsed = json.loads(row.input_json)
            if isinstance(parsed, dict):
                input_obj = parsed
        except json.JSONDecodeError:
            input_obj = {}

    output_obj: dict[str, Any] | None = None
    if row.result_json:
        try:
            parsed = json.loads(row.result_json)
            if isinstance(parsed, dict):
                output_obj = parsed
        except json.JSONDecodeError:
            output_obj = None

    rid = row.id
    if rid is None:
        raise HTTPException(404, "Processed item not found")
    return ProcessedItemDetailOut(
        id=int(rid),
        run_id=row.run_id,
        source_file=row.source_file,
        input=input_obj,
        output=output_obj,
        node_outputs=output_obj,
        node_logs=None,
        status=row.status,
        error=row.error_message,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


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
    pid = _graph_project_id(session, r.graph_id)
    processed = _processed_items_for_run(session, run_id)
    return RunOut(
        id=r.id,
        graph_id=r.graph_id,
        project_id=pid,
        status=r.status,
        result=result,
        error_message=r.error_message,
        mapbox_api_token=_mapbox_api_token_for_project(session, pid),
        created_at=r.created_at,
        updated_at=r.updated_at,
        processed_items=processed,
    )
