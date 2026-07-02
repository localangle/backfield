"""Shared duplicate-label clustering for stylebook canonical rows."""

from __future__ import annotations

import difflib
from collections import defaultdict
from typing import Literal, TypeVar

from sqlalchemy import text
from sqlmodel import Session, SQLModel, col, select

from backfield_entities.quality.dismissals import filter_dismissed_pairs, load_dismissed_keys
from backfield_entities.quality.finders._clustering import cluster_ids_from_pairs

DEFAULT_FULL_SIMILARITY_THRESHOLD: float = 0.72
_MIN_LABEL_LEN: int = 4
_MIN_BLOCK_LEN: int = 3
_MIN_FIRST_TOKEN_LEN: int = 2
_LABEL_APOSTROPHE_CHARS = "\u2018\u2019\u02bc\u0060"

NearDuplicateBlock = Literal["comma_head", "first_token", "none"]

CanonicalModel = TypeVar("CanonicalModel", bound=SQLModel)


def normalize_label(label: str) -> str:
    text = label.strip().lower()
    for ch in _LABEL_APOSTROPHE_CHARS:
        text = text.replace(ch, "'")
    return text


def _normalized_label_sql(expr: str) -> str:
    return (
        f"lower(trim(translate({expr}, "
        f"E'\\u2018\\u2019\\u02bc\\u0060', "
        f"E'''''')))"
    )


def block_key_for_label(label: str, *, near_block: NearDuplicateBlock) -> str:
    norm = normalize_label(label)
    if near_block == "comma_head":
        comma = norm.find(",")
        if comma >= 0:
            return norm[:comma].strip()
        return norm
    if near_block == "first_token":
        parts = norm.split()
        return parts[0] if parts else norm
    return norm


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


def _all_member_ids(clusters: list[list[str]]) -> list[str]:
    return sorted({member_id for cluster in clusters for member_id in cluster})


def load_canonical_labels(
    session: Session,
    model: type[CanonicalModel],
    canonical_ids: list[str],
) -> dict[str, str]:
    if not canonical_ids:
        return {}
    rows = session.exec(
        select(model.id, model.label).where(col(model.id).in_(canonical_ids))  # type: ignore[attr-defined]
    ).all()
    return {
        str(row_id): str(label).strip() if label else ""
        for row_id, label in rows
        if row_id is not None
    }


def sort_duplicate_label_clusters(
    clusters: list[list[str]],
    labels_by_id: dict[str, str],
) -> list[list[str]]:
    def sort_key(member_ids: list[str]) -> tuple[int, int, str, str]:
        norms = {
            normalize_label(labels_by_id[member_id])
            for member_id in member_ids
            if labels_by_id.get(member_id)
        }
        is_exact = len(norms) == 1 and bool(norms)
        primary_label = (
            min(norms)
            if is_exact
            else normalize_label(labels_by_id.get(member_ids[0], ""))
        )
        return (0 if is_exact else 1, -len(member_ids), primary_label, member_ids[0])

    return sorted(clusters, key=sort_key)


def filter_duplicate_label_clusters_by_query(
    clusters: list[list[str]],
    labels_by_id: dict[str, str],
    query: str | None,
) -> list[list[str]]:
    needle = normalize_label(query or "")
    if not needle:
        return clusters
    filtered: list[list[str]] = []
    for member_ids in clusters:
        if any(
            needle in normalize_label(labels_by_id.get(member_id, ""))
            for member_id in member_ids
        ):
            filtered.append(member_ids)
    return filtered


def _prepare_duplicate_label_clusters(
    session: Session,
    *,
    model: type[CanonicalModel],
    stylebook_id: int,
    check_id: str,
    full_threshold: float,
    near_block: NearDuplicateBlock,
) -> tuple[list[list[str]], dict[str, str]]:
    pairs = duplicate_label_pair_edges(
        session,
        model=model,
        stylebook_id=stylebook_id,
        full_threshold=full_threshold,
        near_block=near_block,
    )
    dismissed = load_dismissed_keys(session, stylebook_id=stylebook_id, check_id=check_id)
    pairs = filter_dismissed_pairs(pairs, dismissed)
    clusters = cluster_ids_from_pairs(pairs)
    if not clusters:
        return [], {}
    labels_by_id = load_canonical_labels(session, model, _all_member_ids(clusters))
    return sort_duplicate_label_clusters(clusters, labels_by_id), labels_by_id


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
            GROUP BY {_normalized_label_sql("label")}
            HAVING count(*) > 1
            ORDER BY count(*) DESC, {_normalized_label_sql("label")}
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


def _block_key_sql(label_expr: str, *, near_block: NearDuplicateBlock) -> str:
    if near_block == "first_token":
        return f"lower(trim(split_part({label_expr}, ' ', 1)))"
    if near_block == "comma_head":
        return f"lower(trim(split_part({label_expr}, ',', 1)))"
    return f"lower(trim({label_expr}))"


