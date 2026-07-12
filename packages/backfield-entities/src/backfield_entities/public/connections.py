"""Stylebook connection reads for the public API."""

from __future__ import annotations

from backfield_db import StylebookConnection
from pydantic import BaseModel
from sqlalchemy import and_, or_
from sqlmodel import Session, select

from backfield_entities.public.canonical_display import public_canonical_label


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


def list_public_entity_connections(
    session: Session,
    *,
    project_id: int,
    stylebook_id: int,
    entity_type: str,
    entity_id: str,
) -> list[PublicConnectionOut]:
    rows = session.exec(
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
        .order_by(StylebookConnection.created_at, StylebookConnection.id)
    ).all()
    out: list[PublicConnectionOut] = []
    for conn in rows:
        if conn.id is None:
            continue
        out.append(
            PublicConnectionOut(
                id=int(conn.id),
                from_entity_type=str(conn.from_entity_type),
                from_entity_id=str(conn.from_entity_id),
                from_label=_connection_label(
                    session,
                    stylebook_id=stylebook_id,
                    entity_type=str(conn.from_entity_type),
                    entity_id=str(conn.from_entity_id),
                ),
                to_entity_type=str(conn.to_entity_type),
                to_entity_id=str(conn.to_entity_id),
                to_label=_connection_label(
                    session,
                    stylebook_id=stylebook_id,
                    entity_type=str(conn.to_entity_type),
                    entity_id=str(conn.to_entity_id),
                ),
                description=conn.description,
                nature=conn.nature,
            )
        )
    return out
