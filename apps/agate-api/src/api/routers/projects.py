"""Project CRUD and encrypted secrets."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

from api.deps import get_auth, get_session
from backfield_auth.gate import (
    require_project_access,
    require_session_may_assign_project_to_workspace,
    visible_project_ids,
)
from backfield_db import (
    AgateGraph,
    AgateRun,
    BackfieldOrganization,
    BackfieldProject,
    BackfieldProjectSecret,
    BackfieldWorkspace,
    Stylebook,
)
from backfield_db.crypto import encrypt_secret, fernet_from_env
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, col, select

router = APIRouter(prefix="/projects", tags=["projects"])

_KEY_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")


def _settings_dict(project: BackfieldProject) -> dict:
    if not project.settings_json:
        return {}
    try:
        return json.loads(project.settings_json)
    except json.JSONDecodeError:
        return {}


def _workspace_stylebook_by_project_id(
    session: Session, projects: list[BackfieldProject]
) -> dict[int, tuple[int | None, int | None, str | None, str | None]]:
    """Map project id -> (workspace_id, stylebook_id, stylebook_name, stylebook_slug)."""
    out: dict[int, tuple[int | None, int | None, str | None, str | None]] = {}
    wids: set[int] = set()
    for p in projects:
        if p.id is None:
            continue
        if p.workspace_id is not None:
            wids.add(int(p.workspace_id))
    ws_map: dict[int, BackfieldWorkspace] = {}
    if wids:
        wrows = session.exec(
            select(BackfieldWorkspace).where(col(BackfieldWorkspace.id).in_(wids))
        ).all()
        for w in wrows:
            if w.id is not None:
                ws_map[int(w.id)] = w
    sb_ids = {int(w.stylebook_id) for w in ws_map.values()}
    sb_names: dict[int, str] = {}
    sb_slugs: dict[int, str] = {}
    if sb_ids:
        sb_rows = session.exec(select(Stylebook).where(col(Stylebook.id).in_(sb_ids))).all()
        for s in sb_rows:
            if s.id is not None:
                sbid = int(s.id)
                sb_names[sbid] = str(s.name)
                sb_slugs[sbid] = str(s.slug)
    for p in projects:
        if p.id is None:
            continue
        pid = int(p.id)
        if p.workspace_id is None:
            out[pid] = (None, None, None, None)
            continue
        wid = int(p.workspace_id)
        ws = ws_map.get(wid)
        if ws is None:
            out[pid] = (wid, None, None, None)
        else:
            sbid = int(ws.stylebook_id)
            out[pid] = (wid, sbid, sb_names.get(sbid), sb_slugs.get(sbid))
    return out


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

    @classmethod
    def from_row(
        cls,
        p: BackfieldProject,
        *,
        workspace_id: int | None = None,
        workspace_stylebook_id: int | None = None,
        workspace_stylebook_name: str | None = None,
        workspace_stylebook_slug: str | None = None,
    ) -> ProjectOut:
        d = _settings_dict(p)
        return cls(
            id=p.id,
            name=p.name,
            slug=p.slug,
            organization_id=int(p.organization_id),
            system_prompt=d.get("system_prompt"),
            created_at=p.created_at,
            updated_at=p.updated_at,
            workspace_id=workspace_id,
            workspace_stylebook_id=workspace_stylebook_id,
            workspace_stylebook_name=workspace_stylebook_name,
            workspace_stylebook_slug=workspace_stylebook_slug,
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
    meta = _workspace_stylebook_by_project_id(session, list(rows))
    return [
        ProjectOut.from_row(
            r,
            workspace_id=meta.get(int(r.id), (None, None, None, None))[0],
            workspace_stylebook_id=meta.get(int(r.id), (None, None, None, None))[1],
            workspace_stylebook_name=meta.get(int(r.id), (None, None, None, None))[2],
            workspace_stylebook_slug=meta.get(int(r.id), (None, None, None, None))[3],
        )
        for r in rows
        if r.id is not None
    ]


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
    wid, sbid, sbname, sbslug = _workspace_stylebook_by_project_id(session, [p]).get(
        int(p.id), (None, None, None, None)
    )
    return ProjectOut.from_row(
        p,
        workspace_id=wid,
        workspace_stylebook_id=sbid,
        workspace_stylebook_name=sbname,
        workspace_stylebook_slug=sbslug,
    )


class ProjectStatsOut(BaseModel):
    total_runs: int
    articles_processed: int
    avg_duration_ms_per_run: float | None = None
    avg_duration_ms_per_item: float | None = None


_TERMINAL_RUN_STATUSES = frozenset({"succeeded", "failed"})


def _project_stats(session: Session, p: BackfieldProject) -> ProjectStatsOut:
    graphs = session.exec(
        select(AgateGraph).where(AgateGraph.project_id == p.id)
    ).all()
    graph_ids = [g.id for g in graphs]
    if not graph_ids:
        return ProjectStatsOut(total_runs=0, articles_processed=0)
    runs = session.exec(select(AgateRun).where(AgateRun.graph_id.in_(graph_ids))).all()
    total_runs = len(runs)
    articles_processed = sum(1 for r in runs if r.status == "succeeded")
    dur_terminal: list[float] = []
    dur_success: list[float] = []
    for r in runs:
        if r.status not in _TERMINAL_RUN_STATUSES:
            continue
        ms = (r.updated_at - r.created_at).total_seconds() * 1000
        if ms < 0:
            ms = 0.0
        dur_terminal.append(ms)
        if r.status == "succeeded":
            dur_success.append(ms)
    avg_run = sum(dur_terminal) / len(dur_terminal) if dur_terminal else None
    avg_item = sum(dur_success) / len(dur_success) if dur_success else None
    return ProjectStatsOut(
        total_runs=total_runs,
        articles_processed=articles_processed,
        avg_duration_ms_per_run=avg_run,
        avg_duration_ms_per_item=avg_item,
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
    wid, sbid, sbname, sbslug = _workspace_stylebook_by_project_id(session, [p]).get(
        int(p.id), (None, None, None, None)
    )
    return ProjectOut.from_row(
        p,
        workspace_id=wid,
        workspace_stylebook_id=sbid,
        workspace_stylebook_name=sbname,
        workspace_stylebook_slug=sbslug,
    )


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
    wid, sbid, sbname, sbslug = _workspace_stylebook_by_project_id(session, [p]).get(
        int(p.id), (None, None, None, None)
    )
    return ProjectOut.from_row(
        p,
        workspace_id=wid,
        workspace_stylebook_id=sbid,
        workspace_stylebook_name=sbname,
        workspace_stylebook_slug=sbslug,
    )


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
    wid, sbid, sbname, sbslug = _workspace_stylebook_by_project_id(session, [p]).get(
        int(p.id), (None, None, None, None)
    )
    return ProjectOut.from_row(
        p,
        workspace_id=wid,
        workspace_stylebook_id=sbid,
        workspace_stylebook_name=sbname,
        workspace_stylebook_slug=sbslug,
    )


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
