"""Run creation and status."""

from __future__ import annotations

import json
import os
from datetime import datetime
from decimal import Decimal
from typing import Any

from api.deps import get_auth, get_session
from backfield_auth.gate import require_project_access, visible_project_ids
from backfield_core.s3_batch import graph_spec_json_contains_s3_input
from backfield_db import (
    AgateGraph,
    AgateProcessedItem,
    AgateRun,
    BackfieldAiCallRecord,
    BackfieldProjectSecret,
)
from backfield_db.crypto import decrypt_secret
from celery import Celery
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import asc, desc
from sqlmodel import Session, select

DEFAULT_AI_COST_CURRENCY = "USD"

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


class AiCostNodeBreakdown(BaseModel):
    node_id: str | None
    estimated_total: Decimal


class RunEstimatedAiCostOut(BaseModel):
    run_id: str
    currency: str
    estimated_total: Decimal
    incomplete_estimate: bool
    attempt_count: int
    node_breakdown: list[AiCostNodeBreakdown]


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
    estimated_ai_cost: Decimal = Decimal("0")
    estimated_ai_cost_incomplete: bool = False
    estimated_ai_cost_currency: str = DEFAULT_AI_COST_CURRENCY


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
    estimated_ai_cost: Decimal = Decimal("0")
    estimated_ai_cost_incomplete: bool = False
    estimated_ai_cost_currency: str = DEFAULT_AI_COST_CURRENCY


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
    #: Sum of ``BackfieldAiCallRecord`` rows with ``processed_item_id IS NULL`` (single-graph runs).
    whole_run_ai_cost_estimate: Decimal = Decimal("0")
    whole_run_ai_cost_incomplete: bool = False
    whole_run_ai_cost_currency: str = DEFAULT_AI_COST_CURRENCY


def _graph_project_id(session: Session, graph_id: str) -> int:
    g = session.get(AgateGraph, graph_id)
    return g.project_id if g else 0


def _rollup_ai_costs_for_run(
    session: Session, run_id: str
) -> tuple[dict[int, tuple[Decimal, bool]], tuple[Decimal, bool], str]:
    """Aggregate LiteLLM-derived costs per ``processed_item_id`` for the run.

    Returns ``(per_item_id -> (total, incomplete_flag), (null_item_total, incomplete), currency)``.
    Rows with ``processed_item_id IS NULL`` belong to the second tuple (whole-graph execution).
    """
    rows = list(
        session.exec(
            select(BackfieldAiCallRecord).where(BackfieldAiCallRecord.run_id == run_id)
        ).all()
    )
    by_item: dict[int, tuple[Decimal, bool]] = {}
    null_total = Decimal("0")
    null_inc = False
    currency = DEFAULT_AI_COST_CURRENCY
    for row in rows:
        if row.currency:
            currency = str(row.currency)
        raw_cost = row.estimated_cost
        inc_piece = bool(row.cost_estimate_incomplete) or raw_cost is None
        add_amt = raw_cost if raw_cost is not None else Decimal("0")
        key_pi = row.processed_item_id
        if key_pi is None:
            null_total += add_amt
            null_inc = null_inc or inc_piece
        else:
            iid = int(key_pi)
            prev_sum, prev_inc = by_item.get(iid, (Decimal("0"), False))
            by_item[iid] = (prev_sum + add_amt, prev_inc or inc_piece)

    return by_item, (null_total, null_inc), currency


def _any_agate_processed_items(session: Session, run_id: str) -> bool:
    return (
        session.exec(
            select(AgateProcessedItem.id)
            .where(AgateProcessedItem.run_id == run_id)
            .limit(1)
        ).first()
        is not None
    )


