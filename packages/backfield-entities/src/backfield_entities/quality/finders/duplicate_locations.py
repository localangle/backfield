"""Find location canonicals with the same or very similar display names."""

from __future__ import annotations

import difflib
import re
from collections import defaultdict
from itertools import combinations

from backfield_db import StylebookLocationCanonical
from sqlalchemy import text
from sqlmodel import Session, col, select

from backfield_entities.quality.finders._clustering import cluster_ids_from_pairs
from backfield_entities.quality.types import CleanupLocationCanonicalRow

# Full-label similarity must be high; the pre-comma "head" guard blocks suffix-only matches
# (e.g. unrelated places that only share ", Chicago, IL").
DEFAULT_FULL_SIMILARITY_THRESHOLD: float = 0.72
DEFAULT_HEAD_SIMILARITY_THRESHOLD: float = 0.75
_PG_INDEX_PROBE_THRESHOLD: float = 0.45
_MIN_LABEL_LEN: int = 4
_MIN_HEAD_LEN: int = 3


def _normalize_label(label: str) -> str:
    return label.strip().lower()


def _label_head(label: str) -> str:
    text_value = _normalize_label(label)
    comma = text_value.find(",")
    if comma >= 0:
        text_value = text_value[:comma].strip()
    return text_value


def _first_block_token(label: str) -> str:
    cleaned = re.sub(r"[^\w\s]", " ", label.lower())
    parts = [p for p in cleaned.split() if len(p) >= 3]
    return parts[0] if parts else label.strip().lower()[:3]


