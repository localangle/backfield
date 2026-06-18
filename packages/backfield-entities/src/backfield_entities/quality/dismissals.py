"""Persisted cleanup dismissals (duplicate pairs and list items)."""

from __future__ import annotations

from backfield_db import StylebookCleanupDismissal
from sqlmodel import Session, col, select

CLUSTER_CLEANUP_CHECK_IDS: frozenset[str] = frozenset(
    {
        "duplicate-locations",
        "duplicate-people",
        "duplicate-organizations",
    }
)
LIST_CLEANUP_CHECK_IDS: frozenset[str] = frozenset({"missing-geometry-locations"})


def pair_key_for_ids(left_id: str, right_id: str) -> str:
    """Stable key for a canonical pair (sorted ids)."""
    a, b = (left_id, right_id) if left_id < right_id else (right_id, left_id)
    return f"{a}|{b}"


def canonical_dismissal_key(canonical_id: str) -> str:
    """Stable key for a single canonical on list-style cleanup checks."""
    return canonical_id


def all_pairs_for_members(member_ids: list[str]) -> list[tuple[str, str]]:
    sorted_ids = sorted({member_id for member_id in member_ids if member_id})
    pairs: list[tuple[str, str]] = []
    for index, left_id in enumerate(sorted_ids):
        for right_id in sorted_ids[index + 1 :]:
            pairs.append((left_id, right_id))
    return pairs


def load_dismissed_keys(
    session: Session,
    *,
    stylebook_id: int,
    check_id: str,
) -> set[str]:
    rows = session.exec(
        select(StylebookCleanupDismissal.pair_key).where(
            StylebookCleanupDismissal.stylebook_id == stylebook_id,
            StylebookCleanupDismissal.check_id == check_id,
        )
    ).all()
    return {str(row) for row in rows}


def filter_dismissed_pairs(
    pairs: list[tuple[str, str]],
    dismissed_keys: set[str],
) -> list[tuple[str, str]]:
    if not dismissed_keys:
        return pairs
    out: list[tuple[str, str]] = []
    for left_id, right_id in pairs:
        if pair_key_for_ids(left_id, right_id) in dismissed_keys:
            continue
        out.append((left_id, right_id))
    return out


def dismiss_pair(
    session: Session,
    *,
    stylebook_id: int,
    check_id: str,
    left_id: str,
    right_id: str,
    created_by_user_id: int | None = None,
) -> bool:
    """Record dismissal for one canonical pair. Returns True when a new row was inserted."""
    key = pair_key_for_ids(left_id, right_id)
    existing = load_dismissed_keys(session, stylebook_id=stylebook_id, check_id=check_id)
    if key in existing:
        return False
    session.add(
        StylebookCleanupDismissal(
            stylebook_id=stylebook_id,
            check_id=check_id,
            pair_key=key,
            created_by_user_id=created_by_user_id,
        )
    )
    return True


def dismiss_cluster_members(
    session: Session,
    *,
    stylebook_id: int,
    check_id: str,
    member_ids: list[str],
    created_by_user_id: int | None = None,
) -> int:
    """Record dismissals for every pair in a cluster. Returns rows inserted."""
    existing = load_dismissed_keys(session, stylebook_id=stylebook_id, check_id=check_id)
    inserted = 0
    for left_id, right_id in all_pairs_for_members(member_ids):
        key = pair_key_for_ids(left_id, right_id)
        if key in existing:
            continue
        session.add(
            StylebookCleanupDismissal(
                stylebook_id=stylebook_id,
                check_id=check_id,
                pair_key=key,
                created_by_user_id=created_by_user_id,
            )
        )
        existing.add(key)
        inserted += 1
    return inserted


def dismiss_canonical_issue(
    session: Session,
    *,
    stylebook_id: int,
    check_id: str,
    canonical_id: str,
    created_by_user_id: int | None = None,
) -> bool:
    """Dismiss a list-style cleanup item. Returns True when a new row was inserted."""
    key = canonical_dismissal_key(canonical_id)
    existing = load_dismissed_keys(session, stylebook_id=stylebook_id, check_id=check_id)
    if key in existing:
        return False
    session.add(
        StylebookCleanupDismissal(
            stylebook_id=stylebook_id,
            check_id=check_id,
            pair_key=key,
            created_by_user_id=created_by_user_id,
        )
    )
    return True


def undismiss_cluster_members(
    session: Session,
    *,
    stylebook_id: int,
    check_id: str,
    member_ids: list[str],
) -> int:
    """Remove pair dismissals for every pair in a cluster. Returns rows deleted."""
    keys = {
        pair_key_for_ids(left_id, right_id)
        for left_id, right_id in all_pairs_for_members(member_ids)
    }
    if not keys:
        return 0
    rows = list(
        session.exec(
            select(StylebookCleanupDismissal).where(
                StylebookCleanupDismissal.stylebook_id == stylebook_id,
                StylebookCleanupDismissal.check_id == check_id,
                col(StylebookCleanupDismissal.pair_key).in_(keys),
            )
        ).all()
    )
    for row in rows:
        session.delete(row)
    return len(rows)


def undismiss_canonical_issue(
    session: Session,
    *,
    stylebook_id: int,
    check_id: str,
    canonical_id: str,
) -> bool:
    """Remove a list-style dismissal. Returns True when a row was deleted."""
    key = canonical_dismissal_key(canonical_id)
    row = session.exec(
        select(StylebookCleanupDismissal).where(
            StylebookCleanupDismissal.stylebook_id == stylebook_id,
            StylebookCleanupDismissal.check_id == check_id,
            StylebookCleanupDismissal.pair_key == key,
        )
    ).first()
    if row is None:
        return False
    session.delete(row)
    return True
