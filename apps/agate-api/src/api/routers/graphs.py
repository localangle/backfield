"""Graph CRUD."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from agate_runtime import GraphSpec
from api.deps import get_auth, get_session
from backfield_auth.gate import require_project_access, visible_project_ids
from backfield_db import (
    AgateGraph,
    AgateProcessedItem,
    AgateRun,
    BackfieldAiCallRecord,
    BackfieldProject,
    SubstrateArticle,
)
from backfield_entities.catalog.graph_stylebook_refs import (
    StylebookGraphRefsError,
    sanitize_stylebook_refs_for_organization,
    validate_stylebook_refs_for_organization,
)
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ValidationError
from sqlalchemy import delete, desc, update
from sqlmodel import Session, select

router = APIRouter(prefix="/graphs", tags=["graphs"])


def _prepare_spec_stylebook_refs(
    session: Session,
    project_id: int,
    spec: GraphSpec,
) -> GraphSpec:
    proj = session.get(BackfieldProject, project_id)
    if not proj:
        return spec
    org_id = int(proj.organization_id)
    spec_dict = spec.model_dump()
    sanitize_stylebook_refs_for_organization(
        session,
        organization_id=org_id,
        spec=spec_dict,
    )
    try:
        validate_stylebook_refs_for_organization(
            session,
            organization_id=org_id,
            spec=spec_dict,
        )
    except StylebookGraphRefsError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return GraphSpec.model_validate(spec_dict)


class GraphCreate(BaseModel):
    name: str
    description: str = ""
    spec: GraphSpec
    project_id: int
    public_run_enabled: bool = False


class GraphSummaryOut(BaseModel):
    id: str
    name: str
    description: str
    project_id: int
    public_run_enabled: bool
    created_at: datetime


class GraphOut(GraphSummaryOut):
    spec: GraphSpec


def _graph_summary_out(graph: AgateGraph) -> GraphSummaryOut:
    return GraphSummaryOut(
        id=graph.id,
        name=graph.name,
        description=graph.description or "",
        project_id=graph.project_id,
        public_run_enabled=bool(graph.public_run_enabled),
        created_at=graph.created_at,
    )


def _graph_out(graph: AgateGraph) -> GraphOut:
    return GraphOut(
        **_graph_summary_out(graph).model_dump(),
        spec=GraphSpec.model_validate_json(graph.spec_json),
    )


def _graph_out_or_none(graph: AgateGraph) -> GraphOut | None:
    try:
        return _graph_out(graph)
    except ValidationError:
        return None


@router.post("", response_model=GraphOut)
def create_graph(
    body: GraphCreate,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
):
    require_project_access(session, auth, body.project_id)
    p = session.get(BackfieldProject, body.project_id)
    if not p:
        raise HTTPException(404, "Project not found")
    prepared_spec = _prepare_spec_stylebook_refs(session, body.project_id, body.spec)
    g = AgateGraph(
        name=body.name,
        description=(body.description or "").strip(),
        spec_json=prepared_spec.model_dump_json(),
        project_id=body.project_id,
        public_run_enabled=body.public_run_enabled,
    )
    session.add(g)
    session.commit()
    session.refresh(g)
    return _graph_out(g)


@router.get("", response_model=list[GraphOut] | list[GraphSummaryOut])
def list_graphs(
    project_id: int | None = None,
    include_spec: bool = True,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
):
    if project_id is not None:
        require_project_access(session, auth, project_id)
    q = select(AgateGraph).order_by(desc(AgateGraph.created_at))
    if project_id is not None:
        q = q.where(AgateGraph.project_id == project_id)
    rows = session.exec(q).all()
    visible = visible_project_ids(session, auth)
    if visible is not None:
        allowed = set(visible)
        rows = [r for r in rows if r.project_id in allowed]
    if include_spec:
        out: list[GraphOut] = []
        for row in rows:
            graph = _graph_out_or_none(row)
            if graph is not None:
                out.append(graph)
        return out
    return [_graph_summary_out(row) for row in rows]


@router.get("/{graph_id}", response_model=GraphOut)
def get_graph(
    graph_id: str,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
):
    g = session.get(AgateGraph, graph_id)
    if not g:
        raise HTTPException(404, "Graph not found")
    require_project_access(session, auth, int(g.project_id))
    return _graph_out(g)


@router.put("/{graph_id}", response_model=GraphOut)
def update_graph(
    graph_id: str,
    body: GraphCreate,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
):
    g = session.get(AgateGraph, graph_id)
    if not g:
        raise HTTPException(404, "Graph not found")
    require_project_access(session, auth, int(g.project_id))
    require_project_access(session, auth, body.project_id)
    p = session.get(BackfieldProject, body.project_id)
    if not p:
        raise HTTPException(404, "Project not found")
    prepared_spec = _prepare_spec_stylebook_refs(session, body.project_id, body.spec)
    g.name = body.name
    g.description = (body.description or "").strip()
    g.spec_json = prepared_spec.model_dump_json()
    g.project_id = body.project_id
    g.public_run_enabled = body.public_run_enabled
    session.add(g)
    session.commit()
    session.refresh(g)
    return _graph_out(g)


@router.delete("/{graph_id}", status_code=204)
def delete_graph(
    graph_id: str,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
):
    g = session.get(AgateGraph, graph_id)
    if not g:
        raise HTTPException(404, "Graph not found")
    require_project_access(session, auth, int(g.project_id))
    run_ids = [
        str(run_id)
        for run_id in session.exec(select(AgateRun.id).where(AgateRun.graph_id == graph_id)).all()
        if run_id is not None
    ]
    if run_ids:
        # Preserve durable substrate content while removing execution provenance
        # tied to deleted runs.
        session.exec(
            update(SubstrateArticle)
            .where(SubstrateArticle.source_run_id.in_(run_ids))
            .values(source_run_id=None, source_item_id=None)
        )
        session.exec(delete(BackfieldAiCallRecord).where(BackfieldAiCallRecord.run_id.in_(run_ids)))
        session.exec(delete(AgateProcessedItem).where(AgateProcessedItem.run_id.in_(run_ids)))
        session.exec(delete(AgateRun).where(AgateRun.id.in_(run_ids)))
    session.delete(g)
    session.commit()
    return None
