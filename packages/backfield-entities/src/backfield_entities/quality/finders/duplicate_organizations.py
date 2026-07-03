"""Find organization canonicals that are near-duplicates of each other.

The public functions preserve the ``duplicate-organizations`` cleanup check
contract used by the Stylebook API and UI. The internals use an
organization-specific matcher (variants, bounded blocking, guardrails)
implemented in :mod:`_organization_duplicate_signals`.
"""

from __future__ import annotations

from backfield_db import StylebookOrganizationCanonical
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
from backfield_entities.quality.finders._organization_duplicate_signals import (
    DEFAULT_ORG_ACCEPT_THRESHOLD,
    DEFAULT_ORG_MAX_BLOCK_SIZE,
    OrganizationDuplicateProfile,
    build_organization_profile,
    generate_organization_pair_edges,
)

_SIMILAR_FALLBACK = "Similar organizations"
_CHECK_ID = "duplicate-organizations"


def _load_organization_profiles(
    session: Session,
    *,
    stylebook_id: int,
) -> list[OrganizationDuplicateProfile]:
    rows = session.exec(
        select(
            StylebookOrganizationCanonical.id,
            StylebookOrganizationCanonical.label,
            StylebookOrganizationCanonical.organization_type,
        ).where(StylebookOrganizationCanonical.stylebook_id == stylebook_id)
    ).all()
    profiles: list[OrganizationDuplicateProfile] = []
    for row_id, label, organization_type in rows:
        if row_id is None or not label:
            continue
        clean = str(label).strip()
        if not clean:
            continue
        profiles.append(
            build_organization_profile(
                canonical_id=str(row_id),
                label=clean,
                organization_type=organization_type,
            )
        )
    return profiles


def _accept_threshold(full_threshold: float) -> float:
    """Preserve the existing router keyword while defaulting to the org threshold."""
    if full_threshold == DEFAULT_FULL_SIMILARITY_THRESHOLD:
        return DEFAULT_ORG_ACCEPT_THRESHOLD
    return full_threshold


def duplicate_organization_pair_edges(
    session: Session,
    *,
    stylebook_id: int,
    full_threshold: float = DEFAULT_FULL_SIMILARITY_THRESHOLD,
    max_block_size: int = DEFAULT_ORG_MAX_BLOCK_SIZE,
) -> list[tuple[str, str]]:
    profiles = _load_organization_profiles(session, stylebook_id=stylebook_id)
    edges = generate_organization_pair_edges(
        profiles,
        threshold=_accept_threshold(full_threshold),
        max_block_size=max_block_size,
    )
    pairs = [(edge.left_id, edge.right_id) for edge in edges]
    return dedupe_pairs(pairs)


def _prepare_duplicate_organization_clusters(
    session: Session,
    *,
    stylebook_id: int,
    full_threshold: float,
    max_block_size: int,
) -> tuple[list[list[str]], dict[str, str]]:
    pairs = duplicate_organization_pair_edges(
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
    labels_by_id = load_canonical_labels(session, StylebookOrganizationCanonical, all_ids)
    if len(labels_by_id) < len(all_ids):
        # Fall back to a targeted fetch for any missing rows (StylebookOrganizationCanonical.id
        # is TEXT, so the shared helper should cover them, but keep the fetch defensive).
        missing = [cid for cid in all_ids if cid not in labels_by_id]
        if missing:
            extra = session.exec(
                select(
                    StylebookOrganizationCanonical.id,
                    StylebookOrganizationCanonical.label,
                ).where(col(StylebookOrganizationCanonical.id).in_(missing))
            ).all()
            for row_id, label in extra:
                if row_id is not None:
                    labels_by_id[str(row_id)] = (label or "").strip()
    return sort_duplicate_label_clusters(clusters, labels_by_id), labels_by_id


def duplicate_organization_cluster_ids(
    session: Session,
    *,
    stylebook_id: int,
    full_threshold: float = DEFAULT_FULL_SIMILARITY_THRESHOLD,
    max_block_size: int = DEFAULT_ORG_MAX_BLOCK_SIZE,
) -> list[list[str]]:
    clusters, _labels = _prepare_duplicate_organization_clusters(
        session,
        stylebook_id=stylebook_id,
        full_threshold=full_threshold,
        max_block_size=max_block_size,
    )
    return clusters


def count_duplicate_organization_clusters(
    session: Session,
    *,
    stylebook_id: int,
    full_threshold: float = DEFAULT_FULL_SIMILARITY_THRESHOLD,
    max_block_size: int = DEFAULT_ORG_MAX_BLOCK_SIZE,
) -> int:
    return len(
        duplicate_organization_cluster_ids(
            session,
            stylebook_id=stylebook_id,
            full_threshold=full_threshold,
            max_block_size=max_block_size,
        )
    )


def paginate_duplicate_organization_clusters(
    session: Session,
    *,
    stylebook_id: int,
    limit: int,
    offset: int,
    full_threshold: float = DEFAULT_FULL_SIMILARITY_THRESHOLD,
    query: str | None = None,
    max_block_size: int = DEFAULT_ORG_MAX_BLOCK_SIZE,
) -> tuple[list[list[str]], int]:
    clusters, labels_by_id = _prepare_duplicate_organization_clusters(
        session,
        stylebook_id=stylebook_id,
        full_threshold=full_threshold,
        max_block_size=max_block_size,
    )
    clusters = filter_duplicate_label_clusters_by_query(clusters, labels_by_id, query)
    total = len(clusters)
    page = clusters[offset : offset + limit]
    return page, total


def organization_cluster_display_label(labels: list[str]) -> str:
    return cluster_display_label(labels, similar_fallback=_SIMILAR_FALLBACK)
