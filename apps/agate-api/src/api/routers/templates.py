"""Flow templates — list and instantiate into a project graph."""

from __future__ import annotations

import uuid
from typing import Any

from api.deps import get_auth, get_session
from api.routers.graphs import GraphOut
from backfield_agate import GraphSpec
from backfield_agate.types import Edge, NodeConfig
from backfield_auth.gate import require_project_access
from backfield_db import AgateGraph, AgateTemplate, BackfieldProject
from backfield_stylebook.graph_stylebook_refs import (
    StylebookGraphRefsError,
    validate_stylebook_refs_for_organization,
)
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

router = APIRouter(prefix="/templates", tags=["templates"])


class TemplateOut(BaseModel):
    id: str
    name: str
    description: str | None = None
    category: str | None = None


class InstantiateBody(BaseModel):
    project_id: int
    name: str | None = None


def _remap_spec(spec: GraphSpec) -> GraphSpec:
    id_map = {n.id: str(uuid.uuid4()) for n in spec.nodes}
    node_ids = set(id_map.keys())
    new_nodes = [
        NodeConfig(
            id=id_map[n.id],
            type=n.type,
            params=n.params,
            position=n.position,
        )
        for n in spec.nodes
    ]
    new_edges: list[Edge] = []
    for e in spec.edges:
        if e.source not in node_ids or e.target not in node_ids:
            raise HTTPException(400, "Template spec has invalid edge endpoints")
        new_edges.append(
            Edge(
                source=id_map[e.source],
                target=id_map[e.target],
                sourceHandle=e.sourceHandle,
                targetHandle=e.targetHandle,
            )
        )
    return GraphSpec(name=spec.name, nodes=new_nodes, edges=new_edges)


@router.get("", response_model=list[TemplateOut])
def list_templates(
    session: Session = Depends(get_session),
    _auth: dict[str, Any] = Depends(get_auth),
):
    rows = session.exec(select(AgateTemplate).order_by(AgateTemplate.name)).all()
    return [
        TemplateOut(
            id=r.id,
            name=r.name,
            description=r.description,
            category=r.category,
        )
        for r in rows
    ]


@router.post("/{template_id}/instantiate", response_model=GraphOut)
def instantiate(
    template_id: str,
    body: InstantiateBody,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
):
    require_project_access(session, auth, body.project_id)
    t = session.get(AgateTemplate, template_id)
    if not t:
        raise HTTPException(404, "Template not found")
    proj = session.get(BackfieldProject, body.project_id)
    if not proj:
        raise HTTPException(404, "Project not found")
    try:
        spec = GraphSpec.model_validate_json(t.spec_json)
    except Exception as e:
        raise HTTPException(500, f"Invalid template spec: {e}") from e
    remapped = _remap_spec(spec)
    try:
        validate_stylebook_refs_for_organization(
            session,
            organization_id=int(proj.organization_id),
            spec=remapped.model_dump(),
        )
    except StylebookGraphRefsError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    graph_name = body.name.strip() if body.name else f"{t.name} (copy)"
    g = AgateGraph(
        name=graph_name,
        spec_json=remapped.model_dump_json(),
        project_id=body.project_id,
    )
    session.add(g)
    session.commit()
    session.refresh(g)
    return GraphOut(
        id=g.id,
        name=g.name,
        project_id=g.project_id,
        spec=GraphSpec.model_validate_json(g.spec_json),
        created_at=g.created_at,
    )
