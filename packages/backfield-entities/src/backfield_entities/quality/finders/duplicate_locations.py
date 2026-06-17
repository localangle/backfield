"""Find location canonicals with very similar labels (possible duplicates)."""

from __future__ import annotations

import difflib
import re
from collections import defaultdict

from backfield_db import StylebookLocationCanonical
from sqlalchemy import text
from sqlmodel import Session, col, select

from backfield_entities.quality.finders._clustering import cluster_ids_from_pairs
from backfield_entities.quality.types import CleanupLocationCanonicalRow

DEFAULT_DUPLICATE_SIMILARITY_THRESHOLD: float = 0.6
_MIN_LABEL_LEN_FOR_DUPE: int = 4


def _first_block_token(label: str) -> str:
    cleaned = re.sub(r"[^\w\s]", " ", label.lower())
    parts = [p for p in cleaned.split() if len(p) >= 3]
    return parts[0] if parts else label.strip().lower()[:3]


def _postgres_similar_pairs(
    session: Session,
    *,
    stylebook_id: int,
    threshold: float,
) -> list[tuple[str, str, float]]:
    session.execute(
        text("SELECT set_config('pg_trgm.similarity_threshold', :th, true)"),
        {"th": str(threshold)},
    )
    rows = session.execute(
        text(
            """
            SELECT
                a.id AS a_id,
                b.id AS b_id,
                similarity(lower(a.label), lower(b.label)) AS sim
            FROM stylebook_location_canonical AS a
            INNER JOIN stylebook_location_canonical AS b
                ON a.stylebook_id = b.stylebook_id
               AND a.id < b.id
               AND lower(a.label) % lower(b.label)
            WHERE a.stylebook_id = :sid
              AND length(trim(a.label)) >= :min_len
              AND length(trim(b.label)) >= :min_len
              AND similarity(lower(a.label), lower(b.label)) >= :th
            ORDER BY sim DESC
            """
        ),
        {
            "sid": stylebook_id,
            "th": threshold,
            "min_len": _MIN_LABEL_LEN_FOR_DUPE,
        },
    ).all()
    out: list[tuple[str, str, float]] = []
    for a_id, b_id, sim in rows:
        if a_id is None or b_id is None:
            continue
        out.append((str(a_id), str(b_id), float(sim or 0.0)))
    return out


def _sqlite_similar_pairs(
    session: Session,
    *,
    stylebook_id: int,
    threshold: float,
) -> list[tuple[str, str, float]]:
    rows = session.exec(
        select(StylebookLocationCanonical.id, StylebookLocationCanonical.label).where(
            StylebookLocationCanonical.stylebook_id == stylebook_id
        )
    ).all()
    by_block: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for row_id, label in rows:
        if row_id is None or not label:
            continue
        label_text = str(label).strip()
        if len(label_text) < _MIN_LABEL_LEN_FOR_DUPE:
            continue
        block = _first_block_token(label_text)
        by_block[block].append((str(row_id), label_text.lower()))

    pairs: list[tuple[str, str, float]] = []
    seen: set[tuple[str, str]] = set()
    for block_rows in by_block.values():
        if len(block_rows) < 2:
            continue
        for i, (a_id, a_label) in enumerate(block_rows):
            for b_id, b_label in block_rows[i + 1 :]:
                if a_id >= b_id:
                    left, right = b_id, a_id
                else:
                    left, right = a_id, b_id
                key = (left, right)
                if key in seen:
                    continue
                ratio = difflib.SequenceMatcher(None, a_label, b_label).ratio()
                if ratio >= threshold:
                    seen.add(key)
                    pairs.append((left, right, ratio))
    pairs.sort(key=lambda item: -item[2])
    return pairs


def similar_location_canonical_pairs(
    session: Session,
    *,
    stylebook_id: int,
    threshold: float = DEFAULT_DUPLICATE_SIMILARITY_THRESHOLD,
) -> list[tuple[str, str, float]]:
    bind = session.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        return _postgres_similar_pairs(session, stylebook_id=stylebook_id, threshold=threshold)
    return _sqlite_similar_pairs(session, stylebook_id=stylebook_id, threshold=threshold)


def duplicate_location_cluster_ids(
    session: Session,
    *,
    stylebook_id: int,
    threshold: float = DEFAULT_DUPLICATE_SIMILARITY_THRESHOLD,
) -> list[list[str]]:
    pairs = similar_location_canonical_pairs(
        session,
        stylebook_id=stylebook_id,
        threshold=threshold,
    )
    return cluster_ids_from_pairs([(a_id, b_id) for a_id, b_id, _sim in pairs])


def count_duplicate_location_clusters(
    session: Session,
    *,
    stylebook_id: int,
    threshold: float = DEFAULT_DUPLICATE_SIMILARITY_THRESHOLD,
) -> int:
    return len(
        duplicate_location_cluster_ids(
            session,
            stylebook_id=stylebook_id,
            threshold=threshold,
        )
    )


def paginate_duplicate_location_clusters(
    session: Session,
    *,
    stylebook_id: int,
    threshold: float = DEFAULT_DUPLICATE_SIMILARITY_THRESHOLD,
    limit: int,
    offset: int,
) -> tuple[list[list[str]], int]:
    clusters = duplicate_location_cluster_ids(
        session,
        stylebook_id=stylebook_id,
        threshold=threshold,
    )
    total = len(clusters)
    page = clusters[offset : offset + limit]
    return page, total


def load_cleanup_location_rows(
    session: Session,
    *,
    canonical_ids: list[str],
) -> dict[str, CleanupLocationCanonicalRow]:
    if not canonical_ids:
        return {}
    rows = session.exec(
        select(StylebookLocationCanonical).where(
            col(StylebookLocationCanonical.id).in_(canonical_ids)
        )
    ).all()
    out: dict[str, CleanupLocationCanonicalRow] = {}
    for row in rows:
        if row.id is None:
            continue
        out[str(row.id)] = CleanupLocationCanonicalRow(
            id=str(row.id),
            slug=str(row.slug),
            label=str(row.label),
            location_type=str(row.location_type) if row.location_type else None,
            status=str(row.status),
        )
    return out