def _min_block_len(near_block: NearDuplicateBlock) -> int:
    if near_block == "first_token":
        return _MIN_FIRST_TOKEN_LEN
    if near_block == "comma_head":
        return _MIN_BLOCK_LEN
    return 1


def _postgres_near_duplicate_pair_edges(
    session: Session,
    *,
    table: str,
    stylebook_id: int,
    full_threshold: float,
    near_block: NearDuplicateBlock,
) -> list[tuple[str, str]]:
    a_block = _block_key_sql("a.label", near_block=near_block)
    b_block = _block_key_sql("b.label", near_block=near_block)
    block_join = ""
    block_len_filter = ""
    if near_block != "none":
        block_join = f"AND {a_block} = {b_block}"
        block_len_filter = f"AND length({a_block}) >= :min_block_len"
    rows = session.execute(
        text(
            f"""
            SELECT a.id AS a_id, b.id AS b_id
            FROM {table} AS a
            INNER JOIN {table} AS b
                ON a.stylebook_id = b.stylebook_id
               AND a.id < b.id
               {block_join}
            WHERE a.stylebook_id = :sid
              AND length(trim(a.label)) >= :min_len
              AND length(trim(b.label)) >= :min_len
              {block_len_filter}
              AND lower(trim(a.label)) <> lower(trim(b.label))
              AND lower(trim(a.label)) % lower(trim(b.label))
              AND similarity(lower(trim(a.label)), lower(trim(b.label))) >= :full_th
            """
        ),
        {
            "sid": stylebook_id,
            "min_len": _MIN_LABEL_LEN,
            "min_block_len": _min_block_len(near_block),
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
    near_block: NearDuplicateBlock,
) -> list[tuple[str, str]]:
    rows = session.exec(
        select(model.id, model.label).where(model.stylebook_id == stylebook_id)  # type: ignore[attr-defined]
    ).all()
    by_block: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for row_id, label in rows:
        if row_id is None or not label:
            continue
        label_text = str(label).strip()
        if len(label_text) < _MIN_LABEL_LEN:
            continue
        norm = normalize_label(label_text)
        block = block_key_for_label(label_text, near_block=near_block)
        if near_block != "none" and len(block) < _min_block_len(near_block):
            continue
        by_block[block].append((str(row_id), norm))

    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for block_rows in by_block.values():
        if len(block_rows) < 2:
            continue
        for i, (a_id, a_norm) in enumerate(block_rows):
            for b_id, b_norm in block_rows[i + 1 :]:
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
    near_block: NearDuplicateBlock = "comma_head",
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
            near_block=near_block,
        )
    else:
        near = _sqlite_near_duplicate_pair_edges(
            session,
            model=model,
            stylebook_id=stylebook_id,
            full_threshold=full_threshold,
            near_block=near_block,
        )
    return dedupe_pairs([*exact, *near])


def duplicate_label_cluster_ids(
    session: Session,
    *,
    model: type[CanonicalModel],
    stylebook_id: int,
    check_id: str,
    full_threshold: float = DEFAULT_FULL_SIMILARITY_THRESHOLD,
    near_block: NearDuplicateBlock = "comma_head",
) -> list[list[str]]:
    clusters, _labels_by_id = _prepare_duplicate_label_clusters(
        session,
        model=model,
        stylebook_id=stylebook_id,
        check_id=check_id,
        full_threshold=full_threshold,
        near_block=near_block,
    )
    return clusters


def count_duplicate_label_clusters(
    session: Session,
    *,
    model: type[CanonicalModel],
    stylebook_id: int,
    check_id: str,
    full_threshold: float = DEFAULT_FULL_SIMILARITY_THRESHOLD,
    near_block: NearDuplicateBlock = "comma_head",
) -> int:
    return len(
        duplicate_label_cluster_ids(
            session,
            model=model,
            stylebook_id=stylebook_id,
            check_id=check_id,
            full_threshold=full_threshold,
            near_block=near_block,
        )
    )


def paginate_duplicate_label_clusters(
    session: Session,
    *,
    model: type[CanonicalModel],
    stylebook_id: int,
    check_id: str,
    limit: int,
    offset: int,
    full_threshold: float = DEFAULT_FULL_SIMILARITY_THRESHOLD,
    near_block: NearDuplicateBlock = "comma_head",
    query: str | None = None,
) -> tuple[list[list[str]], int]:
    clusters, labels_by_id = _prepare_duplicate_label_clusters(
        session,
        model=model,
        stylebook_id=stylebook_id,
        check_id=check_id,
        full_threshold=full_threshold,
        near_block=near_block,
    )
    clusters = filter_duplicate_label_clusters_by_query(clusters, labels_by_id, query)
    total = len(clusters)
    page = clusters[offset : offset + limit]
    return page, total