def _processed_items_for_run(
    session: Session,
    run_id: str,
    *,
    cost_by_item: dict[int, tuple[Decimal, bool]],
    currency: str,
) -> list[ProcessedItemOut]:
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
        iid = int(row.id)
        est, inc = cost_by_item.get(iid, (Decimal("0"), False))
        out.append(
            ProcessedItemOut(
                id=iid,
                run_id=row.run_id,
                source_file=row.source_file,
                status=row.status,
                error_message=row.error_message,
                created_at=row.created_at,
                updated_at=row.updated_at,
                estimated_ai_cost=est,
                estimated_ai_cost_incomplete=inc,
                estimated_ai_cost_currency=currency,
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


def _detail_from_agate_processed_row(
    row: AgateProcessedItem,
    *,
    estimated_ai_cost: Decimal,
    estimated_ai_cost_incomplete: bool,
    estimated_ai_cost_currency: str,
) -> ProcessedItemDetailOut:
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
        estimated_ai_cost=estimated_ai_cost,
        estimated_ai_cost_incomplete=estimated_ai_cost_incomplete,
        estimated_ai_cost_currency=estimated_ai_cost_currency,
    )


def _maybe_detail_whole_graph_run(
    session: Session,
    run: AgateRun,
    item_id: int,
    *,
    null_cost: Decimal,
    null_incomplete: bool,
    currency: str,
) -> ProcessedItemDetailOut | None:
    """Item ``1`` is the whole run when there are no S3 processed-item rows.

    Matches UI ``normalizeRun``: worker stores JSON on ``agate_run.result_json`` only.
    """
    if item_id != 1:
        return None
    if _any_agate_processed_items(session, run.id):
        return None

    output_obj: dict[str, Any] | None = None
    if run.result_json:
        try:
            parsed = json.loads(run.result_json)
            if isinstance(parsed, dict):
                output_obj = parsed
        except json.JSONDecodeError:
            output_obj = None

    st = run.status
    if st not in ("pending", "running", "succeeded", "failed", "skipped"):
        st = "failed"

    err: str | None = run.error_message if st == "failed" else None

    return ProcessedItemDetailOut(
        id=1,
        run_id=run.id,
        source_file=None,
        input={},
        output=output_obj,
        node_outputs=output_obj,
        node_logs=None,
        status=st,
        error=err,
        created_at=run.created_at,
        updated_at=run.updated_at,
        estimated_ai_cost=null_cost,
        estimated_ai_cost_incomplete=null_incomplete,
        estimated_ai_cost_currency=currency,
    )


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
    by_item, null_b, currency = _rollup_ai_costs_for_run(session, run_id)
    null_cost, null_incomplete = null_b

    row = session.get(AgateProcessedItem, item_id)
    if row is not None and row.run_id == run_id:
        rid = row.id
        iid = int(rid) if rid is not None else 0
        est, inc = by_item.get(iid, (Decimal("0"), False))
        return _detail_from_agate_processed_row(
            row,
            estimated_ai_cost=est,
            estimated_ai_cost_incomplete=inc,
            estimated_ai_cost_currency=currency,
        )

    synthetic = _maybe_detail_whole_graph_run(
        session, r, item_id, null_cost=null_cost, null_incomplete=null_incomplete, currency=currency
    )
    if synthetic is not None:
        return synthetic

    raise HTTPException(404, "Processed item not found")


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
    by_item, null_b, wr_currency = _rollup_ai_costs_for_run(session, run_id)
    null_cost, null_incomplete = null_b
    processed = _processed_items_for_run(
        session, run_id, cost_by_item=by_item, currency=wr_currency
    )
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
        whole_run_ai_cost_estimate=null_cost,
        whole_run_ai_cost_incomplete=null_incomplete,
        whole_run_ai_cost_currency=wr_currency,
    )


@router.get("/{run_id}/estimated-ai-cost", response_model=RunEstimatedAiCostOut)
def get_run_estimated_ai_cost(
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

    stmt = select(BackfieldAiCallRecord).where(BackfieldAiCallRecord.run_id == run_id)
    rows = list(session.exec(stmt).all())
    total = Decimal("0")
    incomplete = False
    by_node: dict[str | None, Decimal] = {}
    currency = "USD"
    for row in rows:
        currency = str(row.currency or "USD")
        if row.estimated_cost is not None:
            total += row.estimated_cost
        else:
            incomplete = True
        if row.cost_estimate_incomplete:
            incomplete = True
        nk = row.node_id
        prev = by_node.get(nk, Decimal("0"))
        by_node[nk] = prev + (row.estimated_cost or Decimal("0"))

    breakdown = [
        AiCostNodeBreakdown(node_id=k, estimated_total=v)
        for k, v in sorted(by_node.items(), key=lambda kv: (kv[0] is None, str(kv[0])))
    ]

    return RunEstimatedAiCostOut(
        run_id=run_id,
        currency=currency,
        estimated_total=total,
        incomplete_estimate=incomplete,
        attempt_count=len(rows),
        node_breakdown=breakdown,
    )
