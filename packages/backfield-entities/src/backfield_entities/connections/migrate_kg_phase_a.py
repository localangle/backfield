"""Offline Phase A connection KG migration: remap natures, merge edges, backfill evidence.

See ``docs/architecture/knowledge-graph.md`` (Existing-data migration plan).
Schema cutover (unique index / drop ``evidence_json``) is a separate Alembic step.
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
from sqlalchemy import func
from sqlmodel import Session, col, select

from backfield_entities.connections.natures import (
    normalize_preferred_nature_slug,
    preferred_natures_for_pair,
)

# Explicit typo / freeform remaps (after lower/strip). Prefer preferred-catalog aliases first.
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

_EVIDENCE_JSON_KEYS = frozenset(
    {
        "quote",
        "confidence",
        "source",
        "article_id",
        "run_id",
        "processed_item_id",
        "prompt_version",
        "match_basis",
        "reason",
        "from_entity_type",
        "from_entity_id",
        "from_display_name",
        "to_entity_type",
        "to_entity_id",
        "to_display_name",
        "adjudication_model",
        "adjudication_ai_model_config_id",
    }
)


@dataclass
class ConnectionKgMigrateReport:
    """Summary of inventory + migrate actions (dry-run or applied)."""

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


def _evidence_richness(conn: StylebookConnection) -> tuple[int, int, float, int]:
    """Higher is better: has evidence_json, non-empty description, earlier created_at."""
    has_ev = 1 if conn.evidence_json else 0
    has_desc = 1 if (conn.description or "").strip() else 0
    created = conn.created_at.timestamp() if conn.created_at is not None else 0.0
    return (has_ev, has_desc, -created, -(conn.id or 0))


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


def _is_no_relationship_description(description: str | None) -> bool:
    text = (description or "").strip()
    if not text:
        return False
    return _NO_RELATIONSHIP_RE.search(text) is not None


def _is_self_loop(conn: StylebookConnection) -> bool:
    return (
        conn.from_entity_type.strip().lower() == conn.to_entity_type.strip().lower()
        and str(conn.from_entity_id) == str(conn.to_entity_id)
    )


def _remap_nature_and_endpoints(
    conn: StylebookConnection,
) -> tuple[str | None, str, str, str, str, str | None]:
    """Return (nature, from_type, from_id, to_type, to_id, remap_reason)."""
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
        if not allowed or normalized in allowed or normalized == raw:
            return (
                normalized,
                from_type,
                from_id,
                to_type,
                to_id,
                f"alias:{raw}->{normalized}",
            )
        # Alias pointed at a slug not valid for this pair — keep original.
        return raw, from_type, from_id, to_type, to_id, None

    return raw, from_type, from_id, to_type, to_id, None


def _payload_remainder(evidence_json: dict[str, Any] | None) -> dict[str, Any] | None:
    if not evidence_json:
        return None
    leftover = {k: v for k, v in evidence_json.items() if k not in _EVIDENCE_JSON_KEYS}
    return leftover or None


def _evidence_from_connection(
    conn: StylebookConnection,
    *,
    is_duplicate: bool,
) -> StylebookConnectionEvidence:
    evidence_json = conn.evidence_json if isinstance(conn.evidence_json, dict) else None
    description = (conn.description or "").strip() or None
    if evidence_json:
        quote = str(evidence_json.get("quote") or "").strip() or None
        reason = str(evidence_json.get("reason") or "").strip() or description
        conf_raw = evidence_json.get("confidence")
        try:
            confidence = float(conf_raw) if conf_raw is not None else None
        except (TypeError, ValueError):
            confidence = None
        article_raw = evidence_json.get("article_id")
        try:
            article_id = int(article_raw) if article_raw is not None else None
        except (TypeError, ValueError):
            article_id = None
        run_id = evidence_json.get("run_id")
        processed_raw = evidence_json.get("processed_item_id")
        try:
            processed_item_id = int(processed_raw) if processed_raw is not None else None
        except (TypeError, ValueError):
            processed_item_id = None
        return StylebookConnectionEvidence(
            connection_id=int(conn.id),  # type: ignore[arg-type]
            article_id=article_id,
            description=description,
            quote=quote,
            reason=reason,
            confidence=confidence,
            source=str(evidence_json.get("source") or "dboutput_auto_connections"),
            prompt_version=(
                str(evidence_json["prompt_version"])
                if evidence_json.get("prompt_version") is not None
                else None
            ),
            run_id=str(run_id) if run_id is not None else None,
            processed_item_id=processed_item_id,
            match_basis=(
                str(evidence_json["match_basis"])
                if evidence_json.get("match_basis") is not None
                else None
            ),
            observed_at=conn.created_at,
            payload_json=_payload_remainder(evidence_json),
        )

    source = "legacy_duplicate" if is_duplicate else "legacy_manual"
    return StylebookConnectionEvidence(
        connection_id=int(conn.id),  # type: ignore[arg-type]
        article_id=None,
        description=description,
        quote=description,
        reason=description,
        confidence=None,
        source=source,
        observed_at=conn.created_at,
        payload_json=None,
    )


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
    for conn in rows:
        by_pair[_nature_pair_key(conn)] += 1
        if not (conn.nature or "").strip():
            report.null_nature_count += 1
        if conn.evidence_json:
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
    """Run inventory, remaps, quarantine, and merge→evidence for Phase A.

    Default is dry-run (``apply=False``): computes the report without committing.
    When ``apply=True``, commits at the end.
    """
    rows, report = _inventory(session, stylebook_id=stylebook_id)
    report.apply = apply
    report.inventory_only = inventory_only
    report.stylebook_id_backfilled = _backfill_stylebook_ids(session, rows, apply=apply)

    if inventory_only:
        if apply:
            session.rollback()
        return report

    # Re-fetch after potential stylebook backfill so group keys are correct.
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

    # --- Step 1: remaps ---
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

    # --- Step 3 (before merge): quarantine ---
    keep_views: list[_EdgeView] = []
    for view in views:
        conn = view.conn
        if _is_self_loop(conn) or _is_no_relationship_description(conn.description):
            report.quarantined += 1
            if len(report.quarantine_samples) < 25:
                report.quarantine_samples.append(
                    {
                        "id": conn.id,
                        "reason": (
                            "self_loop" if _is_self_loop(conn) else "no_relationship_description"
                        ),
                        "description": (conn.description or "")[:200],
                    }
                )
            if apply:
                session.delete(conn)
            continue
        # Also quarantine remapped self-loops (after represented_by swap rare).
        if view.from_type == view.to_type and view.from_id == view.to_id:
            report.quarantined += 1
            if apply:
                session.delete(conn)
            continue
        keep_views.append(view)

    if apply and report.quarantined:
        session.flush()

    # --- Step 2: merge + evidence ---
    groups: dict[tuple[int, str, str, str, str, str], list[_EdgeView]] = defaultdict(list)
    for view in keep_views:
        groups[view.group_key()].append(view)

    report.merge_groups = len(groups)
    report.open_edge_groups = len(groups)

    for group in groups.values():
        ordered = sorted(group, key=lambda v: _evidence_richness(v.conn), reverse=True)
        survivor_view = ordered[0]
        survivor = survivor_view.conn
        duplicates = [v.conn for v in ordered[1:]]
        report.duplicates_deleted += len(duplicates)

        if apply:
            existing_article_ids: set[int] = set()
            existing_null_quotes: set[str] = set()
            prior = session.exec(
                select(StylebookConnectionEvidence).where(
                    StylebookConnectionEvidence.connection_id == int(survivor.id)  # type: ignore[arg-type]
                )
            ).all()
            for ev in prior:
                if ev.article_id is not None:
                    existing_article_ids.add(int(ev.article_id))
                quote_key = (ev.quote or ev.description or "").strip().lower()
                if quote_key and ev.article_id is None:
                    existing_null_quotes.add(quote_key)

            for idx, member_view in enumerate(ordered):
                member = member_view.conn
                evidence = _evidence_from_connection(member, is_duplicate=idx > 0)
                evidence.connection_id = int(survivor.id)  # type: ignore[arg-type]
                if evidence.article_id is not None:
                    if int(evidence.article_id) in existing_article_ids:
                        report.evidence_skipped_existing += 1
                        continue
                    existing_article_ids.add(int(evidence.article_id))
                else:
                    quote_key = (evidence.quote or evidence.description or "").strip().lower()
                    if quote_key and quote_key in existing_null_quotes:
                        report.evidence_skipped_existing += 1
                        continue
                    if quote_key:
                        existing_null_quotes.add(quote_key)
                session.add(evidence)
                report.evidence_created += 1

            for dup in duplicates:
                session.delete(dup)
            survivor.description = None
            survivor.updated_at = datetime.now(UTC)
        else:
            article_seen: set[int] = set()
            for member_view in ordered:
                member = member_view.conn
                evidence_json = (
                    member.evidence_json if isinstance(member.evidence_json, dict) else None
                )
                article_id = None
                if evidence_json and evidence_json.get("article_id") is not None:
                    try:
                        article_id = int(evidence_json["article_id"])
                    except (TypeError, ValueError):
                        article_id = None
                if article_id is not None and article_id in article_seen:
                    report.evidence_skipped_existing += 1
                    continue
                if article_id is not None:
                    article_seen.add(article_id)
                report.evidence_created += 1

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
