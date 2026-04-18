"""Dialect-specific recall for canonical candidates (Postgres pg_trgm vs SQLite fallback)."""

from __future__ import annotations

from backfield_db import StylebookLocationAlias, StylebookLocationCanonical
from sqlalchemy import or_, text
from sqlmodel import Session, col, select

# Low threshold: precision is handled in :mod:`canonical_match_score`.
_PG_SIMILARITY_THRESHOLD: float = 0.12
_DEFAULT_TOP_K: int = 24


def _sqlite_token_conditions(normalized_query: str) -> list:
    norm = normalized_query.strip().lower()
    parts = [p for p in norm.replace(",", " ").split() if len(p) >= 3]
    # Prefer longer tokens for containment without exploding OR count.
    parts = sorted(set(parts), key=len, reverse=True)[:6]
    conds = [col(StylebookLocationAlias.normalized_alias) == norm]
    for p in parts:
        conds.append(col(StylebookLocationAlias.normalized_alias).contains(p))
    return conds


def retrieve_candidate_canonical_ids(
    session: Session,
    *,
    stylebook_id: int,
    query_text: str,
    normalized_query: str,
    limit: int = _DEFAULT_TOP_K,
) -> list[tuple[int, float | None]]:
    """Return ``(canonical_id, optional_db_string_hint)`` ordered best-first.

    On Postgres, the hint is ``MAX(similarity(alias, normalized_query))`` per canonical.
    On SQLite, hints are ``None`` (scorer uses :mod:`difflib`).
    """
    _ = query_text  # reserved for future tokenization / label recall
    nq = normalized_query.strip().lower()
    if not nq:
        return []

    bind = session.get_bind()
    if bind.dialect.name == "postgresql":
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
                "q": nq,
                "sid": stylebook_id,
                "th": _PG_SIMILARITY_THRESHOLD,
                "lim": limit,
            },
        ).all()
        out: list[tuple[int, float | None]] = []
        for row in rows:
            cid = int(row[0])
            sim = float(row[1]) if row[1] is not None else None
            out.append((cid, sim))
        return out

    conds = _sqlite_token_conditions(nq)
    stmt = (
        select(StylebookLocationCanonical.id)
        .join(
            StylebookLocationAlias,
            StylebookLocationAlias.location_canonical_id == StylebookLocationCanonical.id,
        )
        .where(
            StylebookLocationCanonical.stylebook_id == stylebook_id,
            StylebookLocationAlias.suppressed.is_(False),
            or_(*conds),
        )
        .distinct()
        .limit(limit)
    )
    ids = session.exec(stmt).all()
    return [(int(i), None) for i in ids]


def load_canonical_match_features(
    session: Session,
    *,
    canonical_ids: list[int],
) -> dict[int, tuple[StylebookLocationCanonical, tuple[str, ...]]]:
    """Map canonical id → (row, normalized_aliases including label as alias-like string)."""
    if not canonical_ids:
        return {}
    canon_rows = session.exec(
        select(StylebookLocationCanonical).where(col(StylebookLocationCanonical.id).in_(canonical_ids))
    ).all()
    by_id: dict[int, StylebookLocationCanonical] = {}
    for c in canon_rows:
        if c.id is not None:
            by_id[int(c.id)] = c
    alias_rows = session.exec(
        select(StylebookLocationAlias).where(
            col(StylebookLocationAlias.location_canonical_id).in_(canonical_ids),
            StylebookLocationAlias.suppressed == False,  # noqa: E712
        )
    ).all()
    aliases_by_canon: dict[int, list[str]] = {cid: [] for cid in canonical_ids}
    for a in alias_rows:
        if a.location_canonical_id is None:
            continue
        cid = int(a.location_canonical_id)
        if cid in aliases_by_canon:
            aliases_by_canon[cid].append(str(a.normalized_alias))
    out: dict[int, tuple[StylebookLocationCanonical, tuple[str, ...]]] = {}
    for cid in canonical_ids:
        c = by_id.get(cid)
        if c is None:
            continue
        merged = tuple(sorted(set(aliases_by_canon.get(cid, []))))
        out[cid] = (c, merged)
    return out
