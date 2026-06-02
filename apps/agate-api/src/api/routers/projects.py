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
from sqlmodel import Session, select

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


class ProjectStatsOut(BaseModel):
    total_runs: int
    articles_processed: int
    runs_succeeded: int = 0
    runs_in_progress: int = 0
    runs_failed: int = 0
    median_duration_ms_per_run: float | None = None
    min_duration_ms_per_run: float | None = None
    max_duration_ms_per_run: float | None = None
    median_duration_ms_per_item: float | None = None
    median_estimated_ai_cost_per_run: Decimal | None = None
    min_estimated_ai_cost_per_run: Decimal | None = None
    max_estimated_ai_cost_per_run: Decimal | None = None
    median_estimated_ai_cost_currency: str | None = None
    median_estimated_ai_cost_incomplete: bool = False


def _accumulate_ai_cost_rows(rows: list[BackfieldAiCallRecord]) -> tuple[Decimal, bool, str, int]:
    total = Decimal("0")
    incomplete = False
    currency = "USD"
    for row in rows:
        currency = str(row.currency or "USD")
        if row.estimated_cost is not None:
            total += row.estimated_cost
        else:
            incomplete = True
        if row.cost_estimate_incomplete:
            incomplete = True
    return total, incomplete, currency, len(rows)


def _project_ai_cost_rows(
    session: Session,
    project_id: int,
) -> list[BackfieldAiCallRecord]:
    return list(
        session.exec(
            select(BackfieldAiCallRecord).where(BackfieldAiCallRecord.project_id == project_id)
        ).all()
    )


def _model_breakdown_from_ai_cost_rows(
    rows: list[BackfieldAiCallRecord],
) -> list[AiCostModelBreakdown]:
    by_model: dict[str, Decimal] = {}
    for row in rows:
        provider_model_id = row.provider_model_id
        by_model[provider_model_id] = by_model.get(provider_model_id, Decimal("0")) + (
            row.estimated_cost or Decimal("0")
        )
    return [
        AiCostModelBreakdown(provider_model_id=model_id, estimated_total=estimated_total)
        for model_id, estimated_total in sorted(
            by_model.items(),
            key=lambda item: (-item[1], item[0]),
        )
    ]


def _rollup_project_ai_cost(session: Session, project_id: int) -> tuple[Decimal, bool, str, int]:
    return _accumulate_ai_cost_rows(_project_ai_cost_rows(session, project_id))


def _median_ms(durations_ms: list[float]) -> float | None:
    if not durations_ms:
        return None
    return float(statistics.median(durations_ms))


def _median_decimal(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    return Decimal(str(statistics.median([float(v) for v in values])))


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


def _median_terminal_processed_item_duration_ms(
    session: Session, succeeded_run_ids: list[str]
) -> float | None:
    """Median wall time per ``agate_processed_item`` row (terminal statuses only).

    Returns ``None`` when there are no such rows (single-graph runs without batch items).
    """
    if not succeeded_run_ids:
        return None
    rows = list(
        session.exec(
            select(AgateProcessedItem).where(
                AgateProcessedItem.run_id.in_(succeeded_run_ids),
            )
        ).all()
    )
    durs: list[float] = []
    for row in rows:
        if row.status not in _ITEM_TERMINAL_STATUSES:
            continue
        ms = (row.updated_at - row.created_at).total_seconds() * 1000
        if ms < 0:
            ms = 0.0
        durs.append(ms)
    return _median_ms(durs)


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
    rows = list(
        session.exec(
            select(BackfieldAiCallRecord).where(
                BackfieldAiCallRecord.project_id == project_id,
                BackfieldAiCallRecord.run_id.in_(list(run_ids)),
            )
        ).all()
    )
    for row in rows:
        currency = str(row.currency or "USD")
        rid = row.run_id
        if rid not in totals:
            continue
        if row.estimated_cost is not None:
            totals[rid] += row.estimated_cost
        else:
            incomplete = True
        if row.cost_estimate_incomplete:
            incomplete = True
    return list(totals.values()), incomplete, currency


def _rollup_project_ai_cost_for_run_ids(
    session: Session, project_id: int, run_ids: frozenset[str]
) -> tuple[Decimal, bool, str, int]:
    if not run_ids:
        return Decimal("0"), False, "USD", 0
    rows = list(
        session.exec(
            select(BackfieldAiCallRecord).where(
                BackfieldAiCallRecord.project_id == project_id,
                BackfieldAiCallRecord.run_id.in_(list(run_ids)),
            )
        ).all()
    )
    return _accumulate_ai_cost_rows(rows)


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
    median_run_duration = _median_ms(dur_success)
    min_run_duration = _min_ms(dur_success)
    max_run_duration = _max_ms(dur_success)

    median_item_duration = _median_terminal_processed_item_duration_ms(session, succeeded_ids)
    if median_item_duration is None:
        median_item_duration = median_run_duration

    pid = int(p.id) if p.id is not None else 0
    succeeded_frozen = frozenset(succeeded_ids)
    per_run_costs, ai_incomplete, ai_currency = _per_run_ai_cost_totals(
        session, pid, succeeded_frozen
    )
    median_ai = _median_decimal(per_run_costs)
    min_ai = _min_decimal(per_run_costs)
    max_ai = _max_decimal(per_run_costs)

    return ProjectStatsOut(
        total_runs=total_runs,
        articles_processed=articles_processed,
        runs_succeeded=runs_succeeded,
        runs_in_progress=runs_in_progress,
        runs_failed=runs_failed,
        median_duration_ms_per_run=median_run_duration,
        min_duration_ms_per_run=min_run_duration,
        max_duration_ms_per_run=max_run_duration,
        median_duration_ms_per_item=median_item_duration,
        median_estimated_ai_cost_per_run=median_ai,
        min_estimated_ai_cost_per_run=min_ai,
        max_estimated_ai_cost_per_run=max_ai,
        median_estimated_ai_cost_currency=ai_currency if runs_succeeded > 0 else None,
        median_estimated_ai_cost_incomplete=ai_incomplete if runs_succeeded > 0 else False,
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

    rows = _project_ai_cost_rows(session, project_id)
    total, incomplete, currency, attempt_count = _accumulate_ai_cost_rows(rows)

    return ProjectEstimatedAiCostOut(
        project_id=project_id,
        currency=currency,
        estimated_total=total,
        incomplete_estimate=incomplete,
        attempt_count=attempt_count,
        model_breakdown=_model_breakdown_from_ai_cost_rows(rows),
    )
