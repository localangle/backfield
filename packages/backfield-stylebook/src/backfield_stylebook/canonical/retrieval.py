"""Dialect-specific recall for canonical candidates (Postgres pg_trgm vs SQLite fallback)."""

from __future__ import annotations

from collections import defaultdict

from backfield_db import StylebookLocationAlias, StylebookLocationCanonical
from sqlalchemy import or_, text
from sqlmodel import Session, col, select

from backfield_stylebook.canonical_link_matrix import types_are_comparable

# Low threshold: precision is handled in :mod:`canonical_match_score`.
_PG_SIMILARITY_THRESHOLD: float = 0.12
_DEFAULT_TOP_K: int = 24


def _distinct_query_strings(*candidates: str | None) -> list[str]:
    """Non-empty stripped lowercase query strings, first-seen order preserved."""
    seen: set[str] = set()
    out: list[str] = []
    for raw in candidates:
        if raw is None:
            continue
        v = raw.strip().lower()
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def _sqlite_token_conditions(normalized_query: str) -> list:
    norm = normalized_query.strip().lower()
    parts = [p for p in norm.replace(",", " ").split() if len(p) >= 3]
    # Prefer longer tokens for containment without exploding OR count.
    parts = sorted(set(parts), key=len, reverse=True)[:6]
    conds = [col(StylebookLocationAlias.normalized_alias) == norm]
    for p in parts:
        conds.append(col(StylebookLocationAlias.normalized_alias).contains(p))
    return conds


def _postgres_recall_chunk(
    session: Session,
    *,
    stylebook_id: int,
    query_lower: str,
    limit: int,
) -> list[tuple[str, float]]:
    stmt = text(
        """
        SELECT slc.id,
               MAX(similarity(sla.normalized_alias, :q)) AS best_sim
        FROM stylebook_location_alias AS sla
        INNER JOIN stylebook_location_canonical AS slc
          ON sla.location_canonical_id = slc.id
        WHERE slc.stylebook_id = :sid
          AND sla.suppressed IS FALSE
        GROUP BY slc.id
        HAVING MAX(similarity(sla.normalized_alias, :q)) > :th
        ORDER BY best_sim DESC
        LIMIT :lim
        """
    )
    rows = session.execute(
        stmt,
        {
            "q": query_lower,
            "sid": stylebook_id,
            "th": _PG_SIMILARITY_THRESHOLD,
            "lim": limit,
        },
    ).all()
    out: list[tuple[str, float]] = []
    for row in rows:
        cid = str(row[0])
        sim = float(row[1]) if row[1] is not None else 0.0
        out.append((cid, sim))
    return out


def _sqlite_recall_chunk(
    session: Session,
    *,
    stylebook_id: int,
    query_lower: str,
    limit: int,
) -> list[str]:
    conds = _sqlite_token_conditions(query_lower)
    stmt = (
        select(StylebookLocationCanonical.id)
        .join(
            StylebookLocationAlias,
            StylebookLocationAlias.location_canonical_id == StylebookLocationCanonical.id,
        )
        .where(
            StylebookLocationCanonical.stylebook_id == stylebook_id,
            StylebookLocationAlias.suppressed == False,  # noqa: E712
            or_(*conds),
        )
        .distinct()
        .limit(limit)
    )
    ids = session.exec(stmt).all()
    return [str(i) for i in ids]


