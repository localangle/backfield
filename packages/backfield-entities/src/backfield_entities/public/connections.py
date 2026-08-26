"""Stylebook connection reads for the public API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from backfield_db import StylebookConnection, StylebookConnectionEvidence
from pydantic import BaseModel
from sqlalchemy import and_, or_
from sqlmodel import Session, col, select

from backfield_entities.connections.custom_natures import merged_nature_catalog
from backfield_entities.connections.display import (
    derived_connection_description_from_rows,
    list_connection_evidence,
)
from backfield_entities.connections.natures import temporal_kind_for_nature
from backfield_entities.public.canonical_display import public_canonical_label
from backfield_entities.public.nature_filters import normalize_natures

PublicConnectionEntityType = Literal["location", "person", "organization"]


class PublicConnectionEvidenceOut(BaseModel):
    """Public connection citation without internal pipeline provenance."""

    article_id: int | None = None
    description: str | None = None
    quote: str | None = None
    reason: str | None = None
    confidence: float | None = None
    asserted_currentness: str = "unspecified"
    observed_at: datetime | None = None


def public_evidence_out_list_from_rows(
    rows: list[StylebookConnectionEvidence],
) -> list[PublicConnectionEvidenceOut]:
    """Shape pre-fetched evidence rows for the public API (already sorted)."""
    return [
        PublicConnectionEvidenceOut(
            article_id=int(row.article_id) if row.article_id is not None else None,
            description=row.description,
            quote=row.quote,
            reason=row.reason,
            confidence=float(row.confidence) if row.confidence is not None else None,
            asserted_currentness=row.asserted_currentness,
            observed_at=row.observed_at,
        )
        for row in rows
    ]


class PublicConnectionOut(BaseModel):
    id: int
    from_entity_type: str
    from_entity_id: str
    from_label: str
    to_entity_type: str
    to_entity_id: str
    to_label: str
    description: str | None = None
    nature: str | None = None
    temporal_kind: Literal["static", "dynamic"] | None = None
    currentness: Literal["current", "former", "unknown"] | None = None
    currentness_as_of: datetime | None = None
    closed_at: datetime | None = None
    evidence: list[PublicConnectionEvidenceOut] = []


def _connection_label(
    session: Session,
    *,
    stylebook_id: int,
    entity_type: str,
    entity_id: str,
) -> str:
    label = public_canonical_label(
        session,
        stylebook_id=stylebook_id,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    if label:
        return label
    return f"{entity_type} {entity_id}"


def _connection_temporal_kind(
    session: Session,
    *,
    stylebook_id: int,
    connection: StylebookConnection,
) -> Literal["static", "dynamic"]:
    nature = (connection.nature or "").strip()
    if nature:
        for entry in merged_nature_catalog(
            session,
            stylebook_id=stylebook_id,
            q=nature,
        ):
            if entry.slug == nature and entry.temporal_kind == "static":
                return "static"
        return temporal_kind_for_nature(
            nature,
            connection.from_entity_type,
            connection.to_entity_type,
        )
    return "dynamic"


def list_public_entity_connections(
    session: Session,
    *,
    project_id: int,
    stylebook_id: int,
    entity_type: PublicConnectionEntityType,
    entity_id: str,
    to_entity_type: PublicConnectionEntityType | None = None,
    natures: tuple[str, ...] = (),
    include_closed: bool = False,
    limit: int = 25,
    offset: int = 0,
) -> tuple[list[PublicConnectionOut], int]:
    target_type = (to_entity_type or "").strip()
    nature_values = normalize_natures(natures)
    directional_filters = [
        and_(
            StylebookConnection.from_entity_type == entity_type,
            StylebookConnection.from_entity_id == entity_id,
            *(
                [StylebookConnection.to_entity_type == target_type]
                if target_type
                else []
            ),
        ),
        and_(
            StylebookConnection.to_entity_type == entity_type,
            StylebookConnection.to_entity_id == entity_id,
            *(
                [StylebookConnection.from_entity_type == target_type]
                if target_type
                else []
            ),
        ),
    ]
    filters = [
        or_(
            StylebookConnection.stylebook_id == int(stylebook_id),
            and_(
                col(StylebookConnection.stylebook_id).is_(None),
                StylebookConnection.project_id == int(project_id),
            ),
        ),
        or_(*directional_filters),
    ]
    if not include_closed:
        filters.append(col(StylebookConnection.closed_at).is_(None))
    if nature_values:
        filters.append(col(StylebookConnection.nature).in_(nature_values))
    rows = session.exec(select(StylebookConnection).where(*filters)).all()

    # Sorting needs only the label of the far side of each edge, so compute
    # those first, then slice to the requested page before hydrating evidence.
    sortable: list[tuple[tuple[str, str, int], StylebookConnection, str, bool]] = []
    for conn in rows:
        if conn.id is None:
            continue
        from_side_matches = (
            str(conn.from_entity_type) == entity_type
            and str(conn.from_entity_id) == entity_id
        )
        if from_side_matches:
            target_type = str(conn.to_entity_type)
            target_id = str(conn.to_entity_id)
        else:
            target_type = str(conn.from_entity_type)
            target_id = str(conn.from_entity_id)
        target_label = _connection_label(
            session,
            stylebook_id=stylebook_id,
            entity_type=target_type,
            entity_id=target_id,
        )
        sort_key = (target_label.casefold(), target_type, int(conn.id))
        sortable.append((sort_key, conn, target_label, from_side_matches))

    sortable.sort(key=lambda item: item[0])
    total = len(sortable)
    page = sortable[offset : offset + limit]

    entity_label: str | None = None
    if page:
        entity_label = _connection_label(
            session,
            stylebook_id=stylebook_id,
            entity_type=entity_type,
            entity_id=entity_id,
        )

    out: list[PublicConnectionOut] = []
    for _sort_key, conn, target_label, from_side_matches in page:
        temporal_kind = _connection_temporal_kind(
            session,
            stylebook_id=stylebook_id,
            connection=conn,
        )
        evidence_rows = list_connection_evidence(session, connection_id=int(conn.id))
        from_label = entity_label if from_side_matches else target_label
        to_label = target_label if from_side_matches else entity_label
        out.append(
            PublicConnectionOut(
                id=int(conn.id),
                from_entity_type=str(conn.from_entity_type),
                from_entity_id=str(conn.from_entity_id),
                from_label=str(from_label),
                to_entity_type=str(conn.to_entity_type),
                to_entity_id=str(conn.to_entity_id),
                to_label=str(to_label),
                description=derived_connection_description_from_rows(evidence_rows),
                nature=conn.nature,
                temporal_kind=temporal_kind,
                currentness=conn.currentness if temporal_kind == "dynamic" else None,
                currentness_as_of=(
                    conn.currentness_as_of if temporal_kind == "dynamic" else None
                ),
                closed_at=conn.closed_at,
                evidence=public_evidence_out_list_from_rows(evidence_rows),
            )
        )
    return out, total
