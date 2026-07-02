"""Find person canonicals with the same or very similar display names."""

from __future__ import annotations

from backfield_db import StylebookPersonCanonical
from sqlmodel import Session

from backfield_entities.quality.finders._duplicate_labels import (
    DEFAULT_FULL_SIMILARITY_THRESHOLD,
    cluster_display_label,
    count_duplicate_label_clusters,
    duplicate_label_cluster_ids,
    duplicate_label_pair_edges,
    paginate_duplicate_label_clusters,
)

_SIMILAR_FALLBACK = "Similar people"
_PERSON_NEAR_BLOCK = "first_token"
_CHECK_ID = "duplicate-people"


def duplicate_person_pair_edges(
    session: Session,
    *,
    stylebook_id: int,
    full_threshold: float = DEFAULT_FULL_SIMILARITY_THRESHOLD,
) -> list[tuple[str, str]]:
    return duplicate_label_pair_edges(
        session,
        model=StylebookPersonCanonical,
        stylebook_id=stylebook_id,
        full_threshold=full_threshold,
        near_block=_PERSON_NEAR_BLOCK,
    )


def duplicate_person_cluster_ids(
    session: Session,
    *,
    stylebook_id: int,
    full_threshold: float = DEFAULT_FULL_SIMILARITY_THRESHOLD,
) -> list[list[str]]:
    return duplicate_label_cluster_ids(
        session,
        model=StylebookPersonCanonical,
        stylebook_id=stylebook_id,
        check_id=_CHECK_ID,
        full_threshold=full_threshold,
        near_block=_PERSON_NEAR_BLOCK,
    )


def count_duplicate_person_clusters(
    session: Session,
    *,
    stylebook_id: int,
    full_threshold: float = DEFAULT_FULL_SIMILARITY_THRESHOLD,
) -> int:
    return count_duplicate_label_clusters(
        session,
        model=StylebookPersonCanonical,
        stylebook_id=stylebook_id,
        check_id=_CHECK_ID,
        full_threshold=full_threshold,
        near_block=_PERSON_NEAR_BLOCK,
    )


def paginate_duplicate_person_clusters(
    session: Session,
    *,
    stylebook_id: int,
    limit: int,
    offset: int,
    full_threshold: float = DEFAULT_FULL_SIMILARITY_THRESHOLD,
    query: str | None = None,
) -> tuple[list[list[str]], int]:
    return paginate_duplicate_label_clusters(
        session,
        model=StylebookPersonCanonical,
        stylebook_id=stylebook_id,
        check_id=_CHECK_ID,
        limit=limit,
        offset=offset,
        full_threshold=full_threshold,
        near_block=_PERSON_NEAR_BLOCK,
        query=query,
    )


def person_cluster_display_label(labels: list[str]) -> str:
    return cluster_display_label(labels, similar_fallback=_SIMILAR_FALLBACK)
