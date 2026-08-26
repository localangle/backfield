"""Rewire ``stylebook_connections`` when a canonical is merged into another."""

from __future__ import annotations

from dataclasses import dataclass

from backfield_db import StylebookConnection, StylebookConnectionEvidence
from sqlalchemy import and_, or_
from sqlmodel import Session, col, select

from backfield_entities.connections.dedupe import (
    connection_nature_coalesced,
    normalize_connection_nature,
)


@dataclass(frozen=True)
class RewireConnectionsResult:
    rewired_count: int
    deduped_count: int
    dropped_self_count: int


def _move_evidence_to_survivor(
    session: Session,
    *,
    duplicate_id: int,
    survivor_id: int,
) -> None:
    """Reattach the duplicate's evidence before deletion so the FK cascade cannot destroy it.

    Evidence citing an article the survivor already cites is deleted with the duplicate.
    """
    for evidence in session.exec(
        select(StylebookConnectionEvidence).where(
            StylebookConnectionEvidence.connection_id == duplicate_id
        )
    ).all():
        if evidence.article_id is not None:
            already_cited = session.exec(
                select(StylebookConnectionEvidence.id).where(
                    StylebookConnectionEvidence.connection_id == survivor_id,
                    StylebookConnectionEvidence.article_id == int(evidence.article_id),
                )
            ).first()
            if already_cited is not None:
                session.delete(evidence)
                continue
        evidence.connection_id = survivor_id
    session.flush()


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

        nature_key = normalize_connection_nature(conn.nature) or ""
        existing_stmt = select(StylebookConnection).where(
            StylebookConnection.from_entity_type == conn.from_entity_type,
            StylebookConnection.from_entity_id == new_from_id,
            StylebookConnection.to_entity_type == conn.to_entity_type,
            StylebookConnection.to_entity_id == new_to_id,
            connection_nature_coalesced() == nature_key,
            col(StylebookConnection.closed_at).is_(None),
        )
        if conn.stylebook_id is not None:
            existing_stmt = existing_stmt.where(
                StylebookConnection.stylebook_id == int(conn.stylebook_id)
            )
        else:
            existing_stmt = existing_stmt.where(
                StylebookConnection.project_id == int(conn.project_id)
            )
        existing = session.exec(existing_stmt).first()
        if existing is not None and existing.id != conn.id:
            if conn.id is not None and existing.id is not None:
                _move_evidence_to_survivor(
                    session,
                    duplicate_id=int(conn.id),
                    survivor_id=int(existing.id),
                )
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
