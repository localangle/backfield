"""Directed ``stylebook_connections`` graph (nested under canonical locations + natures)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from backfield_auth.gate import require_project_access
from backfield_db import (
    BackfieldProject,
    StylebookConnection,
    StylebookConnectionEvidence,
    StylebookLocationCanonical,
    StylebookOrganizationCanonical,
    StylebookPersonCanonical,
)
from backfield_entities.activity import (
    EVENT_CONNECTION_CLOSED,
    EVENT_CONNECTION_CREATED,
    EVENT_CONNECTION_EVIDENCE_ADDED,
    EVENT_CONNECTION_REOPENED,
    EVENT_CONNECTION_UPDATED,
    log_stylebook_activity_safe,
)
from backfield_entities.connections.custom_natures import (
    delete_custom_nature,
    ensure_custom_nature_for_manual_slug,
    merged_nature_catalog,
    upsert_custom_nature,
)
from backfield_entities.connections.dedupe import connection_nature_coalesced
from backfield_entities.connections.display import (
    ConnectionEvidenceOut,
    derived_connection_description,
    evidence_out_list,
    legacy_evidence_json_for_connection,
)
from backfield_entities.connections.evidence import reference_time_is_newer
from backfield_entities.connections.natures import temporal_kind_for_nature
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import and_, or_
from sqlmodel import Session, col, select

from stylebook_api.catalog_scope import StylebookSlugQuery
from stylebook_api.deps import get_auth, get_session
from stylebook_api.helpers.connections_utils import (
    get_canonical_display_name,
    normalize_connection_entity_id,
    validate_canonical_exists,
    validate_connection_pair,
    validate_manual_connection_labels,
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

connections_router = APIRouter(tags=["connections"])
locations_connections_router = APIRouter(prefix="/v1", tags=["connections"])

CONNECTIONS_DEFAULT_LIMIT = 10
CONNECTIONS_MAX_LIMIT = 500


def _created_by_user_id(auth: dict[str, Any]) -> int | None:
    if auth.get("type") != "session" or auth.get("user") is None:
        return None
    return int(auth["user"].id)  # type: ignore[union-attr]


def _log_stylebook_connection_event(
    session: Session,
    *,
    stylebook_id: int,
    auth: dict[str, Any],
    event_type: str,
    conn: StylebookConnection,
    payload_json: dict[str, Any] | None = None,
) -> None:
    log_stylebook_activity_safe(
        session,
        stylebook_id=stylebook_id,
        project_id=int(conn.project_id),
        actor_type="user",
        actor_user_id=_created_by_user_id(auth),
        source="connections",
        event_type=event_type,
        entity_type="connection",
        entity_id=str(conn.id),
        entity_label=(
            derived_connection_description(session, connection_id=int(conn.id))  # type: ignore[arg-type]
            or conn.nature
            or ""
        ).strip()
        or None,
        related_entity_type=conn.to_entity_type,
        related_entity_id=conn.to_entity_id,
        related_entity_label=None,
        payload_json={
            "from_entity_type": conn.from_entity_type,
            "from_entity_id": conn.from_entity_id,
            "to_entity_type": conn.to_entity_type,
            "to_entity_id": conn.to_entity_id,
            "nature": conn.nature,
            "description": derived_connection_description(
                session, connection_id=int(conn.id)  # type: ignore[arg-type]
            ),
            **(payload_json or {}),
        },
    )


class ConnectionResponse(BaseModel):
    id: int
    from_entity_type: str
    from_entity_id: str
    from_display_name: str
    to_entity_type: str
    to_entity_id: str
    to_display_name: str
    description: str | None = None
    nature: str | None = None
    temporal_kind: Literal["static", "dynamic"] | None = None
    currentness: Literal["current", "former", "unknown"] | None = None
    currentness_as_of: datetime | None = None
    evidence_json: dict[str, Any] | None = None
    evidence: list[ConnectionEvidenceOut] = []
    closed_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ConnectionListResponse(BaseModel):
    connections: list[ConnectionResponse]
    total: int
    limit: int
    offset: int


class CreateConnectionRequest(BaseModel):
    to_entity_type: str = Field(..., description="person, location, organization, or work")
    to_entity_id: int | str | UUID = Field(
        ...,
        description="UUID string for location; int for stubs",
    )
    nature: str | None = Field(default=None, min_length=1)
    description: str | None = Field(default=None, min_length=1)
    asserted_currentness: Literal["current", "former", "unspecified"] = "unspecified"

    @model_validator(mode="after")
    def _require_nature_or_description(self) -> CreateConnectionRequest:
        nature = (self.nature or "").strip()
        description = (self.description or "").strip()
        if not nature and not description:
            raise ValueError("Provide at least one of nature or description")
        return self


class UpdateConnectionRequest(BaseModel):
    nature: str | None = None
    description: str | None = None
    asserted_currentness: Literal["current", "former", "unspecified"] | None = None

    @model_validator(mode="after")
    def _require_at_least_one_field(self) -> UpdateConnectionRequest:
        if (
            self.nature is None
            and self.description is None
            and self.asserted_currentness is None
        ):
            raise ValueError("Provide at least one of nature or description")
        if self.nature is not None and not self.nature.strip():
            raise ValueError("nature cannot be empty")
        if self.description is not None and not self.description.strip():
            raise ValueError("description cannot be empty")
        return self


class NatureEntryOut(BaseModel):
    slug: str
    label: str
    source: Literal["preferred", "custom"]
    equivalent_to: str | None = None
    temporal_kind: str | None = None


class NaturesResponse(BaseModel):
    natures: list[NatureEntryOut]


class CreateCustomNatureRequest(BaseModel):
    slug: str = Field(..., min_length=1)
    label: str | None = None
    equivalent_to: str | None = None
    temporal_kind: str = "dynamic"


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


def _connection_temporal_kind(
    session: Session,
    conn: StylebookConnection,
    *,
    stylebook_id: int | None = None,
) -> Literal["static", "dynamic"]:
    nature = (conn.nature or "").strip()
    catalog_id = stylebook_id or conn.stylebook_id
    if nature and catalog_id is not None:
        for entry in merged_nature_catalog(
            session,
            stylebook_id=int(catalog_id),
            q=nature,
        ):
            if entry.slug == nature and entry.temporal_kind == "static":
                return "static"
    if nature:
        return temporal_kind_for_nature(
            nature,
            conn.from_entity_type,
            conn.to_entity_type,
        )
    return "dynamic"


def _connection_response_from_row(
    session: Session,
    *,
    project_id: int,
    conn: StylebookConnection,
    catalog_stylebook_id: int | None = None,
) -> ConnectionResponse:
    nature = conn.nature
    temporal = _connection_temporal_kind(
        session,
        conn,
        stylebook_id=catalog_stylebook_id,
    )
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
        description=derived_connection_description(
            session, connection_id=int(conn.id)  # type: ignore[arg-type]
        ),
        nature=nature,
        temporal_kind=temporal,
        currentness=conn.currentness if temporal == "dynamic" else None,
        currentness_as_of=conn.currentness_as_of if temporal == "dynamic" else None,
        evidence_json=legacy_evidence_json_for_connection(
            session, connection_id=int(conn.id)  # type: ignore[arg-type]
        ),
        evidence=evidence_out_list(session, connection_id=int(conn.id)),  # type: ignore[arg-type]
        closed_at=conn.closed_at,
        created_at=conn.created_at,
        updated_at=conn.updated_at,
    )


def _add_manual_evidence(
    session: Session,
    *,
    connection_id: int,
    description: str | None,
    stylebook_id: int | None = None,
    auth: dict[str, Any] | None = None,
    asserted_currentness: Literal["current", "former", "unspecified"] = "unspecified",
) -> None:
    text = (description or "").strip()
    if not text and asserted_currentness == "unspecified":
        return
    conn = session.get(StylebookConnection, int(connection_id))
    if conn is None:
        return
    temporal_kind = _connection_temporal_kind(
        session,
        conn,
        stylebook_id=stylebook_id,
    )
    if temporal_kind == "static" and asserted_currentness != "unspecified":
        raise HTTPException(
            status_code=422,
            detail="Currentness applies only to relationships that can change.",
        )
    # App-level dedupe for null-article manual evidence by quote.
    existing = session.exec(
        select(StylebookConnectionEvidence).where(
            StylebookConnectionEvidence.connection_id == int(connection_id),
            StylebookConnectionEvidence.article_id.is_(None),  # type: ignore[union-attr]
        )
    ).all()
    needle = text.casefold()
    if needle:
        for row in existing:
            for value in (row.quote, row.description, row.reason):
                if (
                    (value or "").strip().casefold() == needle
                    and row.asserted_currentness == asserted_currentness
                ):
                    return
    now = datetime.now(UTC)
    evidence = StylebookConnectionEvidence(
        connection_id=int(connection_id),
        article_id=None,
        description=text or None,
        quote=text or None,
        reason=text or None,
        source="manual",
        asserted_currentness=asserted_currentness,
        currentness_review_source="manual",
        observed_at=now,
    )
    session.add(evidence)
    session.flush()
    if (
        asserted_currentness in {"current", "former"}
        and temporal_kind == "dynamic"
        and reference_time_is_newer(now, conn.currentness_as_of)
    ):
        conn.currentness = asserted_currentness
        conn.currentness_as_of = now
        conn.currentness_evidence_id = int(evidence.id) if evidence.id is not None else None
        session.add(conn)
    if stylebook_id is not None and auth is not None:
        _log_stylebook_connection_event(
            session,
            stylebook_id=int(stylebook_id),
            auth=auth,
            event_type=EVENT_CONNECTION_EVIDENCE_ADDED,
            conn=conn,
        )


def _list_connections_for_entity(
    session: Session,
    project_id: int,
    entity_type: str,
    entity_id: str,
    catalog_stylebook_id: int | None = None,
    *,
    include_closed: bool = False,
    limit: int = CONNECTIONS_DEFAULT_LIMIT,
    offset: int = 0,
) -> ConnectionListResponse:
    filters = [
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
    ]
    if catalog_stylebook_id is not None:
        filters.append(StylebookConnection.stylebook_id == int(catalog_stylebook_id))
    if not include_closed:
        filters.append(col(StylebookConnection.closed_at).is_(None))
    conns = session.exec(
        select(StylebookConnection).where(*filters).order_by(StylebookConnection.created_at)
    ).all()
    rows = [
        _connection_response_from_row(
            session,
            project_id=project_id,
            conn=c,
            catalog_stylebook_id=catalog_stylebook_id,
        )
        for c in conns
    ]
    total = len(rows)
    page = rows[offset : offset + limit]
    return ConnectionListResponse(
        connections=page,
        total=total,
        limit=limit,
        offset=offset,
    )


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
        str(c.nature or ""),
    )


def _apply_connection_update(
    session: Session,
    conn: StylebookConnection,
    payload: UpdateConnectionRequest,
    *,
    stylebook_id: int | None = None,
    auth: dict[str, Any] | None = None,
) -> StylebookConnection:
    new_nature = conn.nature
    current_description = derived_connection_description(
        session, connection_id=int(conn.id)  # type: ignore[arg-type]
    )
    new_description = current_description
    if payload.nature is not None:
        new_nature = validate_manual_connection_labels(
            nature=payload.nature,
            description=new_description,
        )[0]
        if stylebook_id is not None:
            new_nature = ensure_custom_nature_for_manual_slug(
                session,
                stylebook_id=int(stylebook_id),
                nature=new_nature,
            )
    if payload.description is not None:
        new_nature, new_description = validate_manual_connection_labels(
            nature=new_nature,
            description=payload.description,
        )
    conn.nature = new_nature
    temporal_kind = _connection_temporal_kind(
        session,
        conn,
        stylebook_id=stylebook_id,
    )
    if temporal_kind == "static":
        conn.currentness = "unknown"
        conn.currentness_as_of = None
        conn.currentness_evidence_id = None
    if payload.description is not None or payload.asserted_currentness is not None:
        _add_manual_evidence(
            session,
            connection_id=int(conn.id),  # type: ignore[arg-type]
            description=new_description,
            stylebook_id=stylebook_id,
            auth=auth,
            asserted_currentness=payload.asserted_currentness or "unspecified",
        )
    return conn


def _find_existing_connection(
    session: Session,
    *,
    project_ids: list[int],
    from_entity_type: str,
    from_entity_id: str,
    to_entity_type: str,
    to_entity_id: str,
    nature: str | None,
    description: str | None = None,
) -> StylebookConnection | None:
    _ = description
    normalized_nature, _normalized_description = validate_manual_connection_labels(
        nature=nature,
        description=description,
    )
    return session.exec(
        select(StylebookConnection)
        .where(
            StylebookConnection.project_id.in_(project_ids),
            StylebookConnection.from_entity_type == from_entity_type,
            StylebookConnection.from_entity_id == from_entity_id,
            StylebookConnection.to_entity_type == to_entity_type,
            StylebookConnection.to_entity_id == to_entity_id,
            connection_nature_coalesced() == (normalized_nature or ""),
            col(StylebookConnection.closed_at).is_(None),
        )
        .order_by(StylebookConnection.created_at, StylebookConnection.id)
    ).first()


def _list_stylebook_connections_for_entity(
    session: Session,
    *,
    project_ids: list[int],
    entity_type: str,
    entity_id: str,
    catalog_stylebook_id: int,
    display_project_id: int,
    include_closed: bool = False,
    limit: int = CONNECTIONS_DEFAULT_LIMIT,
    offset: int = 0,
) -> ConnectionListResponse:
    _ = project_ids
    filters = [
        StylebookConnection.stylebook_id == int(catalog_stylebook_id),
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
    ]
    if not include_closed:
        filters.append(col(StylebookConnection.closed_at).is_(None))
    conns = list(
        session.exec(
            select(StylebookConnection)
            .where(*filters)
            .order_by(StylebookConnection.created_at, StylebookConnection.id)
        ).all()
    )
    deduped: list[StylebookConnection] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for conn in conns:
        key = _connection_dedupe_key(conn)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(conn)
    total = len(deduped)
    page_rows = deduped[offset : offset + limit]
    return ConnectionListResponse(
        connections=[
            _connection_response_from_row(
                session,
                project_id=display_project_id,
                conn=c,
                catalog_stylebook_id=catalog_stylebook_id,
            )
            for c in page_rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


def _soft_close_connection(
    session: Session,
    *,
    conn: StylebookConnection,
    stylebook_id: int,
    auth: dict[str, Any],
) -> None:
    if conn.closed_at is None:
        conn.closed_at = datetime.now(UTC)
        conn.updated_at = datetime.now(UTC)
        session.add(conn)
        _log_stylebook_connection_event(
            session,
            stylebook_id=stylebook_id,
            auth=auth,
            event_type=EVENT_CONNECTION_CLOSED,
            conn=conn,
        )


def _reopen_connection(
    session: Session,
    *,
    conn: StylebookConnection,
    stylebook_id: int,
    auth: dict[str, Any],
) -> None:
    if conn.closed_at is not None:
        conn.closed_at = None
        conn.updated_at = datetime.now(UTC)
        session.add(conn)
        _log_stylebook_connection_event(
            session,
            stylebook_id=stylebook_id,
            auth=auth,
            event_type=EVENT_CONNECTION_REOPENED,
            conn=conn,
        )


def _natures_response(session: Session, *, stylebook_id: int, q: str | None) -> NaturesResponse:
    entries = merged_nature_catalog(session, stylebook_id=stylebook_id, q=q)
    return NaturesResponse(
        natures=[
            NatureEntryOut(
                slug=e.slug,
                label=e.label,
                source=e.source,
                equivalent_to=e.equivalent_to,
                temporal_kind=e.temporal_kind,
            )
            for e in entries
        ]
    )


def _matching_stylebook_connection_rows(
    session: Session,
    *,
    project_ids: list[int],
    connection: StylebookConnection,
    open_only: bool = True,
) -> list[StylebookConnection]:
    filters = [
        StylebookConnection.project_id.in_(project_ids),
        StylebookConnection.from_entity_type == connection.from_entity_type,
        StylebookConnection.from_entity_id == connection.from_entity_id,
        StylebookConnection.to_entity_type == connection.to_entity_type,
        StylebookConnection.to_entity_id == connection.to_entity_id,
        connection_nature_coalesced() == (connection.nature or ""),
    ]
    if open_only:
        filters.append(col(StylebookConnection.closed_at).is_(None))
    else:
        filters.append(col(StylebookConnection.closed_at).is_not(None))
    return session.exec(
        select(StylebookConnection).where(*filters).order_by(StylebookConnection.id.asc())
    ).all()


@connections_router.get("/natures", response_model=NaturesResponse)
def list_connection_natures(
    project_slug: str = Query(...),
    stylebook_slug: StylebookSlugQuery = None,
    q: str | None = Query(None),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> NaturesResponse:
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    sb_id = _require_stylebook_id(session, proj, stylebook_slug)
    return _natures_response(session, stylebook_id=sb_id, q=q)


@locations_connections_router.get(
    "/canonical-locations/{location_id}/connections",
    response_model=ConnectionListResponse,
)
def list_location_connections(
    location_id: UUID,
    project_slug: str = Query(...),
    stylebook_slug: StylebookSlugQuery = None,
    include_closed: bool = Query(False),
    limit: int = Query(CONNECTIONS_DEFAULT_LIMIT, ge=1, le=CONNECTIONS_MAX_LIMIT),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> ConnectionListResponse:
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    sb_id = _require_stylebook_id(session, proj, stylebook_slug)
    loc_key = str(location_id)
    validate_canonical_exists(session, int(proj.id), "location", location_id, sb_id)
    return _list_connections_for_entity(
        session,
        int(proj.id),
        "location",
        loc_key,
        sb_id,
        include_closed=include_closed,
        limit=limit,
        offset=offset,
    )


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
    nature, description = validate_manual_connection_labels(
        nature=payload.nature,
        description=payload.description,
    )
    nature = ensure_custom_nature_for_manual_slug(
        session, stylebook_id=int(sb_id), nature=nature
    )
    conn = StylebookConnection(
        project_id=int(proj.id),
        stylebook_id=int(sb_id),
        from_entity_type="location",
        from_entity_id=loc_key,
        to_entity_type=payload.to_entity_type,
        to_entity_id=to_key,
        nature=nature,
    )
    session.add(conn)
    session.flush()
    _add_manual_evidence(
        session,
        connection_id=int(conn.id),  # type: ignore[arg-type]
        description=description,
        stylebook_id=int(sb_id),
        auth=auth,
        asserted_currentness=payload.asserted_currentness,
    )
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
    _apply_connection_update(
        session, conn, payload, stylebook_id=sb_id, auth=auth
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
    stylebook_id = int(conn.stylebook_id)
    project_ids = _stylebook_project_ids(
        session, organization_id=int(proj.organization_id)
    )
    rows = _matching_stylebook_connection_rows(
        session, project_ids=project_ids, connection=conn
    )
    for row in rows or [conn]:
        _soft_close_connection(
            session, conn=row, stylebook_id=stylebook_id, auth=auth
        )
    session.commit()
    return {"ok": True, "closed": True}


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
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    return _natures_response(session, stylebook_id=int(sb.id), q=q)


@connections_router.post(
    "/stylebooks/{stylebook_slug}/connection-natures",
    response_model=NatureEntryOut,
)
def create_stylebook_custom_nature(
    stylebook_slug: str,
    payload: CreateCustomNatureRequest = Body(...),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> NatureEntryOut:
    require_stylebook_edit_access(session, auth=auth, stylebook_slug=stylebook_slug)
    sb = require_stylebook_by_slug_in_auth_org(
        session, auth=auth, stylebook_slug=stylebook_slug
    )
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    try:
        row = upsert_custom_nature(
            session,
            stylebook_id=int(sb.id),
            slug=payload.slug,
            label=payload.label,
            equivalent_to=payload.equivalent_to,
            temporal_kind=payload.temporal_kind,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    session.commit()
    session.refresh(row)
    return NatureEntryOut(
        slug=row.slug,
        label=row.label,
        source="custom",
        equivalent_to=row.equivalent_to,
        temporal_kind=row.temporal_kind,
    )


@connections_router.delete(
    "/stylebooks/{stylebook_slug}/connection-natures/{nature_slug}",
)
def delete_stylebook_custom_nature(
    stylebook_slug: str,
    nature_slug: str,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> dict[str, bool]:
    require_stylebook_edit_access(session, auth=auth, stylebook_slug=stylebook_slug)
    sb = require_stylebook_by_slug_in_auth_org(
        session, auth=auth, stylebook_slug=stylebook_slug
    )
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    deleted = delete_custom_nature(
        session, stylebook_id=int(sb.id), slug=nature_slug
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Custom nature not found")
    session.commit()
    return {"ok": True}


@locations_connections_router.get(
    "/stylebooks/{stylebook_slug}/canonical-locations/{location_id}/connections",
    response_model=ConnectionListResponse,
)
def list_stylebook_location_connections(
    stylebook_slug: str,
    location_id: UUID,
    include_closed: bool = Query(False),
    limit: int = Query(CONNECTIONS_DEFAULT_LIMIT, ge=1, le=CONNECTIONS_MAX_LIMIT),
    offset: int = Query(0, ge=0),
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
        return ConnectionListResponse(
            connections=[], total=0, limit=limit, offset=offset
        )
    return _list_stylebook_connections_for_entity(
        session,
        project_ids=project_ids,
        entity_type="location",
        entity_id=str(location_id),
        catalog_stylebook_id=int(sb.id),
        display_project_id=project_ids[0],
        include_closed=include_closed,
        limit=limit,
        offset=offset,
    )


@locations_connections_router.get(
    "/stylebooks/{stylebook_slug}/canonical-people/{person_id}/connections",
    response_model=ConnectionListResponse,
)
def list_stylebook_person_connections(
    stylebook_slug: str,
    person_id: UUID,
    include_closed: bool = Query(False),
    limit: int = Query(CONNECTIONS_DEFAULT_LIMIT, ge=1, le=CONNECTIONS_MAX_LIMIT),
    offset: int = Query(0, ge=0),
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
        return ConnectionListResponse(
            connections=[], total=0, limit=limit, offset=offset
        )
    return _list_stylebook_connections_for_entity(
        session,
        project_ids=project_ids,
        entity_type="person",
        entity_id=str(person_id),
        catalog_stylebook_id=int(sb.id),
        display_project_id=project_ids[0],
        include_closed=include_closed,
        limit=limit,
        offset=offset,
    )


@locations_connections_router.get(
    "/stylebooks/{stylebook_slug}/canonical-organizations/{organization_id}/connections",
    response_model=ConnectionListResponse,
)
def list_stylebook_organization_connections(
    stylebook_slug: str,
    organization_id: UUID,
    include_closed: bool = Query(False),
    limit: int = Query(CONNECTIONS_DEFAULT_LIMIT, ge=1, le=CONNECTIONS_MAX_LIMIT),
    offset: int = Query(0, ge=0),
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
        return ConnectionListResponse(
            connections=[], total=0, limit=limit, offset=offset
        )
    return _list_stylebook_connections_for_entity(
        session,
        project_ids=project_ids,
        entity_type="organization",
        entity_id=str(organization_id),
        catalog_stylebook_id=int(sb.id),
        display_project_id=project_ids[0],
        include_closed=include_closed,
        limit=limit,
        offset=offset,
    )


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
    nature, description = validate_manual_connection_labels(
        nature=payload.nature,
        description=payload.description,
    )
    nature = ensure_custom_nature_for_manual_slug(
        session, stylebook_id=int(sb.id), nature=nature
    )
    existing = _find_existing_connection(
        session,
        project_ids=project_ids,
        from_entity_type="location",
        from_entity_id=loc_key,
        to_entity_type=payload.to_entity_type,
        to_entity_id=to_key,
        nature=nature,
        description=description,
    )
    if existing is None:
        existing = StylebookConnection(
            project_id=storage_project_id,
            stylebook_id=int(sb.id),
            from_entity_type="location",
            from_entity_id=loc_key,
            to_entity_type=payload.to_entity_type,
            to_entity_id=to_key,
            nature=nature,
        )
        session.add(existing)
        session.flush()
        _add_manual_evidence(
            session,
            connection_id=int(existing.id),  # type: ignore[arg-type]
            description=description,
            stylebook_id=int(sb.id),
            auth=auth,
            asserted_currentness=payload.asserted_currentness,
        )
        session.commit()
        session.refresh(existing)
        _log_stylebook_connection_event(
            session,
            stylebook_id=int(sb.id),
            auth=auth,
            event_type=EVENT_CONNECTION_CREATED,
            conn=existing,
        )
        session.commit()
    else:
        _add_manual_evidence(
            session,
            connection_id=int(existing.id),  # type: ignore[arg-type]
            description=description,
            stylebook_id=int(sb.id),
            auth=auth,
            asserted_currentness=payload.asserted_currentness,
        )
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
    for row in rows:
        _apply_connection_update(
            session, row, payload, stylebook_id=int(sb.id), auth=auth
        )
        session.add(row)
    _log_stylebook_connection_event(
        session,
        stylebook_id=int(sb.id),
        auth=auth,
        event_type=EVENT_CONNECTION_UPDATED,
        conn=conn,
        payload_json={"replica_count": len(rows)},
    )
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
    for row in rows or [conn]:
        _soft_close_connection(
            session, conn=row, stylebook_id=int(sb.id), auth=auth
        )
    session.commit()
    return {"ok": True, "closed": True}


@locations_connections_router.post(
    "/stylebooks/{stylebook_slug}/canonical-locations/{location_id}/connections/{connection_id}/reopen",
    response_model=ConnectionResponse,
)
def reopen_stylebook_location_connection(
    stylebook_slug: str,
    location_id: UUID,
    connection_id: int,
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
        session, project_ids=project_ids, connection=conn, open_only=False
    )
    for row in rows or [conn]:
        _reopen_connection(
            session, conn=row, stylebook_id=int(sb.id), auth=auth
        )
    session.commit()
    session.refresh(conn)
    return _connection_response_from_row(
        session,
        project_id=storage_project_id,
        conn=conn,
        catalog_stylebook_id=int(sb.id),
    )


def _create_stylebook_entity_connection(
    session: Session,
    *,
    storage_project_id: int,
    project_ids: list[int],
    catalog_stylebook_id: int,
    auth: dict[str, Any],
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
    nature, description = validate_manual_connection_labels(
        nature=payload.nature,
        description=payload.description,
    )
    nature = ensure_custom_nature_for_manual_slug(
        session, stylebook_id=int(catalog_stylebook_id), nature=nature
    )
    existing = _find_existing_connection(
        session,
        project_ids=project_ids,
        from_entity_type=from_entity_type,
        from_entity_id=from_entity_id,
        to_entity_type=payload.to_entity_type,
        to_entity_id=to_key,
        nature=nature,
        description=description,
    )
    if existing is None:
        existing = StylebookConnection(
            project_id=storage_project_id,
            stylebook_id=int(catalog_stylebook_id),
            from_entity_type=from_entity_type,
            from_entity_id=from_entity_id,
            to_entity_type=payload.to_entity_type,
            to_entity_id=to_key,
            nature=nature,
        )
        session.add(existing)
        session.flush()
        _add_manual_evidence(
            session,
            connection_id=int(existing.id),  # type: ignore[arg-type]
            description=description,
            stylebook_id=int(catalog_stylebook_id),
            auth=auth,
            asserted_currentness=payload.asserted_currentness,
        )
        session.commit()
        session.refresh(existing)
        _log_stylebook_connection_event(
            session,
            stylebook_id=int(catalog_stylebook_id),
            auth=auth,
            event_type=EVENT_CONNECTION_CREATED,
            conn=existing,
        )
        session.commit()
    else:
        _add_manual_evidence(
            session,
            connection_id=int(existing.id),  # type: ignore[arg-type]
            description=description,
            stylebook_id=int(catalog_stylebook_id),
            auth=auth,
            asserted_currentness=payload.asserted_currentness,
        )
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
        auth=auth,
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
    for row in rows:
        _apply_connection_update(
            session, row, payload, stylebook_id=int(sb.id), auth=auth
        )
        session.add(row)
    _log_stylebook_connection_event(
        session,
        stylebook_id=int(sb.id),
        auth=auth,
        event_type=EVENT_CONNECTION_UPDATED,
        conn=conn,
        payload_json={"replica_count": len(rows)},
    )
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
    for row in rows or [conn]:
        _soft_close_connection(
            session, conn=row, stylebook_id=int(sb.id), auth=auth
        )
    session.commit()
    return {"ok": True, "closed": True}


@locations_connections_router.post(
    "/stylebooks/{stylebook_slug}/canonical-people/{person_id}/connections/{connection_id}/reopen",
    response_model=ConnectionResponse,
)
def reopen_stylebook_person_connection(
    stylebook_slug: str,
    person_id: UUID,
    connection_id: int,
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
        session, project_ids=project_ids, connection=conn, open_only=False
    )
    for row in rows or [conn]:
        _reopen_connection(
            session, conn=row, stylebook_id=int(sb.id), auth=auth
        )
    session.commit()
    session.refresh(conn)
    return _connection_response_from_row(
        session,
        project_id=storage_project_id,
        conn=conn,
        catalog_stylebook_id=int(sb.id),
    )


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
        auth=auth,
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
    for row in rows:
        _apply_connection_update(
            session, row, payload, stylebook_id=int(sb.id), auth=auth
        )
        session.add(row)
    _log_stylebook_connection_event(
        session,
        stylebook_id=int(sb.id),
        auth=auth,
        event_type=EVENT_CONNECTION_UPDATED,
        conn=conn,
        payload_json={"replica_count": len(rows)},
    )
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
    for row in rows or [conn]:
        _soft_close_connection(
            session, conn=row, stylebook_id=int(sb.id), auth=auth
        )
    session.commit()
    return {"ok": True, "closed": True}


@locations_connections_router.post(
    "/stylebooks/{stylebook_slug}/canonical-organizations/{organization_id}/connections/{connection_id}/reopen",
    response_model=ConnectionResponse,
)
def reopen_stylebook_organization_connection(
    stylebook_slug: str,
    organization_id: UUID,
    connection_id: int,
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
        session, project_ids=project_ids, connection=conn, open_only=False
    )
    for row in rows or [conn]:
        _reopen_connection(
            session, conn=row, stylebook_id=int(sb.id), auth=auth
        )
    session.commit()
    session.refresh(conn)
    return _connection_response_from_row(
        session,
        project_id=storage_project_id,
        conn=conn,
        catalog_stylebook_id=int(sb.id),
    )
