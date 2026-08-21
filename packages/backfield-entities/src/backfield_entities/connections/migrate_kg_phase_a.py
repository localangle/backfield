"""Offline Phase A connection KG migration: remap natures and merge open edges.

Prefer running this **before** schema cutover ``078_conn_kg_cutover``. After cutover,
connection ``description`` / ``evidence_json`` no longer exist; this command still remaps
natures, quarantines self-loops, and merges duplicate open edges (reattaching evidence).
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from backfield_db import (
    BackfieldProject,
    StylebookConnection,
    StylebookConnectionEvidence,
)
from sqlalchemy import func, inspect
from sqlmodel import Session, col, select

from backfield_entities.connections.natures import (
    normalize_preferred_nature_slug,
    preferred_natures_for_pair,
)

_NATURE_TYPO_REMAP: dict[str, str] = {
    "located in": "located_at",
    "located_in": "located_at",
    "works at": "works_for",
    "lives in": "lives_in",
    "born in": "born_in",
    "based in": "based_in",
    "operates in": "operates_in",
    "member of": "member_of",
    "works for": "works_for",
}

_NO_RELATIONSHIP_RE = re.compile(
    r"(?i)\b("
    r"no valid .{0,80}relationship|"
    r"no relationship can be extracted|"
    r"cannot be extracted|"
    r"no (?:organization|person|location).{0,40}relationship"
    r")\b"
)


@dataclass
class ConnectionKgMigrateReport:
    apply: bool = False
    inventory_only: bool = False
    stylebook_id: int | None = None
    connection_total: int = 0
    by_nature_pair: dict[str, int] = field(default_factory=dict)
    null_nature_count: int = 0
    with_evidence_json: int = 0
    without_evidence_json: int = 0
    stylebook_id_backfilled: int = 0
    remapped: int = 0
    remap_samples: list[dict[str, Any]] = field(default_factory=list)
    quarantined: int = 0
    quarantine_samples: list[dict[str, Any]] = field(default_factory=list)
    merge_groups: int = 0
    duplicates_deleted: int = 0
    evidence_created: int = 0
    evidence_skipped_existing: int = 0
    open_edge_groups: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class _EdgeView:
    conn: StylebookConnection
    nature: str | None
    from_type: str
    from_id: str
    to_type: str
    to_id: str
    remap_reason: str | None

    def group_key(self) -> tuple[int, str, str, str, str, str]:
        stylebook_id = (
            int(self.conn.stylebook_id) if self.conn.stylebook_id is not None else -1
        )
        return (
            stylebook_id,
            self.from_type,
            self.from_id,
            self.to_type,
            self.to_id,
            (self.nature or "").strip().lower(),
        )


def _has_legacy_columns(session: Session) -> bool:
    bind = session.get_bind()
    columns = {c["name"] for c in inspect(bind).get_columns("stylebook_connections")}
    return "description" in columns or "evidence_json" in columns


def _nature_pair_key(conn: StylebookConnection) -> str:
    nature = (conn.nature or "(null)").strip() or "(null)"
    return f"{conn.from_entity_type}->{conn.to_entity_type}|{nature}"


def _group_key(conn: StylebookConnection) -> tuple[int, str, str, str, str, str]:
    stylebook_id = int(conn.stylebook_id) if conn.stylebook_id is not None else -1
    nature = (conn.nature or "").strip().lower()
    return (
        stylebook_id,
        conn.from_entity_type.strip().lower(),
        str(conn.from_entity_id),
        conn.to_entity_type.strip().lower(),
        str(conn.to_entity_id),
        nature,
    )


def _is_self_loop(conn: StylebookConnection) -> bool:
    return (
        conn.from_entity_type.strip().lower() == conn.to_entity_type.strip().lower()
        and str(conn.from_entity_id) == str(conn.to_entity_id)
    )


def _evidence_narrative(session: Session, connection_id: int) -> str:
    rows = session.exec(
        select(StylebookConnectionEvidence).where(
            StylebookConnectionEvidence.connection_id == int(connection_id)
        )
    ).all()
    parts: list[str] = []
    for row in rows:
        for value in (row.description, row.quote, row.reason):
            text = (value or "").strip()
            if text:
                parts.append(text)
    return " ".join(parts)


def _is_no_relationship(session: Session, conn: StylebookConnection) -> bool:
    legacy = getattr(conn, "description", None)
    text = (legacy or "").strip()
    if text and _NO_RELATIONSHIP_RE.search(text):
        return True
    if conn.id is None:
        return False
    return bool(_NO_RELATIONSHIP_RE.search(_evidence_narrative(session, int(conn.id))))


def _remap_nature_and_endpoints(
    conn: StylebookConnection,
) -> tuple[str | None, str, str, str, str, str | None]:
    from_type = conn.from_entity_type.strip().lower()
    to_type = conn.to_entity_type.strip().lower()
    from_id = str(conn.from_entity_id)
    to_id = str(conn.to_entity_id)
    raw = (conn.nature or "").strip().lower() or None

    if raw == "represented_by" and from_type == "person" and to_type == "person":
        return "represents", to_type, to_id, from_type, from_id, "represented_by_swap"

    if raw == "plays_for" and from_type == "organization" and to_type == "organization":
        return "team_of", from_type, from_id, to_type, to_id, "plays_for_org_to_team_of"

    if raw is None:
        return None, from_type, from_id, to_type, to_id, None

    if raw in _NATURE_TYPO_REMAP:
        mapped = _NATURE_TYPO_REMAP[raw]
        return mapped, from_type, from_id, to_type, to_id, f"typo:{raw}->{mapped}"

    normalized = normalize_preferred_nature_slug(raw)
    if normalized != raw:
        allowed = preferred_natures_for_pair(from_type, to_type)
        if not allowed or normalized in allowed:
            return (
                normalized,
                from_type,
                from_id,
                to_type,
                to_id,
                f"alias:{raw}->{normalized}",
            )
        return raw, from_type, from_id, to_type, to_id, None

    return raw, from_type, from_id, to_type, to_id, None


def _inventory(
    session: Session,
    *,
    stylebook_id: int | None,
) -> tuple[list[StylebookConnection], ConnectionKgMigrateReport]:
    stmt = select(StylebookConnection)
    if stylebook_id is not None:
        stmt = stmt.where(StylebookConnection.stylebook_id == int(stylebook_id))
    rows = list(session.exec(stmt).all())
    report = ConnectionKgMigrateReport(
        stylebook_id=stylebook_id,
        connection_total=len(rows),
    )
    by_pair: dict[str, int] = defaultdict(int)
    legacy = _has_legacy_columns(session)
    for conn in rows:
        by_pair[_nature_pair_key(conn)] += 1
        if not (conn.nature or "").strip():
            report.null_nature_count += 1
        if legacy:
            if getattr(conn, "evidence_json", None):
                report.with_evidence_json += 1
            else:
                report.without_evidence_json += 1
    report.by_nature_pair = dict(sorted(by_pair.items(), key=lambda item: (-item[1], item[0])))
    report.open_edge_groups = len({_group_key(c) for c in rows if c.closed_at is None})
    return rows, report


def _backfill_stylebook_ids(
    session: Session,
    rows: list[StylebookConnection],
    *,
    apply: bool,
) -> int:
    missing = [c for c in rows if c.stylebook_id is None]
    if not missing:
        return 0
    project_ids = sorted({int(c.project_id) for c in missing})
    projects = {
        int(p.id): int(p.stylebook_id)  # type: ignore[arg-type]
        for p in session.exec(
            select(BackfieldProject).where(col(BackfieldProject.id).in_(project_ids))
        ).all()
        if p.id is not None and p.stylebook_id is not None
    }
    count = 0
    for conn in missing:
        sb = projects.get(int(conn.project_id))
        if sb is None:
            continue
        conn.stylebook_id = sb
        count += 1
    if apply and count:
        session.flush()
    return count


def migrate_connections_kg_phase_a(
    session: Session,
    *,
    apply: bool = False,
    inventory_only: bool = False,
    stylebook_id: int | None = None,
) -> ConnectionKgMigrateReport:
    rows, report = _inventory(session, stylebook_id=stylebook_id)
    report.apply = apply
    report.inventory_only = inventory_only
    report.stylebook_id_backfilled = _backfill_stylebook_ids(session, rows, apply=apply)

    if inventory_only:
        if apply:
            session.rollback()
        return report

    if apply and report.stylebook_id_backfilled:
        session.flush()
        rows, _ = _inventory(session, stylebook_id=stylebook_id)

    views: list[_EdgeView] = []
    for conn in rows:
        if conn.closed_at is not None:
            continue
        nature, from_type, from_id, to_type, to_id, reason = _remap_nature_and_endpoints(conn)
        views.append(
            _EdgeView(
                conn=conn,
                nature=nature,
                from_type=from_type,
                from_id=from_id,
                to_type=to_type,
                to_id=to_id,
                remap_reason=reason,
            )
        )

    for view in views:
        conn = view.conn
        changed = (
            (view.nature or None) != ((conn.nature or "").strip().lower() or None)
            or view.from_type != conn.from_entity_type.strip().lower()
            or view.to_type != conn.to_entity_type.strip().lower()
            or view.from_id != str(conn.from_entity_id)
            or view.to_id != str(conn.to_entity_id)
        )
        if not changed or view.remap_reason is None:
            continue
        report.remapped += 1
        if len(report.remap_samples) < 25:
            report.remap_samples.append(
                {
                    "id": conn.id,
                    "reason": view.remap_reason,
                    "from": f"{conn.from_entity_type}:{conn.from_entity_id}",
                    "to": f"{conn.to_entity_type}:{conn.to_entity_id}",
                    "nature_before": conn.nature,
                    "nature_after": view.nature,
                }
            )
        if apply:
            conn.nature = view.nature
            conn.from_entity_type = view.from_type
            conn.from_entity_id = view.from_id
            conn.to_entity_type = view.to_type
            conn.to_entity_id = view.to_id
            conn.updated_at = datetime.now(UTC)

    if apply and report.remapped:
        session.flush()

    keep_views: list[_EdgeView] = []
    for view in views:
        conn = view.conn
        if _is_self_loop(conn) or _is_no_relationship(session, conn):
            report.quarantined += 1
            if len(report.quarantine_samples) < 25:
                report.quarantine_samples.append(
                    {
                        "id": conn.id,
                        "reason": (
                            "self_loop" if _is_self_loop(conn) else "no_relationship_description"
                        ),
                        "description": _evidence_narrative(session, int(conn.id))[:200]
                        if conn.id is not None
                        else "",
                    }
                )
            if apply:
                session.delete(conn)
            continue
        if view.from_type == view.to_type and view.from_id == view.to_id:
            report.quarantined += 1
            if apply:
                session.delete(conn)
            continue
        keep_views.append(view)

    if apply and report.quarantined:
        session.flush()

    groups: dict[tuple[int, str, str, str, str, str], list[_EdgeView]] = defaultdict(list)
    for view in keep_views:
        groups[view.group_key()].append(view)

    report.merge_groups = len(groups)
    report.open_edge_groups = len(groups)

    for group in groups.values():
        ordered = sorted(group, key=lambda v: int(v.conn.id or 0))
        survivor = ordered[0].conn
        duplicates = [v.conn for v in ordered[1:]]
        report.duplicates_deleted += len(duplicates)
        if not apply:
            continue

        for dup in duplicates:
            dup_id = int(dup.id)  # type: ignore[arg-type]
            survivor_id = int(survivor.id)  # type: ignore[arg-type]
            for evidence in session.exec(
                select(StylebookConnectionEvidence).where(
                    StylebookConnectionEvidence.connection_id == dup_id
                )
            ).all():
                if evidence.article_id is not None:
                    exists = session.exec(
                        select(StylebookConnectionEvidence.id).where(
                            StylebookConnectionEvidence.connection_id == survivor_id,
                            StylebookConnectionEvidence.article_id == int(evidence.article_id),
                        )
                    ).first()
                    if exists is not None:
                        report.evidence_skipped_existing += 1
                        session.delete(evidence)
                        continue
                evidence.connection_id = survivor_id
                report.evidence_created += 1
            session.delete(dup)
        survivor.updated_at = datetime.now(UTC)

    if apply:
        session.commit()
        _, after = _inventory(session, stylebook_id=stylebook_id)
        report.open_edge_groups = after.open_edge_groups
        report.connection_total = after.connection_total
    else:
        session.rollback()

    return report


def connection_count(session: Session) -> int:
    return int(session.exec(select(func.count()).select_from(StylebookConnection)).one())
