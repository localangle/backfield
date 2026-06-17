"""Find organization canonicals with the same or very similar display names."""

from __future__ import annotations

from backfield_db import StylebookOrganizationCanonical
from sqlmodel import Session

from backfield_entities.quality.finders._duplicate_labels import (
    DEFAULT_FULL_SIMILARITY_THRESHOLD,
    cluster_display_label,
    count_duplicate_label_clusters,
    duplicate_label_cluster_ids,
    duplicate_label_pair_edges,
    paginate_duplicate_label_clusters,
)

_SIMILAR_FALLBACK = "Similar organizations"
# Most organization names have no comma; block on the first token (e.g. "City …").
_ORG_NEAR_BLOCK = "first_token"


def duplicate_organization_pair_edges(
    session: Session,
    *,
    stylebook_id: int,
    full_threshold: float = DEFAULT_FULL_SIMILARITY_THRESHOLD,
) -> list[tuple[str, str]]:
    return duplicate_label_pair_edges(
        session,
        model=StylebookOrganizationCanonical,
        stylebook_id=stylebook_id,
        full_threshold=full_threshold,
        near_block=_ORG_NEAR_BLOCK,
    )


def duplicate_organization_cluster_ids(
    session: Session,
    *,
    stylebook_id: int,
    full_threshold: float = DEFAULT_FULL_SIMILARITY_THRESHOLD,
) -> list[list[str]]:
    return duplicate_label_cluster_ids(
        session,
        model=StylebookOrganizationCanonical,
        stylebook_id=stylebook_id,
        full_threshold=full_threshold,
        near_block=_ORG_NEAR_BLOCK,
    )


def count_duplicate_organization_clusters(
    session: Session,
    *,
    stylebook_id: int,
    full_threshold: float = DEFAULT_FULL_SIMILARITY_THRESHOLD,
) -> int:
    return count_duplicate_label_clusters(
        session,
        model=StylebookOrganizationCanonical,
        stylebook_id=stylebook_id,
        full_threshold=full_threshold,
        near_block=_ORG_NEAR_BLOCK,
    )


def paginate_duplicate_organization_clusters(
    session: Session,
    *,
    stylebook_id: int,
    limit: int,
    offset: int,
    full_threshold: float = DEFAULT_FULL_SIMILARITY_THRESHOLD,
) -> tuple[list[list[str]], int]:
    return paginate_duplicate_label_clusters(
        session,
        model=StylebookOrganizationCanonical,
        stylebook_id=stylebook_id,
        limit=limit,
        offset=offset,
        full_threshold=full_threshold,
        near_block=_ORG_NEAR_BLOCK,
    )


def organization_cluster_display_label(labels: list[str]) -> str:
    return cluster_display_label(labels, similar_fallback=_SIMILAR_FALLBACK)
