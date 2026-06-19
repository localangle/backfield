"""Project CRUD and encrypted secrets."""

from __future__ import annotations

import json
import re
import statistics
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from api.deps import get_auth, get_session
from backfield_auth.gate import (
    require_project_access,
    require_session_may_assign_project_to_workspace,
    visible_project_ids,
)
from backfield_db import (
    AgateGraph,
    AgateProcessedItem,
    AgateRun,
    BackfieldAiCallRecord,
    BackfieldOrganization,
    BackfieldProject,
    BackfieldProjectSecret,
    BackfieldWorkspace,
    Stylebook,
)
from backfield_db.crypto import encrypt_secret, fernet_from_env
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import case, func, or_
from sqlmodel import Session, col, select

router = APIRouter(prefix="/projects", tags=["projects"])

_KEY_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")

# Items still queued or executing are excluded from average-item duration.
_ITEM_TERMINAL_STATUSES = frozenset({"succeeded", "failed", "timed_out", "skipped"})


class ProjectEstimatedAiCostOut(BaseModel):
    project_id: int
    currency: str
    estimated_total: Decimal
    incomplete_estimate: bool
    attempt_count: int
    model_breakdown: list[AiCostModelBreakdown] = Field(default_factory=list)


class AiCostModelBreakdown(BaseModel):
    provider_model_id: str
    estimated_total: Decimal


def _settings_dict(project: BackfieldProject) -> dict:
    if not project.settings_json:
        return {}
    try:
        return json.loads(project.settings_json)
    except json.JSONDecodeError:
        return {}


def _set_system_prompt(project: BackfieldProject, value: str | None) -> None:
    d = _settings_dict(project)
    if value is None or value == "":
        d.pop("system_prompt", None)
    else:
        d["system_prompt"] = str(value)
    project.settings_json = json.dumps(d) if d else None


class ProjectCreate(BaseModel):
    name: str
    slug: str | None = None
    workspace_id: int | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    slug: str | None = None
    system_prompt: str | None = None


class ProjectOut(BaseModel):
    id: int
    name: str
    slug: str
    organization_id: int
    system_prompt: str | None = None
    created_at: datetime
    updated_at: datetime
    workspace_id: int | None = None
    workspace_stylebook_id: int | None = None
    workspace_stylebook_name: str | None = None
    workspace_stylebook_slug: str | None = None


def _project_to_out(session: Session, p: BackfieldProject) -> ProjectOut:
    wid = int(p.workspace_id) if p.workspace_id is not None else None
    sid: int | None = None
    sname: str | None = None
    sslug: str | None = None
    if wid is not None:
        ws = session.get(BackfieldWorkspace, wid)
        if ws is not None and ws.stylebook_id is not None:
            sb = session.get(Stylebook, int(ws.stylebook_id))
            if sb is not None and sb.id is not None:
                sid = int(sb.id)
                sname = str(sb.name)
                sslug = str(sb.slug)
    d = _settings_dict(p)
    if p.id is None:
        raise HTTPException(500, "Project row missing id")
    return ProjectOut(
        id=int(p.id),
        name=p.name,
        slug=p.slug,
        organization_id=int(p.organization_id),
        system_prompt=d.get("system_prompt"),
        created_at=p.created_at,
        updated_at=p.updated_at,
        workspace_id=wid,
        workspace_stylebook_id=sid,
        workspace_stylebook_name=sname,
        workspace_stylebook_slug=sslug,
    )