def retrieve_candidate_canonical_ids(
    session: Session,
    *,
    stylebook_id: int,
    query_text: str,
    normalized_query: str,
    formatted_address: str | None = None,
    limit: int = _DEFAULT_TOP_K,
    substrate_location_type: str | None = None,
) -> list[tuple[str, float | None]]:
    """Return ``(canonical_id, optional_db_string_hint)`` ordered best-first.

    Merges recall across ``normalized_query``, ``query_text``, and optional
    ``formatted_address`` so geocoder-only elaborations (``West Side``, ``USA``)
    still surface the same canonical as the shorter display name.

    On Postgres, the hint is the max ``similarity`` seen for that canonical across
    all query variants. On SQLite, hints are ``None`` (scorer uses :mod:`difflib`).

    When ``substrate_location_type`` is set, canonicals whose ``location_type`` fails
    :func:`types_are_comparable` with that substrate type are dropped (order preserved).
    """
    variants = _distinct_query_strings(normalized_query, query_text, formatted_address)
    if not variants:
        return []

    bind = session.get_bind()
    per = max(8, min(limit, 32) // len(variants))

    if bind.dialect.name == "postgresql":
        best_sim: dict[str, float] = defaultdict(float)
        for v in variants:
            for cid, sim in _postgres_recall_chunk(
                session, stylebook_id=stylebook_id, query_lower=v, limit=per
            ):
                if sim > best_sim[cid]:
                    best_sim[cid] = sim
        ranked = sorted(best_sim.items(), key=lambda it: -it[1])[:limit]
        raw = [(cid, float(s)) for cid, s in ranked]
        return _filter_recall_by_substrate_type(session, raw, substrate_location_type, limit)

    seen: set[str] = set()
    ordered: list[str] = []
    for v in variants:
        chunk = _sqlite_recall_chunk(
            session, stylebook_id=stylebook_id, query_lower=v, limit=per
        )
        for cid in chunk:
            if cid not in seen:
                seen.add(cid)
                ordered.append(cid)
            if len(ordered) >= limit:
                break
        if len(ordered) >= limit:
            break
    raw = [(cid, None) for cid in ordered]
    return _filter_recall_by_substrate_type(session, raw, substrate_location_type, limit)


def _filter_recall_by_substrate_type(
    session: Session,
    raw: list[tuple[str, float | None]],
    substrate_location_type: str | None,
    limit: int,
) -> list[tuple[str, float | None]]:
    if not raw or not (substrate_location_type or "").strip():
        return raw[:limit]
    ids = [cid for cid, _ in raw]
    rows = session.exec(
        select(StylebookLocationCanonical).where(col(StylebookLocationCanonical.id).in_(ids))
    ).all()
    lt_by_id: dict[str, str | None] = {}
    for c in rows:
        if c.id is not None:
            lt_by_id[str(c.id)] = c.location_type
    out: list[tuple[str, float | None]] = []
    for cid, hint in raw:
        lt = lt_by_id.get(str(cid))
        if types_are_comparable(substrate_location_type, lt):
            out.append((cid, hint))
        if len(out) >= limit:
            break
    return out


def load_canonical_match_features(
    session: Session,
    *,
    canonical_ids: list[str],
) -> dict[str, tuple[StylebookLocationCanonical, tuple[str, ...]]]:
    """Map canonical id → (row, normalized_aliases including label as alias-like string)."""
    if not canonical_ids:
        return {}
    canon_rows = session.exec(
        select(StylebookLocationCanonical).where(col(StylebookLocationCanonical.id).in_(canonical_ids))
    ).all()
    by_id: dict[str, StylebookLocationCanonical] = {}
    for c in canon_rows:
        if c.id is not None:
            by_id[str(c.id)] = c
    alias_rows = session.exec(
        select(StylebookLocationAlias).where(
            col(StylebookLocationAlias.location_canonical_id).in_(canonical_ids),
            StylebookLocationAlias.suppressed == False,  # noqa: E712
        )
    ).all()
    aliases_by_canon: dict[str, list[str]] = {cid: [] for cid in canonical_ids}
    for a in alias_rows:
        if a.location_canonical_id is None:
            continue
        cid = str(a.location_canonical_id)
        if cid in aliases_by_canon:
            aliases_by_canon[cid].append(str(a.normalized_alias))
    out: dict[str, tuple[StylebookLocationCanonical, tuple[str, ...]]] = {}
    for cid in canonical_ids:
        c = by_id.get(cid)
        if c is None:
            continue
        merged = tuple(sorted(set(aliases_by_canon.get(cid, []))))
        out[cid] = (c, merged)
    return out
