"""Editorial substrate ↔ canonical operations (unlink, atomic relink, suggestions)."""

from __future__ import annotations

from backfield_db import StylebookLocationAlias, StylebookLocationCanonical, SubstrateLocation
from sqlmodel import Session, col, func, select

from backfield_stylebook.canonical_link import (
    CANONICAL_LINK_LINKED,
    CANONICAL_LINK_PENDING,
    CANONICAL_LINK_UNLINKED,
    CANONICAL_LINK_WAIVED,
)
from backfield_stylebook.canonical_link_matrix import link_pair_allowed
from backfield_stylebook.canonical_policy import (
    find_existing_canonical_id_by_alias,
    rank_scored_canonical_recall_matches,
)
from backfield_stylebook.canonical_retrieval import retrieve_candidate_canonical_ids
from backfield_stylebook.locations import refresh_aliases_for_linked_location


def rank_canonical_suggestions_for_substrate(
    session: Session,
    *,
    stylebook_id: int,
    location: SubstrateLocation,
    limit: int = 24,
) -> list[tuple[str, str]]:
    """Ordered ``(canonical_id, label)`` for UI: exact alias hit first, then ingest-style recall."""
    exact_cid = find_existing_canonical_id_by_alias(
        session, stylebook_id=stylebook_id, normalized_name=str(location.normalized_name)
    )
    recall = retrieve_candidate_canonical_ids(
        session,
        stylebook_id=stylebook_id,
        query_text=str(location.name),
        normalized_query=str(location.normalized_name),
        formatted_address=location.formatted_address,
        substrate_location_type=location.location_type,
    )
    ranked = rank_scored_canonical_recall_matches(session, location=location, recall=list(recall))
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    if exact_cid is not None:
        canon = session.get(StylebookLocationCanonical, str(exact_cid))
        if canon is not None and int(canon.stylebook_id) == int(stylebook_id):
            eid = str(exact_cid)
            out.append((eid, str(canon.label)))
            seen.add(eid)
    for cid, lab, _sc, _idx in ranked:
        if cid in seen:
            continue
        out.append((cid, lab))
        seen.add(cid)
        if len(out) >= limit:
            break
    return out[:limit]


def delete_canonical_alias_if_no_other_linked_substrate(
    session: Session,
    *,
    canonical_id: str,
    normalized_name: str,
    exclude_substrate_location_id: int,
) -> bool:
    """Delete non-suppressed alias when no other linked substrate shares that normalized name."""
    norm = str(normalized_name).strip()
    if not norm:
        return False
    cnt_stmt = (
        select(func.count())
        .select_from(SubstrateLocation)
        .where(
            col(SubstrateLocation.stylebook_location_canonical_id) == str(canonical_id),
            SubstrateLocation.normalized_name == norm,
            col(SubstrateLocation.id) != int(exclude_substrate_location_id),
        )
    )
    other = int(session.scalar(cnt_stmt) or 0)
    if other > 0:
        return False
    alias = session.exec(
        select(StylebookLocationAlias).where(
            StylebookLocationAlias.location_canonical_id == str(canonical_id),
            StylebookLocationAlias.normalized_alias == norm,
            StylebookLocationAlias.suppressed.is_(False),
        )
    ).first()
    if alias is None:
        return False
    session.delete(alias)
    return True


def unlink_substrate_from_canonical(
    session: Session,
    *,
    stylebook_id: int,
    location: SubstrateLocation,
    provenance: str = "stylebook_ui_unlink",
    requeue_after_unlink: bool = True,
) -> None:
    """Clear canonical FK; remove matching alias on old canonical when safe.

    When ``requeue_after_unlink`` is true (default), set ``pending`` for the open candidate
    queue. When false, set ``unlinked`` so the row stays out of the queue (story-only remove).
    """
    if location.id is None:
        raise ValueError("location must be persisted")
    if str(location.canonical_link_status) != CANONICAL_LINK_LINKED:
        raise ValueError("location is not linked to a canonical")
    cid = location.stylebook_location_canonical_id
    if cid is None:
        raise ValueError("linked location missing stylebook_location_canonical_id")
    canon = session.get(StylebookLocationCanonical, str(cid))
    if canon is None or int(canon.stylebook_id) != int(stylebook_id):
        raise ValueError("canonical not in this stylebook")
    lid = int(location.id)
    old = str(cid)
    norm = str(location.normalized_name)
    delete_canonical_alias_if_no_other_linked_substrate(
        session,
        canonical_id=old,
        normalized_name=norm,
        exclude_substrate_location_id=lid,
    )
    location.stylebook_location_canonical_id = None
    location.canonical_link_status = (
        CANONICAL_LINK_PENDING if requeue_after_unlink else CANONICAL_LINK_UNLINKED
    )
    location.canonical_review_reasons_json = [
        {
            "code": "unlinked_from_canonical" if requeue_after_unlink else "removed_from_story",
            "previous_canonical_id": old,
            "provenance": provenance,
        }
    ]
    session.add(location)


def dispose_orphan_substrate_without_requeue(
    session: Session,
    *,
    location: SubstrateLocation,
    provenance: str,
) -> None:
    """Unlink from catalog without entering the open queue, then delete the substrate row."""
    if location.id is None:
        raise ValueError("location must be persisted")

    st = str(location.canonical_link_status or "")
    if st == CANONICAL_LINK_LINKED and location.stylebook_location_canonical_id is not None:
        cid = location.stylebook_location_canonical_id
        canon = session.get(StylebookLocationCanonical, str(cid))
        sb_id = int(canon.stylebook_id) if canon is not None else 0
        if canon is not None and sb_id > 0:
            unlink_substrate_from_canonical(
                session,
                stylebook_id=sb_id,
                location=location,
                provenance=provenance,
                requeue_after_unlink=False,
            )
        else:
            location.stylebook_location_canonical_id = None
            location.canonical_link_status = CANONICAL_LINK_UNLINKED
            location.canonical_review_reasons_json = [
                {
                    "code": "removed_from_story",
                    "previous_canonical_id": str(cid),
                    "provenance": provenance,
                    "note": "canonical_row_missing",
                }
            ]
            session.add(location)
    elif st == CANONICAL_LINK_PENDING and location.stylebook_location_canonical_id is not None:
        location.stylebook_location_canonical_id = None
        session.add(location)

    session.delete(location)


