"""Find location canonicals with the same or very similar display names."""

from __future__ import annotations

import difflib
from collections import defaultdict

from backfield_db import StylebookLocationCanonical
from sqlalchemy import text
from sqlmodel import Session, col, select

from backfield_entities.quality.dismissals import filter_dismissed_pairs, load_dismissed_keys
from backfield_entities.quality.finders._clustering import cluster_ids_from_pairs
from backfield_entities.quality.finders._duplicate_labels import (
    _all_member_ids,
    filter_duplicate_label_clusters_by_query,
    load_canonical_labels,
    sort_duplicate_label_clusters,
)
from backfield_entities.quality.types import CleanupLocationCanonicalRow

# Near-duplicates must share the same primary name (pre-comma head) and pass full-label similarity.
DEFAULT_FULL_SIMILARITY_THRESHOLD: float = 0.72
DEFAULT_HEAD_SIMILARITY_THRESHOLD: float = 0.75
_CHECK_ID = "duplicate-locations"
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


def _star_edges(members: list[str]) -> list[tuple[str, str]]:
    if len(members) < 2:
        return []
    root = members[0]
    return [(root, member) for member in members[1:]]


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
        pairs.extend(_star_edges(members))
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


def _postgres_near_duplicate_pair_edges(
    session: Session,
    *,
    stylebook_id: int,
    full_threshold: float,
) -> list[tuple[str, str]]:
    """Join on equal pre-comma head (indexed), not full-label trigram self-join."""
    rows = session.execute(
        text(
            """
            SELECT a.id AS a_id, b.id AS b_id
            FROM stylebook_location_canonical AS a
            INNER JOIN stylebook_location_canonical AS b
                ON a.stylebook_id = b.stylebook_id
               AND a.id < b.id
               AND lower(trim(split_part(a.label, ',', 1)))
                   = lower(trim(split_part(b.label, ',', 1)))
            WHERE a.stylebook_id = :sid
              AND length(trim(a.label)) >= :min_len
              AND length(trim(b.label)) >= :min_len
              AND length(trim(split_part(a.label, ',', 1))) >= :min_head_len
              AND lower(trim(a.label)) <> lower(trim(b.label))
              AND lower(trim(a.label)) % lower(trim(b.label))
              AND similarity(lower(trim(a.label)), lower(trim(b.label))) >= :full_th
            """
        ),
        {
            "sid": stylebook_id,
            "min_len": _MIN_LABEL_LEN,
            "min_head_len": _MIN_HEAD_LEN,
            "full_th": full_threshold,
        },
    ).all()
    out: list[tuple[str, str]] = []
    for a_id, b_id in rows:
        if a_id is None or b_id is None:
            continue
        out.append((str(a_id), str(b_id)))
    return out


def _sqlite_near_duplicate_pair_edges(
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
    by_head: dict[str, list[tuple[str, str]]] = defaultdict(list)
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
        by_head[head].append((str(row_id), norm))

    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for head, head_rows in by_head.items():
        if len(head_rows) < 2:
            continue
        for i, (a_id, a_norm) in enumerate(head_rows):
            for b_id, b_norm in head_rows[i + 1 :]:
                if a_norm == b_norm:
                    continue
                left, right = (a_id, b_id) if a_id < b_id else (b_id, a_id)
                if (left, right) in seen:
                    continue
                full_ratio = difflib.SequenceMatcher(None, a_norm, b_norm).ratio()
                if full_ratio < full_threshold:
                    continue
                head_ratio = difflib.SequenceMatcher(None, head, _label_head(b_norm)).ratio()
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
        near = _postgres_near_duplicate_pair_edges(
            session,
            stylebook_id=stylebook_id,
            full_threshold=full_threshold,
        )
    else:
        near = _sqlite_near_duplicate_pair_edges(
            session,
            stylebook_id=stylebook_id,
            full_threshold=full_threshold,
            head_threshold=head_threshold,
        )
    return _dedupe_pairs([*exact, *near])


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
    dismissed = load_dismissed_keys(session, stylebook_id=stylebook_id, check_id=_CHECK_ID)
    pairs = filter_dismissed_pairs(pairs, dismissed)
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
    query: str | None = None,
) -> tuple[list[list[str]], int]:
    clusters = duplicate_location_cluster_ids(
        session,
        stylebook_id=stylebook_id,
        full_threshold=full_threshold,
        head_threshold=head_threshold,
    )
    if clusters:
        labels_by_id = load_canonical_labels(
            session,
            StylebookLocationCanonical,
            _all_member_ids(clusters),
        )
        clusters = sort_duplicate_label_clusters(clusters, labels_by_id)
        clusters = filter_duplicate_label_clusters_by_query(clusters, labels_by_id, query)
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
