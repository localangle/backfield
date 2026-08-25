"""Connection lifecycle helpers for canonical delete and orphan repair."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime

from backfield_db import (
    StylebookConnection,
    StylebookConnectionEvidence,
    StylebookLocationCanonical,
    StylebookOrganizationCanonical,
    StylebookPersonCanonical,
)
from sqlalchemy import and_, or_
from sqlmodel import Session, col, select

from backfield_entities.connections.rewire import rewire_connections_for_canonical_merge


@dataclass(frozen=True)
class CloseConnectionsResult:
    closed_count: int


@dataclass(frozen=True)
class RepairOrphanConnectionsResult:
    closed_count: int
    rewired_count: int
    inspected_count: int


def close_open_connections_for_canonical(
    session: Session,
    *,
    entity_type: str,
    canonical_id: str,
    closed_at: datetime | None = None,
) -> CloseConnectionsResult:
    """Soft-close every open connection that references a deleted canonical."""
    entity_id = str(canonical_id)
    now = closed_at or datetime.now(UTC)
    connections = list(
        session.exec(
            select(StylebookConnection).where(
                col(StylebookConnection.closed_at).is_(None),
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
        ).all()
    )
    for conn in connections:
        conn.closed_at = now
        conn.updated_at = now
        session.add(conn)
    if connections:
        session.flush()
    return CloseConnectionsResult(closed_count=len(connections))


def _canonical_exists(
    session: Session,
    *,
    entity_type: str,
    entity_id: str,
) -> bool:
    if entity_type == "person":
        return session.get(StylebookPersonCanonical, entity_id) is not None
    if entity_type == "organization":
        return session.get(StylebookOrganizationCanonical, entity_id) is not None
    if entity_type == "location":
        return session.get(StylebookLocationCanonical, entity_id) is not None
    return False


def _evidence_display_names_for_missing_endpoint(
    session: Session,
    *,
    connection_id: int,
    endpoint: str,
) -> list[str]:
    rows = session.exec(
        select(StylebookConnectionEvidence)
        .where(StylebookConnectionEvidence.connection_id == int(connection_id))
        .order_by(col(StylebookConnectionEvidence.created_at).desc())
    ).all()
    key = "from_display_name" if endpoint == "from" else "to_display_name"
    names: list[str] = []
    seen: set[str] = set()
    for row in rows:
        payload = row.payload_json if isinstance(row.payload_json, dict) else {}
        name = str(payload.get(key) or "").strip()
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    return names


def _unique_canonical_id_by_label(
    session: Session,
    *,
    entity_type: str,
    stylebook_id: int | None,
    label: str,
) -> str | None:
    normalized = label.strip()
    if not normalized or stylebook_id is None:
        return None
    if entity_type == "person":
        rows = session.exec(
            select(StylebookPersonCanonical).where(
                StylebookPersonCanonical.stylebook_id == int(stylebook_id),
                StylebookPersonCanonical.label == normalized,
            )
        ).all()
    elif entity_type == "organization":
        rows = session.exec(
            select(StylebookOrganizationCanonical).where(
                StylebookOrganizationCanonical.stylebook_id == int(stylebook_id),
                StylebookOrganizationCanonical.label == normalized,
            )
        ).all()
    elif entity_type == "location":
        rows = session.exec(
            select(StylebookLocationCanonical).where(
                StylebookLocationCanonical.stylebook_id == int(stylebook_id),
                StylebookLocationCanonical.label == normalized,
            )
        ).all()
    else:
        return None
    if len(rows) != 1 or rows[0].id is None:
        return None
    return str(rows[0].id)


def _resolve_survivor_for_missing(
    session: Session,
    *,
    entity_type: str,
    missing_id: str,
    connections: list[StylebookConnection],
) -> str | None:
    """Return a unique survivor id when evidence labels agree on one living canonical."""
    candidates: set[str] = set()
    for conn in connections:
        if conn.id is None:
            continue
        if (
            str(conn.from_entity_type) == entity_type
            and str(conn.from_entity_id) == missing_id
        ):
            endpoint = "from"
        elif (
            str(conn.to_entity_type) == entity_type
            and str(conn.to_entity_id) == missing_id
        ):
            endpoint = "to"
        else:
            continue
        for label in _evidence_display_names_for_missing_endpoint(
            session,
            connection_id=int(conn.id),
            endpoint=endpoint,
        ):
            survivor = _unique_canonical_id_by_label(
                session,
                entity_type=entity_type,
                stylebook_id=conn.stylebook_id,
                label=label,
            )
            if survivor and survivor != missing_id:
                candidates.add(survivor)
    if len(candidates) == 1:
        return next(iter(candidates))
    return None


def repair_orphan_open_connections(
    session: Session,
    *,
    stylebook_id: int | None = None,
    dry_run: bool = True,
) -> RepairOrphanConnectionsResult:
    """Close or rewire open connections whose endpoints no longer exist.

    When evidence stores a display name that uniquely matches one surviving
    canonical of the same type in the stylebook, rewire that missing id to the
    survivor. Otherwise soft-close remaining orphan edges.
    """
    stmt = select(StylebookConnection).where(col(StylebookConnection.closed_at).is_(None))
    if stylebook_id is not None:
        stmt = stmt.where(StylebookConnection.stylebook_id == int(stylebook_id))
    connections = list(session.exec(stmt).all())

    missing_to_conns: dict[tuple[str, str], list[StylebookConnection]] = defaultdict(list)
    for conn in connections:
        for entity_type, entity_id in (
            (str(conn.from_entity_type), str(conn.from_entity_id)),
            (str(conn.to_entity_type), str(conn.to_entity_id)),
        ):
            if not _canonical_exists(session, entity_type=entity_type, entity_id=entity_id):
                missing_to_conns[(entity_type, entity_id)].append(conn)

    inspected = sum(len(rows) for rows in missing_to_conns.values())
    closed = 0
    rewired = 0
    now = datetime.now(UTC)
    # Missing endpoints that will be (or were) remapped to a survivor.
    resolved_missing: set[tuple[str, str]] = set()

    for (entity_type, missing_id), related in missing_to_conns.items():
        survivor_id = _resolve_survivor_for_missing(
            session,
            entity_type=entity_type,
            missing_id=missing_id,
            connections=related,
        )
        project_ids = sorted(
            {
                int(conn.project_id)
                for conn in related
                if conn.project_id is not None
            }
        )
        if survivor_id is not None and project_ids:
            resolved_missing.add((entity_type, missing_id))
            if dry_run:
                rewired += len(related)
                continue
            result = rewire_connections_for_canonical_merge(
                session,
                entity_type=entity_type,
                source_canonical_id=missing_id,
                target_canonical_id=survivor_id,
                project_ids=project_ids,
            )
            rewired += (
                result.rewired_count + result.deduped_count + result.dropped_self_count
            )

    # Soft-close any still-open orphans (including edges that still miss an
    # endpoint after a partial rewire of the other end).
    remaining_stmt = select(StylebookConnection).where(
        col(StylebookConnection.closed_at).is_(None)
    )
    if stylebook_id is not None:
        remaining_stmt = remaining_stmt.where(
            StylebookConnection.stylebook_id == int(stylebook_id)
        )
    remaining = list(session.exec(remaining_stmt).all())
    for conn in remaining:
        from_key = (str(conn.from_entity_type), str(conn.from_entity_id))
        to_key = (str(conn.to_entity_type), str(conn.to_entity_id))
        from_missing = from_key not in resolved_missing and not _canonical_exists(
            session,
            entity_type=from_key[0],
            entity_id=from_key[1],
        )
        to_missing = to_key not in resolved_missing and not _canonical_exists(
            session,
            entity_type=to_key[0],
            entity_id=to_key[1],
        )
        if not from_missing and not to_missing:
            continue
        if dry_run:
            closed += 1
            continue
        conn.closed_at = now
        conn.updated_at = now
        session.add(conn)
        closed += 1

    if not dry_run and (closed or rewired):
        session.flush()

    return RepairOrphanConnectionsResult(
        closed_count=closed,
        rewired_count=rewired,
        inspected_count=inspected,
    )