def finalize_substrate_after_article_scoped_remove(
    session: Session,
    *,
    location: SubstrateLocation,
    remaining_active_mentions: int,
    provenance: str = "agate_review_delete",
) -> tuple[bool, int]:
    """Finish substrate handling after soft-deleting mentions for one article.

    Returns ``(location_deleted, candidates_created)``. When other stories still have
    active mentions on this substrate, the row and catalog link are left unchanged.
    When none remain, unlink without requeue (if linked) and delete the substrate row.
    """
    if remaining_active_mentions > 0:
        return False, 0
    if location.id is None:
        return False, 0

    dispose_orphan_substrate_without_requeue(
        session, location=location, provenance=provenance
    )
    return True, 0


def requeue_substrate_after_story_remove(
    session: Session,
    *,
    stylebook_id: int,
    location: SubstrateLocation,
    provenance: str = "agate_review_delete",
) -> bool:
    """Unlink or reset status so the substrate appears in the open candidate queue.

    Returns True when the row was linked (and is now unlinked) or was moved from
    ``waived`` / ``unlinked`` to ``pending``. Rows already ``pending`` with no
    canonical FK return False (already in the open queue).
    """
    if location.id is None:
        raise ValueError("location must be persisted")
    st = str(location.canonical_link_status or "")
    if st == CANONICAL_LINK_LINKED and location.stylebook_location_canonical_id is not None:
        cid = location.stylebook_location_canonical_id
        canon = session.get(StylebookLocationCanonical, str(cid))
        if canon is None:
            location.stylebook_location_canonical_id = None
            location.canonical_link_status = CANONICAL_LINK_PENDING
            location.canonical_review_reasons_json = [
                {
                    "code": "unlinked_from_canonical",
                    "previous_canonical_id": str(cid),
                    "provenance": provenance,
                    "note": "canonical_row_missing",
                }
            ]
            session.add(location)
            return True
        # Use the canonical row's stylebook (may differ from project default resolution).
        unlink_substrate_from_canonical(
            session,
            stylebook_id=int(canon.stylebook_id),
            location=location,
            provenance=provenance,
        )
        return True
    if st in (CANONICAL_LINK_WAIVED, CANONICAL_LINK_UNLINKED):
        location.canonical_link_status = CANONICAL_LINK_PENDING
        location.stylebook_location_canonical_id = None
        session.add(location)
        return True
    if st == CANONICAL_LINK_PENDING and location.stylebook_location_canonical_id is not None:
        location.stylebook_location_canonical_id = None
        session.add(location)
        return True
    return False


def link_substrate_to_canonical_atomic(
    session: Session,
    *,
    stylebook_id: int,
    location: SubstrateLocation,
    target_canonical_id: str,
    provenance: str = "stylebook_ui_link",
    enforce_type_gate: bool = False,
) -> bool:
    """Attach substrate to canonical B, refresh aliases on B, prune alias on old A when safe.

    When ``enforce_type_gate`` is true, linking is allowed only if
    :func:`~backfield_stylebook.canonical_link_matrix.link_pair_allowed` returns true
    (today always true; reserved for a future deny-list).

    Returns ``False`` if already linked to ``target_canonical_id`` (idempotent no-op).
    """
    if location.id is None:
        raise ValueError("location must be persisted")
    tid = str(target_canonical_id)
    canon = session.get(StylebookLocationCanonical, tid)
    if canon is None or int(canon.stylebook_id) != int(stylebook_id):
        raise ValueError("target canonical not in this stylebook")
    if enforce_type_gate and not link_pair_allowed(location.location_type, canon.location_type):
        raise ValueError(
            "substrate location_type is incompatible with the target canonical location_type "
            "for linking"
        )
    lid = int(location.id)
    prev = location.stylebook_location_canonical_id
    prev_str = str(prev) if prev is not None else None
    st = str(location.canonical_link_status)
    if st not in (CANONICAL_LINK_PENDING, CANONICAL_LINK_LINKED):
        raise ValueError("location canonical_link_status does not allow manual link")
    if st == CANONICAL_LINK_PENDING and prev_str is not None:
        raise ValueError("invalid state: pending with non-null canonical FK")
    if prev_str == tid and st == CANONICAL_LINK_LINKED:
        return False

    if st == CANONICAL_LINK_PENDING:
        location.canonical_review_reasons_json = [
            {"code": "linked_to_canonical", "canonical_id": tid, "provenance": provenance}
        ]
    else:
        location.canonical_review_reasons_json = [
            {
                "code": "relinked_canonical",
                "from_canonical_id": prev_str,
                "to_canonical_id": tid,
                "provenance": provenance,
            }
        ]
    location.stylebook_location_canonical_id = tid
    location.canonical_link_status = CANONICAL_LINK_LINKED
    session.add(location)
    session.flush()
    refresh_aliases_for_linked_location(
        session, stylebook_id=stylebook_id, location=location, provenance=provenance
    )
    if prev_str is not None and prev_str != tid:
        delete_canonical_alias_if_no_other_linked_substrate(
            session,
            canonical_id=prev_str,
            normalized_name=str(location.normalized_name),
            exclude_substrate_location_id=lid,
        )
    return True
