"""Directed ``stylebook_connections`` graph (nested under canonical locations + natures)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from backfield_auth.gate import require_project_access
from backfield_db import (
    BackfieldProject,
    StylebookConnection,
    StylebookLocationCanonical,
    StylebookOrganizationCanonical,
    StylebookPersonCanonical,
)
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
from stylebook_api.helpers.project_scope import (
    project_by_slug as _project_by_slug,
)
from stylebook_api.helpers.project_scope import (
    require_stylebook_id as _require_stylebook_id,
)
from stylebook_api.stylebook_permissions import require_stylebook_edit_access
from stylebook_api.stylebook_scope import require_stylebook_by_slug_in_auth_org


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
    evidence_json: dict[str, Any] | None = None
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


def _connection_response_from_row(
    session: Session,
    *,
    project_id: int,
    conn: StylebookConnection,
    catalog_stylebook_id: int | None = None,
) -> ConnectionResponse:
    return ConnectionResponse(
        id=int(conn.id),  # type: ignore[arg-type]
        from_entity_type=conn.from_entity_type,
        from_entity_id=conn.from_entity_id,
        from_display_name=_display_name(
            session,
            project_id,
            conn.from_entity_type,
            conn.from_entity_id,
            catalog_stylebook_id,
        ),
        to_entity_type=conn.to_entity_type,
        to_entity_id=conn.to_entity_id,
        to_display_name=_display_name(
            session,
            project_id,
            conn.to_entity_type,
            conn.to_entity_id,
            catalog_stylebook_id,
        ),
        nature=conn.nature,
        evidence_json=conn.evidence_json if isinstance(conn.evidence_json, dict) else None,
        created_at=conn.created_at,
    )


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
    return [
        _connection_response_from_row(
            session,
            project_id=project_id,
            conn=c,
            catalog_stylebook_id=catalog_stylebook_id,
        )
        for c in conns
    ]


def _stylebook_project_ids(session: Session, *, organization_id: int) -> list[int]:
    rows = session.exec(
        select(BackfieldProject.id)
        .where(BackfieldProject.organization_id == organization_id)
        .order_by(BackfieldProject.id.asc())
    ).all()
    return [int(r) for r in rows if r is not None]


def _stylebook_storage_project_id(session: Session, *, organization_id: int) -> int:
    project_ids = _stylebook_project_ids(session, organization_id=organization_id)
    if not project_ids:
        raise HTTPException(
            status_code=400,
            detail="This stylebook needs at least one project before connections can be edited.",
        )
    return project_ids[0]


def _canonical_in_stylebook_or_404(
    session: Session,
    *,
    stylebook_id: int,
    canonical_id: UUID,
) -> None:
    canon = session.get(StylebookLocationCanonical, str(canonical_id))
    if canon is None or int(canon.stylebook_id) != int(stylebook_id):
        raise HTTPException(status_code=404, detail="Canonical location not found")


def _canonical_person_in_stylebook_or_404(
    session: Session,
    *,
    stylebook_id: int,
    canonical_id: UUID,
) -> None:
    canon = session.get(StylebookPersonCanonical, str(canonical_id))
    if canon is None or int(canon.stylebook_id) != int(stylebook_id):
        raise HTTPException(status_code=404, detail="Canonical person not found")


def _canonical_organization_in_stylebook_or_404(
    session: Session,
    *,
    stylebook_id: int,
    canonical_id: UUID,
) -> None:
    canon = session.get(StylebookOrganizationCanonical, str(canonical_id))
    if canon is None or int(canon.stylebook_id) != int(stylebook_id):
        raise HTTPException(status_code=404, detail="Canonical organization not found")


def _connection_dedupe_key(c: StylebookConnection) -> tuple[str, str, str, str, str]:
    return (
        str(c.from_entity_type),
        str(c.from_entity_id),
        str(c.to_entity_type),
        str(c.to_entity_id),
        str(c.nature),
    )


def _list_stylebook_connections_for_entity(
    session: Session,
    *,
    project_ids: list[int],
    entity_type: str,
    entity_id: str,
    catalog_stylebook_id: int,
    display_project_id: int,
) -> list[ConnectionResponse]:
    conns = session.exec(
        select(StylebookConnection)
        .where(
            StylebookConnection.project_id.in_(project_ids),
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
        .order_by(StylebookConnection.created_at, StylebookConnection.id)
    ).all()
    deduped: list[StylebookConnection] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for conn in conns:
        key = _connection_dedupe_key(conn)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(conn)
    return [
        _connection_response_from_row(
            session,
            project_id=display_project_id,
            conn=c,
            catalog_stylebook_id=catalog_stylebook_id,
        )
        for c in deduped
    ]


def _matching_stylebook_connection_rows(
    session: Session,
    *,
    project_ids: list[int],
    connection: StylebookConnection,
) -> list[StylebookConnection]:
    return session.exec(
        select(StylebookConnection)
        .where(
            StylebookConnection.project_id.in_(project_ids),
            StylebookConnection.from_entity_type == connection.from_entity_type,
            StylebookConnection.from_entity_id == connection.from_entity_id,
            StylebookConnection.to_entity_type == connection.to_entity_type,
            StylebookConnection.to_entity_id == connection.to_entity_id,
            StylebookConnection.nature == connection.nature,
        )
        .order_by(StylebookConnection.id.asc())
    ).all()


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
    return _connection_response_from_row(
        session,
        project_id=int(proj.id),
        conn=conn,
        catalog_stylebook_id=sb_id,
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
    return _connection_response_from_row(
        session,
        project_id=int(proj.id),
        conn=conn,
        catalog_stylebook_id=sb_id,
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


@connections_router.get("/stylebooks/{stylebook_slug}/natures", response_model=NaturesResponse)
def list_stylebook_connection_natures(
    stylebook_slug: str,
    q: str | None = Query(None),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> NaturesResponse:
    sb = require_stylebook_by_slug_in_auth_org(
        session, auth=auth, stylebook_slug=stylebook_slug
    )
    project_ids = _stylebook_project_ids(session, organization_id=int(sb.organization_id))
    if not project_ids:
        return NaturesResponse(natures=[])
    stmt = (
        select(StylebookConnection.nature)
        .where(StylebookConnection.project_id.in_(project_ids))
        .distinct()
    )
    if q and q.strip():
        esc = _escape_ilike_metacharacters(q.strip())
        stmt = stmt.where(StylebookConnection.nature.ilike(f"%{esc}%", escape="\\"))
    stmt = stmt.order_by(StylebookConnection.nature).limit(100)
    rows = session.exec(stmt).all()
    return NaturesResponse(natures=list(rows))


@locations_connections_router.get(
    "/stylebooks/{stylebook_slug}/canonical-locations/{location_id}/connections",
    response_model=ConnectionListResponse,
)
def list_stylebook_location_connections(
    stylebook_slug: str,
    location_id: UUID,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> ConnectionListResponse:
    sb = require_stylebook_by_slug_in_auth_org(
        session, auth=auth, stylebook_slug=stylebook_slug
    )
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    _canonical_in_stylebook_or_404(
        session, stylebook_id=int(sb.id), canonical_id=location_id
    )
    project_ids = _stylebook_project_ids(session, organization_id=int(sb.organization_id))
    if not project_ids:
        return ConnectionListResponse(connections=[])
    rows = _list_stylebook_connections_for_entity(
        session,
        project_ids=project_ids,
        entity_type="location",
        entity_id=str(location_id),
        catalog_stylebook_id=int(sb.id),
        display_project_id=project_ids[0],
    )
    return ConnectionListResponse(connections=rows)


@locations_connections_router.get(
    "/stylebooks/{stylebook_slug}/canonical-people/{person_id}/connections",
    response_model=ConnectionListResponse,
)
def list_stylebook_person_connections(
    stylebook_slug: str,
    person_id: UUID,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> ConnectionListResponse:
    sb = require_stylebook_by_slug_in_auth_org(
        session, auth=auth, stylebook_slug=stylebook_slug
    )
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    _canonical_person_in_stylebook_or_404(
        session, stylebook_id=int(sb.id), canonical_id=person_id
    )
    project_ids = _stylebook_project_ids(session, organization_id=int(sb.organization_id))
    if not project_ids:
        return ConnectionListResponse(connections=[])
    rows = _list_stylebook_connections_for_entity(
        session,
        project_ids=project_ids,
        entity_type="person",
        entity_id=str(person_id),
        catalog_stylebook_id=int(sb.id),
        display_project_id=project_ids[0],
    )
    return ConnectionListResponse(connections=rows)


@locations_connections_router.get(
    "/stylebooks/{stylebook_slug}/canonical-organizations/{organization_id}/connections",
    response_model=ConnectionListResponse,
)
def list_stylebook_organization_connections(
    stylebook_slug: str,
    organization_id: UUID,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> ConnectionListResponse:
    sb = require_stylebook_by_slug_in_auth_org(
        session, auth=auth, stylebook_slug=stylebook_slug
    )
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    _canonical_organization_in_stylebook_or_404(
        session, stylebook_id=int(sb.id), canonical_id=organization_id
    )
    project_ids = _stylebook_project_ids(session, organization_id=int(sb.organization_id))
    if not project_ids:
        return ConnectionListResponse(connections=[])
    rows = _list_stylebook_connections_for_entity(
        session,
        project_ids=project_ids,
        entity_type="organization",
        entity_id=str(organization_id),
        catalog_stylebook_id=int(sb.id),
        display_project_id=project_ids[0],
    )
    return ConnectionListResponse(connections=rows)


@locations_connections_router.post(
    "/stylebooks/{stylebook_slug}/canonical-locations/{location_id}/connections",
    response_model=ConnectionResponse,
)
def create_stylebook_location_connection(
    stylebook_slug: str,
    location_id: UUID,
    payload: CreateConnectionRequest = Body(...),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> ConnectionResponse:
    require_stylebook_edit_access(session, auth=auth, stylebook_slug=stylebook_slug)
    sb = require_stylebook_by_slug_in_auth_org(
        session, auth=auth, stylebook_slug=stylebook_slug
    )
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    storage_project_id = _stylebook_storage_project_id(
        session, organization_id=int(sb.organization_id)
    )
    project_ids = _stylebook_project_ids(session, organization_id=int(sb.organization_id))
    loc_key = str(location_id)
    validate_canonical_exists(
        session, storage_project_id, "location", location_id, int(sb.id)
    )
    validate_connection_pair("location", payload.to_entity_type)
    validate_canonical_exists(
        session,
        storage_project_id,
        payload.to_entity_type,
        payload.to_entity_id,
        int(sb.id),
    )
    to_key = normalize_connection_entity_id(payload.to_entity_type, payload.to_entity_id)
    validate_not_self_connection(
        "location",
        loc_key,
        payload.to_entity_type,
        to_key,
    )
    nature = payload.nature.strip()
    existing = session.exec(
        select(StylebookConnection)
        .where(
            StylebookConnection.project_id.in_(project_ids),
            StylebookConnection.from_entity_type == "location",
            StylebookConnection.from_entity_id == loc_key,
            StylebookConnection.to_entity_type == payload.to_entity_type,
            StylebookConnection.to_entity_id == to_key,
            StylebookConnection.nature == nature,
        )
        .order_by(StylebookConnection.created_at, StylebookConnection.id)
    ).first()
    if existing is None:
        existing = StylebookConnection(
            project_id=storage_project_id,
            from_entity_type="location",
            from_entity_id=loc_key,
            to_entity_type=payload.to_entity_type,
            to_entity_id=to_key,
            nature=nature,
        )
        session.add(existing)
        session.commit()
        session.refresh(existing)
    return _connection_response_from_row(
        session,
        project_id=storage_project_id,
        conn=existing,
        catalog_stylebook_id=int(sb.id),
    )


@locations_connections_router.patch(
    "/stylebooks/{stylebook_slug}/canonical-locations/{location_id}/connections/{connection_id}",
    response_model=ConnectionResponse,
)
def update_stylebook_location_connection(
    stylebook_slug: str,
    location_id: UUID,
    connection_id: int,
    payload: UpdateConnectionRequest = Body(...),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> ConnectionResponse:
    require_stylebook_edit_access(session, auth=auth, stylebook_slug=stylebook_slug)
    sb = require_stylebook_by_slug_in_auth_org(
        session, auth=auth, stylebook_slug=stylebook_slug
    )
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    storage_project_id = _stylebook_storage_project_id(
        session, organization_id=int(sb.organization_id)
    )
    project_ids = _stylebook_project_ids(session, organization_id=int(sb.organization_id))
    validate_canonical_exists(
        session, storage_project_id, "location", location_id, int(sb.id)
    )
    loc_key = str(location_id)
    conn = session.exec(
        select(StylebookConnection).where(
            StylebookConnection.id == connection_id,
            StylebookConnection.project_id.in_(project_ids),
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
    rows = _matching_stylebook_connection_rows(
        session, project_ids=project_ids, connection=conn
    )
    new_nature = payload.nature.strip()
    for row in rows:
        row.nature = new_nature
        session.add(row)
    session.commit()
    session.refresh(conn)
    return _connection_response_from_row(
        session,
        project_id=storage_project_id,
        conn=conn,
        catalog_stylebook_id=int(sb.id),
    )


@locations_connections_router.delete(
    "/stylebooks/{stylebook_slug}/canonical-locations/{location_id}/connections/{connection_id}"
)
def delete_stylebook_location_connection(
    stylebook_slug: str,
    location_id: UUID,
    connection_id: int,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> dict[str, bool]:
    require_stylebook_edit_access(session, auth=auth, stylebook_slug=stylebook_slug)
    sb = require_stylebook_by_slug_in_auth_org(
        session, auth=auth, stylebook_slug=stylebook_slug
    )
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    storage_project_id = _stylebook_storage_project_id(
        session, organization_id=int(sb.organization_id)
    )
    project_ids = _stylebook_project_ids(session, organization_id=int(sb.organization_id))
    validate_canonical_exists(
        session, storage_project_id, "location", location_id, int(sb.id)
    )
    loc_key = str(location_id)
    conn = session.exec(
        select(StylebookConnection).where(
            StylebookConnection.id == connection_id,
            StylebookConnection.project_id.in_(project_ids),
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
    rows = _matching_stylebook_connection_rows(
        session, project_ids=project_ids, connection=conn
    )
    for row in rows:
        session.delete(row)
    session.commit()
    return {"ok": True}


def _create_stylebook_entity_connection(
    session: Session,
    *,
    storage_project_id: int,
    project_ids: list[int],
    catalog_stylebook_id: int,
    from_entity_type: str,
    from_entity_id: str,
    payload: CreateConnectionRequest,
) -> ConnectionResponse:
    validate_connection_pair(from_entity_type, payload.to_entity_type)
    validate_canonical_exists(
        session,
        storage_project_id,
        payload.to_entity_type,
        payload.to_entity_id,
        catalog_stylebook_id,
    )
    to_key = normalize_connection_entity_id(payload.to_entity_type, payload.to_entity_id)
    validate_not_self_connection(
        from_entity_type,
        from_entity_id,
        payload.to_entity_type,
        to_key,
    )
    nature = payload.nature.strip()
    existing = session.exec(
        select(StylebookConnection)
        .where(
            StylebookConnection.project_id.in_(project_ids),
            StylebookConnection.from_entity_type == from_entity_type,
            StylebookConnection.from_entity_id == from_entity_id,
            StylebookConnection.to_entity_type == payload.to_entity_type,
            StylebookConnection.to_entity_id == to_key,
            StylebookConnection.nature == nature,
        )
        .order_by(StylebookConnection.created_at, StylebookConnection.id)
    ).first()
    if existing is None:
        existing = StylebookConnection(
            project_id=storage_project_id,
            from_entity_type=from_entity_type,
            from_entity_id=from_entity_id,
            to_entity_type=payload.to_entity_type,
            to_entity_id=to_key,
            nature=nature,
        )
        session.add(existing)
        session.commit()
        session.refresh(existing)
    return _connection_response_from_row(
        session,
        project_id=storage_project_id,
        conn=existing,
        catalog_stylebook_id=catalog_stylebook_id,
    )


def _find_stylebook_entity_connection(
    session: Session,
    *,
    project_ids: list[int],
    entity_type: str,
    entity_id: str,
    connection_id: int,
) -> StylebookConnection:
    conn = session.exec(
        select(StylebookConnection).where(
            StylebookConnection.id == connection_id,
            StylebookConnection.project_id.in_(project_ids),
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
    ).first()
    if conn is None:
        raise HTTPException(status_code=404, detail="Connection not found")
    return conn


@locations_connections_router.post(
    "/stylebooks/{stylebook_slug}/canonical-people/{person_id}/connections",
    response_model=ConnectionResponse,
)
def create_stylebook_person_connection(
    stylebook_slug: str,
    person_id: UUID,
    payload: CreateConnectionRequest = Body(...),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> ConnectionResponse:
    require_stylebook_edit_access(session, auth=auth, stylebook_slug=stylebook_slug)
    sb = require_stylebook_by_slug_in_auth_org(
        session, auth=auth, stylebook_slug=stylebook_slug
    )
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    storage_project_id = _stylebook_storage_project_id(
        session, organization_id=int(sb.organization_id)
    )
    project_ids = _stylebook_project_ids(session, organization_id=int(sb.organization_id))
    person_key = str(person_id)
    validate_canonical_exists(
        session, storage_project_id, "person", person_id, int(sb.id)
    )
    return _create_stylebook_entity_connection(
        session,
        storage_project_id=storage_project_id,
        project_ids=project_ids,
        catalog_stylebook_id=int(sb.id),
        from_entity_type="person",
        from_entity_id=person_key,
        payload=payload,
    )


@locations_connections_router.patch(
    "/stylebooks/{stylebook_slug}/canonical-people/{person_id}/connections/{connection_id}",
    response_model=ConnectionResponse,
)
def update_stylebook_person_connection(
    stylebook_slug: str,
    person_id: UUID,
    connection_id: int,
    payload: UpdateConnectionRequest = Body(...),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> ConnectionResponse:
    require_stylebook_edit_access(session, auth=auth, stylebook_slug=stylebook_slug)
    sb = require_stylebook_by_slug_in_auth_org(
        session, auth=auth, stylebook_slug=stylebook_slug
    )
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    storage_project_id = _stylebook_storage_project_id(
        session, organization_id=int(sb.organization_id)
    )
    project_ids = _stylebook_project_ids(session, organization_id=int(sb.organization_id))
    person_key = str(person_id)
    validate_canonical_exists(
        session, storage_project_id, "person", person_id, int(sb.id)
    )
    conn = _find_stylebook_entity_connection(
        session,
        project_ids=project_ids,
        entity_type="person",
        entity_id=person_key,
        connection_id=connection_id,
    )
    rows = _matching_stylebook_connection_rows(
        session, project_ids=project_ids, connection=conn
    )
    new_nature = payload.nature.strip()
    for row in rows:
        row.nature = new_nature
        session.add(row)
    session.commit()
    session.refresh(conn)
    return _connection_response_from_row(
        session,
        project_id=storage_project_id,
        conn=conn,
        catalog_stylebook_id=int(sb.id),
    )


@locations_connections_router.delete(
    "/stylebooks/{stylebook_slug}/canonical-people/{person_id}/connections/{connection_id}"
)
def delete_stylebook_person_connection(
    stylebook_slug: str,
    person_id: UUID,
    connection_id: int,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> dict[str, bool]:
    require_stylebook_edit_access(session, auth=auth, stylebook_slug=stylebook_slug)
    sb = require_stylebook_by_slug_in_auth_org(
        session, auth=auth, stylebook_slug=stylebook_slug
    )
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    storage_project_id = _stylebook_storage_project_id(
        session, organization_id=int(sb.organization_id)
    )
    project_ids = _stylebook_project_ids(session, organization_id=int(sb.organization_id))
    person_key = str(person_id)
    validate_canonical_exists(
        session, storage_project_id, "person", person_id, int(sb.id)
    )
    conn = _find_stylebook_entity_connection(
        session,
        project_ids=project_ids,
        entity_type="person",
        entity_id=person_key,
        connection_id=connection_id,
    )
    rows = _matching_stylebook_connection_rows(
        session, project_ids=project_ids, connection=conn
    )
    for row in rows:
        session.delete(row)
    session.commit()
    return {"ok": True}


@locations_connections_router.post(
    "/stylebooks/{stylebook_slug}/canonical-organizations/{organization_id}/connections",
    response_model=ConnectionResponse,
)
def create_stylebook_organization_connection(
    stylebook_slug: str,
    organization_id: UUID,
    payload: CreateConnectionRequest = Body(...),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> ConnectionResponse:
    require_stylebook_edit_access(session, auth=auth, stylebook_slug=stylebook_slug)
    sb = require_stylebook_by_slug_in_auth_org(
        session, auth=auth, stylebook_slug=stylebook_slug
    )
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    storage_project_id = _stylebook_storage_project_id(
        session, organization_id=int(sb.organization_id)
    )
    project_ids = _stylebook_project_ids(session, organization_id=int(sb.organization_id))
    org_key = str(organization_id)
    validate_canonical_exists(
        session, storage_project_id, "organization", organization_id, int(sb.id)
    )
    return _create_stylebook_entity_connection(
        session,
        storage_project_id=storage_project_id,
        project_ids=project_ids,
        catalog_stylebook_id=int(sb.id),
        from_entity_type="organization",
        from_entity_id=org_key,
        payload=payload,
    )


@locations_connections_router.patch(
    "/stylebooks/{stylebook_slug}/canonical-organizations/{organization_id}/connections/{connection_id}",
    response_model=ConnectionResponse,
)
def update_stylebook_organization_connection(
    stylebook_slug: str,
    organization_id: UUID,
    connection_id: int,
    payload: UpdateConnectionRequest = Body(...),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> ConnectionResponse:
    require_stylebook_edit_access(session, auth=auth, stylebook_slug=stylebook_slug)
    sb = require_stylebook_by_slug_in_auth_org(
        session, auth=auth, stylebook_slug=stylebook_slug
    )
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    storage_project_id = _stylebook_storage_project_id(
        session, organization_id=int(sb.organization_id)
    )
    project_ids = _stylebook_project_ids(session, organization_id=int(sb.organization_id))
    org_key = str(organization_id)
    validate_canonical_exists(
        session, storage_project_id, "organization", organization_id, int(sb.id)
    )
    conn = _find_stylebook_entity_connection(
        session,
        project_ids=project_ids,
        entity_type="organization",
        entity_id=org_key,
        connection_id=connection_id,
    )
    rows = _matching_stylebook_connection_rows(
        session, project_ids=project_ids, connection=conn
    )
    new_nature = payload.nature.strip()
    for row in rows:
        row.nature = new_nature
        session.add(row)
    session.commit()
    session.refresh(conn)
    return _connection_response_from_row(
        session,
        project_id=storage_project_id,
        conn=conn,
        catalog_stylebook_id=int(sb.id),
    )


@locations_connections_router.delete(
    "/stylebooks/{stylebook_slug}/canonical-organizations/{organization_id}/connections/{connection_id}"
)
def delete_stylebook_organization_connection(
    stylebook_slug: str,
    organization_id: UUID,
    connection_id: int,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> dict[str, bool]:
    require_stylebook_edit_access(session, auth=auth, stylebook_slug=stylebook_slug)
    sb = require_stylebook_by_slug_in_auth_org(
        session, auth=auth, stylebook_slug=stylebook_slug
    )
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    storage_project_id = _stylebook_storage_project_id(
        session, organization_id=int(sb.organization_id)
    )
    project_ids = _stylebook_project_ids(session, organization_id=int(sb.organization_id))
    org_key = str(organization_id)
    validate_canonical_exists(
        session, storage_project_id, "organization", organization_id, int(sb.id)
    )
    conn = _find_stylebook_entity_connection(
        session,
        project_ids=project_ids,
        entity_type="organization",
        entity_id=org_key,
        connection_id=connection_id,
    )
    rows = _matching_stylebook_connection_rows(
        session, project_ids=project_ids, connection=conn
    )
    for row in rows:
        session.delete(row)
    session.commit()
    return {"ok": True}
