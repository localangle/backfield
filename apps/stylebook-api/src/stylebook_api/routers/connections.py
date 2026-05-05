"""Directed ``stylebook_connections`` graph (nested under canonical locations + natures)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from backfield_auth.gate import require_project_access
from backfield_db import StylebookConnection
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_
from sqlmodel import Session, select

from stylebook_api.catalog_scope import StylebookSlugQuery
from stylebook_api.deps import get_auth, get_session
from stylebook_api.helpers.connections_utils import (
    get_canonical_display_name,
    normalize_connection_entity_id,
    validate_canonical_exists,
    validate_connection_pair,
    validate_not_self_connection,
)
from stylebook_api.routers.locations import _project_by_slug, _require_stylebook_id


def _escape_ilike_metacharacters(s: str) -> str:
    """Escape ``%`` and ``_`` for SQL ``ILIKE`` patterns (use with ``escape='\\\\'``)."""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

connections_router = APIRouter(tags=["connections"])
locations_connections_router = APIRouter(prefix="/v1", tags=["connections"])


class ConnectionResponse(BaseModel):
    id: int
    from_entity_type: str
    from_entity_id: str
    from_display_name: str
    to_entity_type: str
    to_entity_id: str
    to_display_name: str
    nature: str
    created_at: datetime | None = None


class ConnectionListResponse(BaseModel):
    connections: list[ConnectionResponse]


class CreateConnectionRequest(BaseModel):
    to_entity_type: str = Field(..., description="person, location, organization, or work")
    to_entity_id: int | str | UUID = Field(
        ...,
        description="UUID string for location; int for stubs",
    )
    nature: str = Field(..., min_length=1)


class UpdateConnectionRequest(BaseModel):
    nature: str = Field(..., min_length=1)


class NaturesResponse(BaseModel):
    natures: list[str]


def _display_name(
    session: Session,
    project_id: int,
    entity_type: str,
    entity_id: str | int | UUID,
    catalog_stylebook_id: int | None = None,
) -> str:
    name = get_canonical_display_name(
        session, project_id, entity_type, entity_id, catalog_stylebook_id
    )
    if name:
        return name
    sid = normalize_connection_entity_id(entity_type, entity_id)
    return f"{entity_type} #{sid}"


def _list_connections_for_entity(
    session: Session,
    project_id: int,
    entity_type: str,
    entity_id: str,
    catalog_stylebook_id: int | None = None,
) -> list[ConnectionResponse]:
    conns = session.exec(
        select(StylebookConnection)
        .where(
            StylebookConnection.project_id == project_id,
            or_(
                and_(
                    StylebookConnection.from_entity_type == entity_type,
                    StylebookConnection.from_entity_id == entity_id,
                ),
                and_(
                    StylebookConnection.to_entity_type == entity_type,
                    StylebookConnection.to_entity_id == entity_id,
                ),
            ),
        )
        .order_by(StylebookConnection.created_at)
    ).all()
    out: list[ConnectionResponse] = []
    for c in conns:
        out.append(
            ConnectionResponse(
                id=int(c.id),  # type: ignore[arg-type]
                from_entity_type=c.from_entity_type,
                from_entity_id=c.from_entity_id,
                from_display_name=_display_name(
                    session,
                    project_id,
                    c.from_entity_type,
                    c.from_entity_id,
                    catalog_stylebook_id,
                ),
                to_entity_type=c.to_entity_type,
                to_entity_id=c.to_entity_id,
                to_display_name=_display_name(
                    session,
                    project_id,
                    c.to_entity_type,
                    c.to_entity_id,
                    catalog_stylebook_id,
                ),
                nature=c.nature,
                created_at=c.created_at,
            )
        )
    return out


@connections_router.get("/natures", response_model=NaturesResponse)
def list_connection_natures(
    project_slug: str = Query(...),
    q: str | None = Query(None),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> NaturesResponse:
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    stmt = (
        select(StylebookConnection.nature)
        .where(StylebookConnection.project_id == int(proj.id))
        .distinct()
    )
    if q and q.strip():
        esc = _escape_ilike_metacharacters(q.strip())
        stmt = stmt.where(StylebookConnection.nature.ilike(f"%{esc}%", escape="\\"))
    stmt = stmt.order_by(StylebookConnection.nature).limit(100)
    rows = session.exec(stmt).all()
    return NaturesResponse(natures=list(rows))


@locations_connections_router.get(
    "/canonical-locations/{location_id}/connections",
    response_model=ConnectionListResponse,
)
def list_location_connections(
    location_id: UUID,
    project_slug: str = Query(...),
    stylebook_slug: StylebookSlugQuery = None,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> ConnectionListResponse:
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    sb_id = _require_stylebook_id(session, proj, stylebook_slug)
    loc_key = str(location_id)
    validate_canonical_exists(session, int(proj.id), "location", location_id, sb_id)
    rows = _list_connections_for_entity(
        session, int(proj.id), "location", loc_key, sb_id
    )
    return ConnectionListResponse(connections=rows)


@locations_connections_router.post(
    "/canonical-locations/{location_id}/connections",
    response_model=ConnectionResponse,
)
def create_location_connection(
    location_id: UUID,
    project_slug: str = Query(...),
    stylebook_slug: StylebookSlugQuery = None,
    payload: CreateConnectionRequest = Body(...),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> ConnectionResponse:
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    sb_id = _require_stylebook_id(session, proj, stylebook_slug)
    loc_key = str(location_id)
    validate_canonical_exists(session, int(proj.id), "location", location_id, sb_id)
    validate_connection_pair("location", payload.to_entity_type)
    validate_canonical_exists(
        session, int(proj.id), payload.to_entity_type, payload.to_entity_id, sb_id
    )
    to_key = normalize_connection_entity_id(payload.to_entity_type, payload.to_entity_id)
    validate_not_self_connection(
        "location",
        loc_key,
        payload.to_entity_type,
        to_key,
    )
    conn = StylebookConnection(
        project_id=int(proj.id),
        from_entity_type="location",
        from_entity_id=loc_key,
        to_entity_type=payload.to_entity_type,
        to_entity_id=to_key,
        nature=payload.nature.strip(),
    )
    session.add(conn)
    session.commit()
    session.refresh(conn)
    return ConnectionResponse(
        id=int(conn.id),  # type: ignore[arg-type]
        from_entity_type=conn.from_entity_type,
        from_entity_id=conn.from_entity_id,
        from_display_name=_display_name(
            session, int(proj.id), "location", location_id, sb_id
        ),
        to_entity_type=conn.to_entity_type,
        to_entity_id=conn.to_entity_id,
        to_display_name=_display_name(
            session,
            int(proj.id),
            conn.to_entity_type,
            conn.to_entity_id,
            sb_id,
        ),
        nature=conn.nature,
        created_at=conn.created_at,
    )


@locations_connections_router.patch(
    "/canonical-locations/{location_id}/connections/{connection_id}",
    response_model=ConnectionResponse,
)
def update_location_connection(
    location_id: UUID,
    connection_id: int,
    project_slug: str = Query(...),
    stylebook_slug: StylebookSlugQuery = None,
    payload: UpdateConnectionRequest = Body(...),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> ConnectionResponse:
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    sb_id = _require_stylebook_id(session, proj, stylebook_slug)
    loc_key = str(location_id)
    validate_canonical_exists(session, int(proj.id), "location", location_id, sb_id)
    conn = session.exec(
        select(StylebookConnection).where(
            StylebookConnection.id == connection_id,
            StylebookConnection.project_id == int(proj.id),
            or_(
                and_(
                    StylebookConnection.from_entity_type == "location",
                    StylebookConnection.from_entity_id == loc_key,
                ),
                and_(
                    StylebookConnection.to_entity_type == "location",
                    StylebookConnection.to_entity_id == loc_key,
                ),
            ),
        )
    ).first()
    if conn is None:
        raise HTTPException(status_code=404, detail="Connection not found")
    conn.nature = payload.nature.strip()
    session.add(conn)
    session.commit()
    session.refresh(conn)
    return ConnectionResponse(
        id=int(conn.id),  # type: ignore[arg-type]
        from_entity_type=conn.from_entity_type,
        from_entity_id=conn.from_entity_id,
        from_display_name=_display_name(
            session,
            int(proj.id),
            conn.from_entity_type,
            conn.from_entity_id,
            sb_id,
        ),
        to_entity_type=conn.to_entity_type,
        to_entity_id=conn.to_entity_id,
        to_display_name=_display_name(
            session,
            int(proj.id),
            conn.to_entity_type,
            conn.to_entity_id,
            sb_id,
        ),
        nature=conn.nature,
        created_at=conn.created_at,
    )


@locations_connections_router.delete("/canonical-locations/{location_id}/connections/{connection_id}")
def delete_location_connection(
    location_id: UUID,
    connection_id: int,
    project_slug: str = Query(...),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> dict[str, bool]:
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    loc_key = str(location_id)
    conn = session.exec(
        select(StylebookConnection).where(
            StylebookConnection.id == connection_id,
            StylebookConnection.project_id == int(proj.id),
            or_(
                and_(
                    StylebookConnection.from_entity_type == "location",
                    StylebookConnection.from_entity_id == loc_key,
                ),
                and_(
                    StylebookConnection.to_entity_type == "location",
                    StylebookConnection.to_entity_id == loc_key,
                ),
            ),
        )
    ).first()
    if conn is None:
        raise HTTPException(status_code=404, detail="Connection not found")
    session.delete(conn)
    session.commit()
    return {"ok": True}
