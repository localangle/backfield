"""Graph CRUD."""

from __future__ import annotations

from datetime import datetime

from api.deps import get_session
from backfield_core import GraphSpec
from backfield_db import AgateGraph, AgateRun, BackfieldProject
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc
from sqlmodel import Session, select

router = APIRouter(prefix="/graphs", tags=["graphs"])


class GraphCreate(BaseModel):
    name: str
    spec: GraphSpec
    project_id: int


class GraphOut(BaseModel):
    id: str
    name: str
    project_id: int
    spec: GraphSpec
    created_at: datetime


@router.post("", response_model=GraphOut)
def create_graph(body: GraphCreate, session: Session = Depends(get_session)):
    p = session.get(BackfieldProject, body.project_id)
    if not p:
        raise HTTPException(404, "Project not found")
    g = AgateGraph(
        name=body.name,
        spec_json=body.spec.model_dump_json(),
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


@router.get("", response_model=list[GraphOut])
def list_graphs(session: Session = Depends(get_session)):
    rows = session.exec(select(AgateGraph).order_by(desc(AgateGraph.created_at))).all()
    return [
        GraphOut(
            id=r.id,
            name=r.name,
            project_id=r.project_id,
            spec=GraphSpec.model_validate_json(r.spec_json),
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.get("/{graph_id}", response_model=GraphOut)
def get_graph(graph_id: str, session: Session = Depends(get_session)):
    g = session.get(AgateGraph, graph_id)
    if not g:
        raise HTTPException(404, "Graph not found")
    return GraphOut(
        id=g.id,
        name=g.name,
        project_id=g.project_id,
        spec=GraphSpec.model_validate_json(g.spec_json),
        created_at=g.created_at,
    )


@router.put("/{graph_id}", response_model=GraphOut)
def update_graph(
    graph_id: str, body: GraphCreate, session: Session = Depends(get_session)
):
    g = session.get(AgateGraph, graph_id)
    if not g:
        raise HTTPException(404, "Graph not found")
    p = session.get(BackfieldProject, body.project_id)
    if not p:
        raise HTTPException(404, "Project not found")
    g.name = body.name
    g.spec_json = body.spec.model_dump_json()
    g.project_id = body.project_id
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


@router.delete("/{graph_id}", status_code=204)
def delete_graph(graph_id: str, session: Session = Depends(get_session)):
    g = session.get(AgateGraph, graph_id)
    if not g:
        raise HTTPException(404, "Graph not found")
    for run in session.exec(select(AgateRun).where(AgateRun.graph_id == graph_id)).all():
        session.delete(run)
    session.delete(g)
    session.commit()
    return None