def _dedupe_pairs(pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    seen: set[tuple[str, str]] = set()
    out: list[tuple[str, str]] = []
    for left, right in pairs:
        key = (left, right) if left < right else (right, left)
        if key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def _exact_label_pair_edges(
    session: Session,
    *,
    stylebook_id: int,
) -> list[tuple[str, str]]:
    bind = session.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        clusters = _postgres_exact_duplicate_clusters(session, stylebook_id=stylebook_id)
    else:
        clusters = _sqlite_exact_duplicate_clusters(session, stylebook_id=stylebook_id)
    pairs: list[tuple[str, str]] = []
    for members in clusters:
        pairs.extend(combinations(members, 2))
    return pairs


def _postgres_exact_duplicate_clusters(session: Session, *, stylebook_id: int) -> list[list[str]]:
    rows = session.execute(
        text(
            """
            SELECT array_agg(id ORDER BY id)
            FROM stylebook_location_canonical
            WHERE stylebook_id = :sid
              AND length(trim(label)) > 0
            GROUP BY lower(trim(label))
            HAVING count(*) > 1
            ORDER BY count(*) DESC, lower(trim(label))
            """
        ),
        {"sid": stylebook_id},
    ).all()
    out: list[list[str]] = []
    for (member_ids,) in rows:
        if not member_ids:
            continue
        out.append([str(cid) for cid in member_ids])
    return out


def _sqlite_exact_duplicate_clusters(session: Session, *, stylebook_id: int) -> list[list[str]]:
    rows = session.exec(
        select(StylebookLocationCanonical.id, StylebookLocationCanonical.label).where(
            StylebookLocationCanonical.stylebook_id == stylebook_id
        )
    ).all()
    by_label: dict[str, list[str]] = defaultdict(list)
    for row_id, label in rows:
        if row_id is None or not label:
            continue
        norm = _normalize_label(str(label))
        if not norm:
            continue
        by_label[norm].append(str(row_id))
    clusters = [sorted(ids) for ids in by_label.values() if len(ids) >= 2]
    clusters.sort(key=lambda members: (-len(members), members[0]))
    return clusters


def _postgres_fuzzy_pair_edges(
    session: Session,
    *,
    stylebook_id: int,
    full_threshold: float,
    head_threshold: float,
) -> list[tuple[str, str]]:
    index_probe = min(full_threshold, _PG_INDEX_PROBE_THRESHOLD)
    session.execute(
        text("SELECT set_config('pg_trgm.similarity_threshold', :th, true)"),
        {"th": str(index_probe)},
    )
    rows = session.execute(
        text(
            """
            SELECT a.id AS a_id, b.id AS b_id
            FROM stylebook_location_canonical AS a
            INNER JOIN stylebook_location_canonical AS b
                ON a.stylebook_id = b.stylebook_id
               AND a.id < b.id
               AND lower(trim(a.label)) % lower(trim(b.label))
            WHERE a.stylebook_id = :sid
              AND length(trim(a.label)) >= :min_len
              AND length(trim(b.label)) >= :min_len
              AND lower(trim(a.label)) <> lower(trim(b.label))
              AND similarity(lower(trim(a.label)), lower(trim(b.label))) >= :full_th
              AND length(trim(split_part(a.label, ',', 1))) >= :min_head_len
              AND length(trim(split_part(b.label, ',', 1))) >= :min_head_len
              AND similarity(
                    lower(trim(split_part(a.label, ',', 1))),
                    lower(trim(split_part(b.label, ',', 1)))
                  ) >= :head_th
            """
        ),
        {
            "sid": stylebook_id,
            "min_len": _MIN_LABEL_LEN,
            "min_head_len": _MIN_HEAD_LEN,
            "full_th": full_threshold,
            "head_th": head_threshold,
        },
    ).all()
    out: list[tuple[str, str]] = []
    for a_id, b_id in rows:
        if a_id is None or b_id is None:
            continue
        out.append((str(a_id), str(b_id)))
    return out


def _sqlite_fuzzy_pair_edges(
    session: Session,
    *,
    stylebook_id: int,
    full_threshold: float,
    head_threshold: float,
) -> list[tuple[str, str]]:
    rows = session.exec(
        select(StylebookLocationCanonical.id, StylebookLocationCanonical.label).where(
            StylebookLocationCanonical.stylebook_id == stylebook_id
        )
    ).all()
    by_head_block: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for row_id, label in rows:
        if row_id is None or not label:
            continue
        label_text = str(label).strip()
        if len(label_text) < _MIN_LABEL_LEN:
            continue
        norm = _normalize_label(label_text)
        head = _label_head(label_text)
        if len(head) < _MIN_HEAD_LEN:
            continue
        block = _first_block_token(head)
        by_head_block[block].append((str(row_id), norm, head))

    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for block_rows in by_head_block.values():
        if len(block_rows) < 2:
            continue
        for i, (a_id, a_norm, a_head) in enumerate(block_rows):
            for b_id, b_norm, b_head in block_rows[i + 1 :]:
                if a_norm == b_norm:
                    continue
                left, right = (a_id, b_id) if a_id < b_id else (b_id, a_id)
                if (left, right) in seen:
                    continue
                full_ratio = difflib.SequenceMatcher(None, a_norm, b_norm).ratio()
                if full_ratio < full_threshold:
                    continue
                head_ratio = difflib.SequenceMatcher(None, a_head, b_head).ratio()
                if head_ratio < head_threshold:
                    continue
                seen.add((left, right))
                pairs.append((left, right))
    return pairs


def duplicate_location_pair_edges(
    session: Session,
    *,
    stylebook_id: int,
    full_threshold: float = DEFAULT_FULL_SIMILARITY_THRESHOLD,
    head_threshold: float = DEFAULT_HEAD_SIMILARITY_THRESHOLD,
) -> list[tuple[str, str]]:
    exact = _exact_label_pair_edges(session, stylebook_id=stylebook_id)
    bind = session.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        fuzzy = _postgres_fuzzy_pair_edges(
            session,
            stylebook_id=stylebook_id,
            full_threshold=full_threshold,
            head_threshold=head_threshold,
        )
    else:
        fuzzy = _sqlite_fuzzy_pair_edges(
            session,
            stylebook_id=stylebook_id,
            full_threshold=full_threshold,
            head_threshold=head_threshold,
        )
    return _dedupe_pairs([*exact, *fuzzy])


def duplicate_location_cluster_ids(
    session: Session,
    *,
    stylebook_id: int,
    full_threshold: float = DEFAULT_FULL_SIMILARITY_THRESHOLD,
    head_threshold: float = DEFAULT_HEAD_SIMILARITY_THRESHOLD,
) -> list[list[str]]:
    pairs = duplicate_location_pair_edges(
        session,
        stylebook_id=stylebook_id,
        full_threshold=full_threshold,
        head_threshold=head_threshold,
    )
    return cluster_ids_from_pairs(pairs)


def count_duplicate_location_clusters(
    session: Session,
    *,
    stylebook_id: int,
    full_threshold: float = DEFAULT_FULL_SIMILARITY_THRESHOLD,
    head_threshold: float = DEFAULT_HEAD_SIMILARITY_THRESHOLD,
) -> int:
    return len(
        duplicate_location_cluster_ids(
            session,
            stylebook_id=stylebook_id,
            full_threshold=full_threshold,
            head_threshold=head_threshold,
        )
    )


def paginate_duplicate_location_clusters(
    session: Session,
    *,
    stylebook_id: int,
    limit: int,
    offset: int,
    full_threshold: float = DEFAULT_FULL_SIMILARITY_THRESHOLD,
    head_threshold: float = DEFAULT_HEAD_SIMILARITY_THRESHOLD,
) -> tuple[list[list[str]], int]:
    clusters = duplicate_location_cluster_ids(
        session,
        stylebook_id=stylebook_id,
        full_threshold=full_threshold,
        head_threshold=head_threshold,
    )
    total = len(clusters)
    page = clusters[offset : offset + limit]
    return page, total


def cluster_display_label(labels: list[str]) -> str:
    if not labels:
        return "Duplicate locations"
    normalized = {_normalize_label(label) for label in labels}
    if len(normalized) == 1:
        return labels[0]
    heads = {_label_head(label) for label in labels}
    if len(heads) == 1:
        return labels[0].split(",", 1)[0].strip()
    return "Similar locations"


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
