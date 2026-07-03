"""Rewire ``stylebook_connections`` when a canonical is merged into another."""

from __future__ import annotations

from dataclasses import dataclass

from backfield_db import StylebookConnection
from sqlalchemy import and_, or_
from sqlmodel import Session, col, select


@dataclass(frozen=True)
class RewireConnectionsResult:
    rewired_count: int
    deduped_count: int
    dropped_self_count: int


def _rewired_endpoint(
    *,
    endpoint_type: str,
    endpoint_id: str,
    merged_entity_type: str,
    source_canonical_id: str,
    target_canonical_id: str,
) -> str:
    if endpoint_type == merged_entity_type and endpoint_id == source_canonical_id:
        return target_canonical_id
    return endpoint_id


def rewire_connections_for_canonical_merge(
    session: Session,
    *,
    entity_type: str,
    source_canonical_id: str,
    target_canonical_id: str,
    project_ids: list[int],
) -> RewireConnectionsResult:
    """Point connections at ``target_canonical_id`` instead of ``source_canonical_id``.

    Duplicate edges after rewrite are removed (the existing target edge is kept).
    Self-loops created by the rewrite are removed.
    """
    source_id = str(source_canonical_id)
    target_id = str(target_canonical_id)
    if source_id == target_id or not project_ids:
        return RewireConnectionsResult(rewired_count=0, deduped_count=0, dropped_self_count=0)

    connections = list(
        session.exec(
            select(StylebookConnection).where(
                col(StylebookConnection.project_id).in_(project_ids),
                or_(
                    and_(
                        StylebookConnection.from_entity_type == entity_type,
                        StylebookConnection.from_entity_id == source_id,
                    ),
                    and_(
                        StylebookConnection.to_entity_type == entity_type,
                        StylebookConnection.to_entity_id == source_id,
                    ),
                ),
            )
        ).all()
    )

    rewired = 0
    deduped = 0
    dropped_self = 0

    for conn in connections:
        new_from_id = _rewired_endpoint(
            endpoint_type=str(conn.from_entity_type),
            endpoint_id=str(conn.from_entity_id),
            merged_entity_type=entity_type,
            source_canonical_id=source_id,
            target_canonical_id=target_id,
        )
        new_to_id = _rewired_endpoint(
            endpoint_type=str(conn.to_entity_type),
            endpoint_id=str(conn.to_entity_id),
            merged_entity_type=entity_type,
            source_canonical_id=source_id,
            target_canonical_id=target_id,
        )

        if (
            str(conn.from_entity_type) == str(conn.to_entity_type)
            and new_from_id == new_to_id
        ):
            session.delete(conn)
            dropped_self += 1
            continue

        existing = session.exec(
            select(StylebookConnection).where(
                StylebookConnection.project_id == int(conn.project_id),
                StylebookConnection.from_entity_type == conn.from_entity_type,
                StylebookConnection.from_entity_id == new_from_id,
                StylebookConnection.to_entity_type == conn.to_entity_type,
                StylebookConnection.to_entity_id == new_to_id,
                StylebookConnection.nature == conn.nature,
            )
        ).first()
        if existing is not None and existing.id != conn.id:
            session.delete(conn)
            deduped += 1
            continue

        if str(conn.from_entity_id) != new_from_id:
            conn.from_entity_id = new_from_id
        if str(conn.to_entity_id) != new_to_id:
            conn.to_entity_id = new_to_id
        session.add(conn)
        rewired += 1

    if rewired or deduped or dropped_self:
        session.flush()

    return RewireConnectionsResult(
        rewired_count=rewired,
        deduped_count=deduped,
        dropped_self_count=dropped_self,
    )
