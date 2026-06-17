"""Shared duplicate-label clustering for stylebook canonical rows."""

from __future__ import annotations

import difflib
from collections import defaultdict
from typing import TypeVar

from sqlalchemy import text
from sqlmodel import Session, SQLModel, select

from backfield_entities.quality.finders._clustering import cluster_ids_from_pairs

DEFAULT_FULL_SIMILARITY_THRESHOLD: float = 0.72
_MIN_LABEL_LEN: int = 4

CanonicalModel = TypeVar("CanonicalModel", bound=SQLModel)


def normalize_label(label: str) -> str:
    return label.strip().lower()


def dedupe_pairs(pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    seen: set[tuple[str, str]] = set()
    out: list[tuple[str, str]] = []
    for left, right in pairs:
        key = (left, right) if left < right else (right, left)
        if key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def star_edges(members: list[str]) -> list[tuple[str, str]]:
    if len(members) < 2:
        return []
    root = members[0]
    return [(root, member) for member in members[1:]]


def cluster_display_label(
    labels: list[str],
    *,
    similar_fallback: str = "Similar records",
) -> str:
    if not labels:
        return similar_fallback
    normalized = {normalize_label(label) for label in labels}
    if len(normalized) == 1:
        return labels[0]
    return similar_fallback


def _postgres_exact_duplicate_clusters(
    session: Session,
    *,
    table: str,
    stylebook_id: int,
) -> list[list[str]]:
    rows = session.execute(
        text(
            f"""
            SELECT array_agg(id ORDER BY id)
            FROM {table}
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


def _sqlite_exact_duplicate_clusters(
    session: Session,
    *,
    model: type[CanonicalModel],
    stylebook_id: int,
) -> list[list[str]]:
    rows = session.exec(
        select(model.id, model.label).where(model.stylebook_id == stylebook_id)  # type: ignore[attr-defined]
    ).all()
    by_label: dict[str, list[str]] = defaultdict(list)
    for row_id, label in rows:
        if row_id is None or not label:
            continue
        norm = normalize_label(str(label))
        if not norm:
            continue
        by_label[norm].append(str(row_id))
    clusters = [sorted(ids) for ids in by_label.values() if len(ids) >= 2]
    clusters.sort(key=lambda members: (-len(members), members[0]))
    return clusters


def exact_label_pair_edges(
    session: Session,
    *,
    model: type[CanonicalModel],
    stylebook_id: int,
) -> list[tuple[str, str]]:
    table = str(model.__tablename__)
    bind = session.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        clusters = _postgres_exact_duplicate_clusters(
            session,
            table=table,
            stylebook_id=stylebook_id,
        )
    else:
        clusters = _sqlite_exact_duplicate_clusters(
            session,
            model=model,
            stylebook_id=stylebook_id,
        )
    pairs: list[tuple[str, str]] = []
    for members in clusters:
        pairs.extend(star_edges(members))
    return pairs


def _postgres_near_duplicate_pair_edges(
    session: Session,
    *,
    table: str,
    stylebook_id: int,
    full_threshold: float,
) -> list[tuple[str, str]]:
    rows = session.execute(
        text(
            f"""
            SELECT a.id AS a_id, b.id AS b_id
            FROM {table} AS a
            INNER JOIN {table} AS b
                ON a.stylebook_id = b.stylebook_id
               AND a.id < b.id
            WHERE a.stylebook_id = :sid
              AND length(trim(a.label)) >= :min_len
              AND length(trim(b.label)) >= :min_len
              AND lower(trim(a.label)) <> lower(trim(b.label))
              AND similarity(lower(trim(a.label)), lower(trim(b.label))) >= :full_th
            """
        ),
        {
            "sid": stylebook_id,
            "min_len": _MIN_LABEL_LEN,
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
    model: type[CanonicalModel],
    stylebook_id: int,
    full_threshold: float,
) -> list[tuple[str, str]]:
    rows = session.exec(
        select(model.id, model.label).where(model.stylebook_id == stylebook_id)  # type: ignore[attr-defined]
    ).all()
    normalized_rows: list[tuple[str, str]] = []
    for row_id, label in rows:
        if row_id is None or not label:
            continue
        label_text = str(label).strip()
        if len(label_text) < _MIN_LABEL_LEN:
            continue
        normalized_rows.append((str(row_id), normalize_label(label_text)))

    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for i, (a_id, a_norm) in enumerate(normalized_rows):
        for b_id, b_norm in normalized_rows[i + 1 :]:
            if a_norm == b_norm:
                continue
            left, right = (a_id, b_id) if a_id < b_id else (b_id, a_id)
            if (left, right) in seen:
                continue
            if difflib.SequenceMatcher(None, a_norm, b_norm).ratio() < full_threshold:
                continue
            seen.add((left, right))
            pairs.append((left, right))
    return pairs


def duplicate_label_pair_edges(
    session: Session,
    *,
    model: type[CanonicalModel],
    stylebook_id: int,
    full_threshold: float = DEFAULT_FULL_SIMILARITY_THRESHOLD,
) -> list[tuple[str, str]]:
    table = str(model.__tablename__)
    exact = exact_label_pair_edges(session, model=model, stylebook_id=stylebook_id)
    bind = session.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        near = _postgres_near_duplicate_pair_edges(
            session,
            table=table,
            stylebook_id=stylebook_id,
            full_threshold=full_threshold,
        )
    else:
        near = _sqlite_near_duplicate_pair_edges(
            session,
            model=model,
            stylebook_id=stylebook_id,
            full_threshold=full_threshold,
        )
    return dedupe_pairs([*exact, *near])


def duplicate_label_cluster_ids(
    session: Session,
    *,
    model: type[CanonicalModel],
    stylebook_id: int,
    full_threshold: float = DEFAULT_FULL_SIMILARITY_THRESHOLD,
) -> list[list[str]]:
    pairs = duplicate_label_pair_edges(
        session,
        model=model,
        stylebook_id=stylebook_id,
        full_threshold=full_threshold,
    )
    return cluster_ids_from_pairs(pairs)


def count_duplicate_label_clusters(
    session: Session,
    *,
    model: type[CanonicalModel],
    stylebook_id: int,
    full_threshold: float = DEFAULT_FULL_SIMILARITY_THRESHOLD,
) -> int:
    return len(
        duplicate_label_cluster_ids(
            session,
            model=model,
            stylebook_id=stylebook_id,
            full_threshold=full_threshold,
        )
    )


def paginate_duplicate_label_clusters(
    session: Session,
    *,
    model: type[CanonicalModel],
    stylebook_id: int,
    limit: int,
    offset: int,
    full_threshold: float = DEFAULT_FULL_SIMILARITY_THRESHOLD,
) -> tuple[list[list[str]], int]:
    clusters = duplicate_label_cluster_ids(
        session,
        model=model,
        stylebook_id=stylebook_id,
        full_threshold=full_threshold,
    )
    total = len(clusters)
    page = clusters[offset : offset + limit]
    return page, total
