"""Find person canonicals that are near-duplicates of each other.

The public functions preserve the ``duplicate-people`` cleanup check contract
used by the Stylebook API and UI. The internals use a person-specific matcher
(variants, bounded blocking, suffix guardrails) implemented in
:mod:`_person_duplicate_signals`.
"""

from __future__ import annotations

from backfield_db import StylebookPersonCanonical
from sqlmodel import Session, col, select

from backfield_entities.quality.dismissals import filter_dismissed_pairs, load_dismissed_keys
from backfield_entities.quality.finders._clustering import cluster_ids_from_pairs
from backfield_entities.quality.finders._duplicate_labels import (
    DEFAULT_FULL_SIMILARITY_THRESHOLD,
    cluster_display_label,
    dedupe_pairs,
    filter_duplicate_label_clusters_by_query,
    load_canonical_labels,
    sort_duplicate_label_clusters,
)
from backfield_entities.quality.finders._person_duplicate_signals import (
    DEFAULT_PERSON_ACCEPT_THRESHOLD,
    DEFAULT_PERSON_MAX_BLOCK_SIZE,
    PersonDuplicateProfile,
    build_person_profile,
    generate_person_pair_edges,
)

_SIMILAR_FALLBACK = "Similar people"
_CHECK_ID = "duplicate-people"


def _load_person_profiles(
    session: Session,
    *,
    stylebook_id: int,
) -> list[PersonDuplicateProfile]:
    rows = session.exec(
        select(
            StylebookPersonCanonical.id,
            StylebookPersonCanonical.label,
            StylebookPersonCanonical.person_type,
            StylebookPersonCanonical.status,
        ).where(StylebookPersonCanonical.stylebook_id == stylebook_id)
    ).all()
    profiles: list[PersonDuplicateProfile] = []
    for row_id, label, person_type, status in rows:
        if row_id is None or not label:
            continue
        if (status or "active").strip().lower() != "active":
            continue
        clean = str(label).strip()
        if not clean:
            continue
        profiles.append(
            build_person_profile(
                canonical_id=str(row_id),
                label=clean,
                person_type=person_type,
            )
        )
    return profiles


def _accept_threshold(full_threshold: float) -> float:
    """Preserve the existing router keyword while defaulting to the person threshold."""
    if full_threshold == DEFAULT_FULL_SIMILARITY_THRESHOLD:
        return DEFAULT_PERSON_ACCEPT_THRESHOLD
    return full_threshold


def duplicate_person_pair_edges(
    session: Session,
    *,
    stylebook_id: int,
    full_threshold: float = DEFAULT_FULL_SIMILARITY_THRESHOLD,
    max_block_size: int = DEFAULT_PERSON_MAX_BLOCK_SIZE,
) -> list[tuple[str, str]]:
    profiles = _load_person_profiles(session, stylebook_id=stylebook_id)
    edges = generate_person_pair_edges(
        profiles,
        threshold=_accept_threshold(full_threshold),
        max_block_size=max_block_size,
    )
    pairs = [(edge.left_id, edge.right_id) for edge in edges]
    return dedupe_pairs(pairs)


def _prepare_duplicate_person_clusters(
    session: Session,
    *,
    stylebook_id: int,
    full_threshold: float,
    max_block_size: int,
) -> tuple[list[list[str]], dict[str, str]]:
    pairs = duplicate_person_pair_edges(
        session,
        stylebook_id=stylebook_id,
        full_threshold=full_threshold,
        max_block_size=max_block_size,
    )
    dismissed = load_dismissed_keys(session, stylebook_id=stylebook_id, check_id=_CHECK_ID)
    pairs = filter_dismissed_pairs(pairs, dismissed)
    clusters = cluster_ids_from_pairs(pairs)
    if not clusters:
        return [], {}
    all_ids = sorted({member_id for cluster in clusters for member_id in cluster})
    labels_by_id = load_canonical_labels(session, StylebookPersonCanonical, all_ids)
    if len(labels_by_id) < len(all_ids):
        missing = [cid for cid in all_ids if cid not in labels_by_id]
        if missing:
            extra = session.exec(
                select(
                    StylebookPersonCanonical.id,
                    StylebookPersonCanonical.label,
                ).where(col(StylebookPersonCanonical.id).in_(missing))
            ).all()
            for row_id, label in extra:
                if row_id is not None:
                    labels_by_id[str(row_id)] = (label or "").strip()
    return sort_duplicate_label_clusters(clusters, labels_by_id), labels_by_id


def duplicate_person_cluster_ids(
    session: Session,
    *,
    stylebook_id: int,
    full_threshold: float = DEFAULT_FULL_SIMILARITY_THRESHOLD,
    max_block_size: int = DEFAULT_PERSON_MAX_BLOCK_SIZE,
) -> list[list[str]]:
    clusters, _labels = _prepare_duplicate_person_clusters(
        session,
        stylebook_id=stylebook_id,
        full_threshold=full_threshold,
        max_block_size=max_block_size,
    )
    return clusters


def count_duplicate_person_clusters(
    session: Session,
    *,
    stylebook_id: int,
    full_threshold: float = DEFAULT_FULL_SIMILARITY_THRESHOLD,
    max_block_size: int = DEFAULT_PERSON_MAX_BLOCK_SIZE,
) -> int:
    return len(
        duplicate_person_cluster_ids(
            session,
            stylebook_id=stylebook_id,
            full_threshold=full_threshold,
            max_block_size=max_block_size,
        )
    )


def paginate_duplicate_person_clusters(
    session: Session,
    *,
    stylebook_id: int,
    limit: int,
    offset: int,
    full_threshold: float = DEFAULT_FULL_SIMILARITY_THRESHOLD,
    query: str | None = None,
    max_block_size: int = DEFAULT_PERSON_MAX_BLOCK_SIZE,
) -> tuple[list[list[str]], int]:
    clusters, labels_by_id = _prepare_duplicate_person_clusters(
        session,
        stylebook_id=stylebook_id,
        full_threshold=full_threshold,
        max_block_size=max_block_size,
    )
    clusters = filter_duplicate_label_clusters_by_query(clusters, labels_by_id, query)
    total = len(clusters)
    page = clusters[offset : offset + limit]
    return page, total


def person_cluster_display_label(labels: list[str]) -> str:
    return cluster_display_label(labels, similar_fallback=_SIMILAR_FALLBACK)