def _slugify(name: str) -> str:
    s = name.lower().strip().replace(" ", "-")
    s = re.sub(r"[^a-z0-9-]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "project"


@router.get("", response_model=list[ProjectOut])
def list_projects(
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
):
    visible = visible_project_ids(session, auth)
    q = select(BackfieldProject).order_by(BackfieldProject.id)
    if visible is not None:
        if not visible:
            return []
        q = q.where(BackfieldProject.id.in_(visible))
    rows = session.exec(q).all()
    return [_project_to_out(session, r) for r in rows if r.id is not None]


@router.post("", response_model=ProjectOut)
def create_project(
    body: ProjectCreate,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
):
    if auth["type"] == "api_key":
        raise HTTPException(403, "Cannot create projects with an API key")
    slug = body.slug.strip() if body.slug else _slugify(body.name)
    existing = session.exec(select(BackfieldProject).where(BackfieldProject.slug == slug)).first()
    if existing:
        raise HTTPException(409, "Slug already exists")
    org = session.exec(
        select(BackfieldOrganization).where(BackfieldOrganization.slug == "default")
    ).first()
    if org is None:
        raise HTTPException(500, "Default organization missing; run migrations")
    workspace_id: int | None = None
    if body.workspace_id is not None:
        ws = session.get(BackfieldWorkspace, int(body.workspace_id))
        if ws is None or ws.id is None:
            raise HTTPException(400, "Workspace not found")
        if int(ws.organization_id) != int(org.id):
            raise HTTPException(400, "Workspace is not in the default organization")
        workspace_id = int(ws.id)
        require_session_may_assign_project_to_workspace(
            session,
            auth,
            workspace_id=workspace_id,
            organization_id=int(org.id),
        )

    p = BackfieldProject(
        organization_id=org.id,
        name=body.name.strip(),
        slug=slug,
        workspace_id=workspace_id,
    )
    session.add(p)
    session.commit()
    session.refresh(p)
    if p.id is None:
        raise HTTPException(500, "Project persist failed")
    return _project_to_out(session, p)


class SlowestFlowOut(BaseModel):
    graph_id: str
    flow_name: str
    avg_ms: float


class TopFlowByCostOut(BaseModel):
    graph_id: str
    flow_name: str
    avg_estimated_cost: Decimal


class ProjectStatsOut(BaseModel):
    total_runs: int
    articles_processed: int
    runs_succeeded: int = 0
    runs_in_progress: int = 0
    runs_failed: int = 0
    avg_duration_ms_per_run: float | None = None
    min_duration_ms_per_run: float | None = None
    max_duration_ms_per_run: float | None = None
    avg_duration_ms_per_item: float | None = None
    slowest_flows: list[SlowestFlowOut] = Field(default_factory=list)
    avg_estimated_ai_cost_per_run: Decimal | None = None
    top_flows_by_cost: list[TopFlowByCostOut] = Field(default_factory=list)
    avg_estimated_ai_cost_currency: str | None = None
    avg_estimated_ai_cost_incomplete: bool = False


def _ai_cost_incomplete_expr():
    return or_(
        BackfieldAiCallRecord.cost_estimate_incomplete.is_(True),
        BackfieldAiCallRecord.estimated_cost.is_(None),
    )


def _ai_cost_incomplete_aggregate():
    return func.max(
        case(
            (_ai_cost_incomplete_expr(), 1),
            else_=0,
        )
    )


def _project_ai_cost_totals(
    session: Session,
    project_id: int,
) -> tuple[Decimal, bool, str, int]:
    """Aggregate tracked LLM cost for a project in one DB round-trip."""
    count, total, incomplete_flag, currency = session.exec(
        select(
            func.count(),
            func.coalesce(func.sum(BackfieldAiCallRecord.estimated_cost), 0),
            _ai_cost_incomplete_aggregate(),
            func.max(BackfieldAiCallRecord.currency),
        ).where(BackfieldAiCallRecord.project_id == project_id)
    ).one()
    est = Decimal(str(total)) if total is not None else Decimal("0")
    return est, bool(incomplete_flag), str(currency or "USD"), int(count or 0)


def _project_ai_cost_model_breakdown(
    session: Session,
    project_id: int,
) -> list[AiCostModelBreakdown]:
    cost_sum = func.coalesce(func.sum(BackfieldAiCallRecord.estimated_cost), 0)
    rows = session.exec(
        select(
            BackfieldAiCallRecord.provider_model_id,
            cost_sum,
        )
        .where(BackfieldAiCallRecord.project_id == project_id)
        .group_by(BackfieldAiCallRecord.provider_model_id)
        .order_by(cost_sum.desc(), BackfieldAiCallRecord.provider_model_id)
    ).all()
    return [
        AiCostModelBreakdown(
            provider_model_id=str(provider_model_id),
            estimated_total=Decimal(str(estimated_total)),
        )
        for provider_model_id, estimated_total in rows
    ]


def _mean_ms(durations_ms: list[float]) -> float | None:
    if not durations_ms:
        return None
    return float(statistics.mean(durations_ms))


def _mean_decimal(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    return sum(values) / len(values)


def _min_ms(durations_ms: list[float]) -> float | None:
    if not durations_ms:
        return None
    return float(min(durations_ms))


def _max_ms(durations_ms: list[float]) -> float | None:
    if not durations_ms:
        return None
    return float(max(durations_ms))


def _min_decimal(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    return min(values)


def _max_decimal(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    return max(values)


def _processed_item_duration_ms_expr():
    return (
        func.extract(
            "epoch",
            AgateProcessedItem.updated_at
            - func.coalesce(AgateProcessedItem.started_at, AgateProcessedItem.created_at),
        )
        * 1000.0
    )


def _avg_terminal_processed_item_duration_ms(
    session: Session, succeeded_run_ids: list[str]
) -> float | None:
    """Mean wall time per ``agate_processed_item`` row (terminal statuses only).

    Returns ``None`` when there are no such rows (single-graph runs without batch items).
    """
    if not succeeded_run_ids:
        return None
    filters = (
        AgateProcessedItem.run_id.in_(succeeded_run_ids),
        col(AgateProcessedItem.status).in_(_ITEM_TERMINAL_STATUSES),
    )
    duration_ms = _processed_item_duration_ms_expr()
    avg = session.exec(select(func.avg(duration_ms)).where(*filters)).one()
    if avg is None:
        return None
    return max(float(avg), 0.0)


def _run_wall_duration_ms_expr():
    return func.extract("epoch", AgateRun.updated_at - AgateRun.created_at) * 1000.0


def _slowest_flows_for_project(
    session: Session,
    graph_ids: list[str],
    *,
    limit: int = 5,
) -> list[SlowestFlowOut]:
    if not graph_ids:
        return []
    run_duration_ms = _run_wall_duration_ms_expr()
    rows = session.exec(
        select(
            AgateGraph.id,
            AgateGraph.name,
            func.avg(run_duration_ms),
        )
        .join(AgateGraph, AgateGraph.id == AgateRun.graph_id)
        .where(
            AgateRun.graph_id.in_(graph_ids),
            AgateRun.status == "succeeded",
        )
        .group_by(AgateGraph.id, AgateGraph.name)
        .order_by(func.avg(run_duration_ms).desc())
        .limit(limit)
    ).all()
    return [
        SlowestFlowOut(
            graph_id=str(graph_id),
            flow_name=str(flow_name),
            avg_ms=round(max(float(avg_ms), 0.0), 1),
        )
        for graph_id, flow_name, avg_ms in rows
        if avg_ms is not None
    ]


def _top_flows_by_avg_ai_cost_for_project(
    session: Session,
    project_id: int,
    graph_ids: list[str],
    *,
    limit: int = 5,
) -> list[TopFlowByCostOut]:
    if not graph_ids:
        return []
    per_run_cost = func.coalesce(func.sum(BackfieldAiCallRecord.estimated_cost), 0)
    per_run_subq = (
        select(
            BackfieldAiCallRecord.run_id.label("run_id"),
            per_run_cost.label("total_cost"),
        )
        .where(BackfieldAiCallRecord.project_id == project_id)
        .group_by(BackfieldAiCallRecord.run_id)
        .subquery()
    )
    run_total = func.coalesce(per_run_subq.c.total_cost, 0)
    rows = session.exec(
        select(
            AgateGraph.id,
            AgateGraph.name,
            func.avg(run_total),
        )
        .select_from(AgateRun)
        .join(AgateGraph, AgateGraph.id == AgateRun.graph_id)
        .outerjoin(per_run_subq, per_run_subq.c.run_id == AgateRun.id)
        .where(
            AgateRun.graph_id.in_(graph_ids),
            AgateRun.status == "succeeded",
        )
        .group_by(AgateGraph.id, AgateGraph.name)
        .order_by(func.avg(run_total).desc())
        .limit(limit)
    ).all()
    return [
        TopFlowByCostOut(
            graph_id=str(graph_id),
            flow_name=str(flow_name),
            avg_estimated_cost=Decimal(str(avg_cost)),
        )
        for graph_id, flow_name, avg_cost in rows
        if avg_cost is not None
    ]


def _per_run_ai_cost_totals(
    session: Session,
    project_id: int,
    run_ids: frozenset[str],
) -> tuple[list[Decimal], bool, str]:
    """Total tracked LLM cost per run id (zeros for succeeded runs with no rows)."""
    if not run_ids:
        return [], False, "USD"
    totals: dict[str, Decimal] = {rid: Decimal("0") for rid in run_ids}
    incomplete = False
    currency = "USD"
    rows = session.exec(
        select(
            BackfieldAiCallRecord.run_id,
            func.coalesce(func.sum(BackfieldAiCallRecord.estimated_cost), 0),
            _ai_cost_incomplete_aggregate(),
            func.max(BackfieldAiCallRecord.currency),
        )
        .where(
            BackfieldAiCallRecord.project_id == project_id,
            BackfieldAiCallRecord.run_id.in_(list(run_ids)),
        )
        .group_by(BackfieldAiCallRecord.run_id)
    ).all()
    for run_id, total, incomplete_flag, row_currency in rows:
        if run_id is None or run_id not in totals:
            continue
        totals[run_id] = Decimal(str(total)) if total is not None else Decimal("0")
        if row_currency:
            currency = str(row_currency)
        if incomplete_flag:
            incomplete = True
    return list(totals.values()), incomplete, currency


def _project_stats(session: Session, p: BackfieldProject) -> ProjectStatsOut:
    graphs = session.exec(
        select(AgateGraph).where(AgateGraph.project_id == p.id)
    ).all()
    graph_ids = [g.id for g in graphs]
    if not graph_ids:
        return ProjectStatsOut(total_runs=0, articles_processed=0)
    runs = session.exec(select(AgateRun).where(AgateRun.graph_id.in_(graph_ids))).all()
    total_runs = len(runs)

    runs_succeeded = 0
    runs_in_progress = 0
    runs_failed = 0
    succeeded_ids: list[str] = []
    for r in runs:
        st = r.status
        if st == "succeeded":
            runs_succeeded += 1
            succeeded_ids.append(r.id)
        elif st in ("pending", "running"):
            runs_in_progress += 1
        elif st == "failed":
            runs_failed += 1
        else:
            runs_failed += 1

    articles_processed = runs_succeeded

    dur_success: list[float] = []
    for r in runs:
        if r.status != "succeeded":
            continue
        ms = (r.updated_at - r.created_at).total_seconds() * 1000
        if ms < 0:
            ms = 0.0
        dur_success.append(ms)
    avg_run_duration = _mean_ms(dur_success)
    min_run_duration = _min_ms(dur_success)
    max_run_duration = _max_ms(dur_success)

    avg_item_duration = _avg_terminal_processed_item_duration_ms(session, succeeded_ids)
    if avg_item_duration is None:
        avg_item_duration = avg_run_duration

    pid = int(p.id) if p.id is not None else 0
    succeeded_frozen = frozenset(succeeded_ids)
    per_run_costs, ai_incomplete, ai_currency = _per_run_ai_cost_totals(
        session, pid, succeeded_frozen
    )
    avg_ai = _mean_decimal(per_run_costs)
    slowest_flows = _slowest_flows_for_project(session, graph_ids)
    top_flows_by_cost = _top_flows_by_avg_ai_cost_for_project(session, pid, graph_ids)

    return ProjectStatsOut(
        total_runs=total_runs,
        articles_processed=articles_processed,
        runs_succeeded=runs_succeeded,
        runs_in_progress=runs_in_progress,
        runs_failed=runs_failed,
        avg_duration_ms_per_run=avg_run_duration,
        min_duration_ms_per_run=min_run_duration,
        max_duration_ms_per_run=max_run_duration,
        avg_duration_ms_per_item=avg_item_duration,
        slowest_flows=slowest_flows,
        avg_estimated_ai_cost_per_run=avg_ai,
        top_flows_by_cost=top_flows_by_cost,
        avg_estimated_ai_cost_currency=ai_currency if runs_succeeded > 0 else None,
        avg_estimated_ai_cost_incomplete=ai_incomplete if runs_succeeded > 0 else False,
    )


@router.get("/by-slug/{slug}/stats", response_model=ProjectStatsOut)
def project_stats_by_slug(
    slug: str,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
):
    p = session.exec(select(BackfieldProject).where(BackfieldProject.slug == slug)).first()
    if not p:
        raise HTTPException(404, "Project not found")
    require_project_access(session, auth, int(p.id))
    return _project_stats(session, p)


@router.get("/by-slug/{slug}", response_model=ProjectOut)
def get_project_by_slug(
    slug: str,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
):
    p = session.exec(select(BackfieldProject).where(BackfieldProject.slug == slug)).first()
    if not p:
        raise HTTPException(404, "Project not found")
    require_project_access(session, auth, int(p.id))
    return _project_to_out(session, p)


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: int,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
):
    require_project_access(session, auth, project_id)
    p = session.get(BackfieldProject, project_id)
    if not p:
        raise HTTPException(404, "Project not found")
    return _project_to_out(session, p)


@router.get("/{project_id}/stats", response_model=ProjectStatsOut)
def project_stats(
    project_id: int,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
):
    require_project_access(session, auth, project_id)
    p = session.get(BackfieldProject, project_id)
    if not p:
        raise HTTPException(404, "Project not found")
    return _project_stats(session, p)


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: int,
    body: ProjectUpdate,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
):
    require_project_access(session, auth, project_id)
    p = session.get(BackfieldProject, project_id)
    if not p:
        raise HTTPException(404, "Project not found")
    patch = body.model_dump(exclude_unset=True)
    if "name" in patch and patch["name"] is not None:
        p.name = patch["name"].strip()
    if "slug" in patch and patch["slug"] is not None:
        new_slug = patch["slug"].strip()
        if new_slug != p.slug:
            clash = session.exec(
                select(BackfieldProject).where(BackfieldProject.slug == new_slug)
            ).first()
            if clash and clash.id != p.id:
                raise HTTPException(409, "Slug already exists")
            p.slug = new_slug
    if "system_prompt" in patch:
        _set_system_prompt(p, patch["system_prompt"])
    p.updated_at = datetime.now(UTC)
    session.add(p)
    session.commit()
    session.refresh(p)
    return _project_to_out(session, p)


@router.delete("/{project_id}", status_code=204)
def delete_project(
    project_id: int,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
):
    require_project_access(session, auth, project_id)
    p = session.get(BackfieldProject, project_id)
    if not p:
        raise HTTPException(404, "Project not found")
    if p.slug == "general":
        raise HTTPException(400, "Cannot delete the General project")
    if session.exec(select(AgateGraph).where(AgateGraph.project_id == project_id)).first():
        raise HTTPException(400, "Project still has flows; reassign or delete them first")
    session.delete(p)
    session.commit()
    return None


# --- Secrets ---


class SecretOut(BaseModel):
    key_name: str
    created_at: datetime
    updated_at: datetime


class SecretSetBody(BaseModel):
    value: str = Field(..., min_length=1)


@router.get("/{project_id}/secrets", response_model=list[SecretOut])
def list_secrets(
    project_id: int,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
):
    require_project_access(session, auth, project_id)
    p = session.get(BackfieldProject, project_id)
    if not p:
        raise HTTPException(404, "Project not found")
    rows = session.exec(
        select(BackfieldProjectSecret)
        .where(BackfieldProjectSecret.project_id == project_id)
        .order_by(BackfieldProjectSecret.key)
    ).all()
    return [
        SecretOut(key_name=r.key, created_at=r.created_at, updated_at=r.updated_at) for r in rows
    ]


@router.put("/{project_id}/secrets/{key_name}", response_model=SecretOut)
def set_secret(
    project_id: int,
    key_name: str,
    body: SecretSetBody,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
):
    require_project_access(session, auth, project_id)
    if not _KEY_RE.match(key_name):
        raise HTTPException(400, "Invalid key name; use A-Z, digits, underscore")
    if fernet_from_env() is None:
        raise HTTPException(
            503, "MASTER_ENCRYPTION_KEY is not configured; cannot store secrets"
        )
    p = session.get(BackfieldProject, project_id)
    if not p:
        raise HTTPException(404, "Project not found")
    try:
        enc = encrypt_secret(body.value)
    except RuntimeError as e:
        raise HTTPException(503, str(e)) from e
    now = datetime.now(UTC)
    existing = session.exec(
        select(BackfieldProjectSecret).where(
            BackfieldProjectSecret.project_id == project_id,
            BackfieldProjectSecret.key == key_name,
        )
    ).first()
    if existing:
        existing.value_encrypted = enc
        existing.updated_at = now
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return SecretOut(
            key_name=existing.key,
            created_at=existing.created_at,
            updated_at=existing.updated_at,
        )
    row = BackfieldProjectSecret(
        project_id=project_id, key=key_name, value_encrypted=enc, created_at=now, updated_at=now
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return SecretOut(key_name=row.key, created_at=row.created_at, updated_at=row.updated_at)


@router.delete("/{project_id}/secrets/{key_name}", status_code=204)
def delete_secret(
    project_id: int,
    key_name: str,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
):
    require_project_access(session, auth, project_id)
    p = session.get(BackfieldProject, project_id)
    if not p:
        raise HTTPException(404, "Project not found")
    row = session.exec(
        select(BackfieldProjectSecret).where(
            BackfieldProjectSecret.project_id == project_id,
            BackfieldProjectSecret.key == key_name,
        )
    ).first()
    if not row:
        raise HTTPException(404, "Secret not found")
    session.delete(row)
    session.commit()
    return None


@router.get("/{project_id}/estimated-ai-cost", response_model=ProjectEstimatedAiCostOut)
def get_project_estimated_ai_cost(
    project_id: int,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
):
    require_project_access(session, auth, project_id)
    p = session.get(BackfieldProject, project_id)
    if not p:
        raise HTTPException(404, "Project not found")

    total, incomplete, currency, attempt_count = _project_ai_cost_totals(session, project_id)

    return ProjectEstimatedAiCostOut(
        project_id=project_id,
        currency=currency,
        estimated_total=total,
        incomplete_estimate=incomplete,
        attempt_count=attempt_count,
        model_breakdown=_project_ai_cost_model_breakdown(session, project_id),
    )
