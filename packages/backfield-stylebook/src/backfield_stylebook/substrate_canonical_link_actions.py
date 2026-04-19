"""Editorial substrate ↔ canonical operations (unlink, atomic relink, suggestions)."""

from __future__ import annotations

from backfield_db import StylebookLocationAlias, StylebookLocationCanonical, SubstrateLocation
from sqlmodel import Session, col, func, select

from backfield_stylebook.canonical_link import CANONICAL_LINK_LINKED, CANONICAL_LINK_PENDING
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
) -> list[tuple[int, str]]:
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
    )
    ranked = rank_scored_canonical_recall_matches(session, location=location, recall=list(recall))
    out: list[tuple[int, str]] = []
    seen: set[int] = set()
    if exact_cid is not None:
        canon = session.get(StylebookLocationCanonical, int(exact_cid))
        if canon is not None and int(canon.stylebook_id) == int(stylebook_id):
            eid = int(exact_cid)
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
    canonical_id: int,
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
            col(SubstrateLocation.stylebook_location_canonical_id) == int(canonical_id),
            SubstrateLocation.normalized_name == norm,
            col(SubstrateLocation.id) != int(exclude_substrate_location_id),
        )
    )
    other = int(session.scalar(cnt_stmt) or 0)
    if other > 0:
        return False
    alias = session.exec(
        select(StylebookLocationAlias).where(
            StylebookLocationAlias.location_canonical_id == int(canonical_id),
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
) -> None:
    """Clear canonical FK; set pending; remove matching alias on old canonical when safe."""
    if location.id is None:
        raise ValueError("location must be persisted")
    if str(location.canonical_link_status) != CANONICAL_LINK_LINKED:
        raise ValueError("location is not linked to a canonical")
    cid = location.stylebook_location_canonical_id
    if cid is None:
        raise ValueError("linked location missing stylebook_location_canonical_id")
    canon = session.get(StylebookLocationCanonical, int(cid))
    if canon is None or int(canon.stylebook_id) != int(stylebook_id):
        raise ValueError("canonical not in this stylebook")
    lid = int(location.id)
    old = int(cid)
    norm = str(location.normalized_name)
    delete_canonical_alias_if_no_other_linked_substrate(
        session,
        canonical_id=old,
        normalized_name=norm,
        exclude_substrate_location_id=lid,
    )
    location.stylebook_location_canonical_id = None
    location.canonical_link_status = CANONICAL_LINK_PENDING
    location.canonical_review_reasons_json = [
        {
            "code": "unlinked_from_canonical",
            "previous_canonical_id": old,
            "provenance": provenance,
        }
    ]
    session.add(location)


def link_substrate_to_canonical_atomic(
    session: Session,
    *,
    stylebook_id: int,
    location: SubstrateLocation,
    target_canonical_id: int,
    provenance: str = "stylebook_ui_link",
) -> bool:
    """Attach substrate to canonical B, refresh aliases on B, prune alias on old A when safe.

    Returns ``False`` if already linked to ``target_canonical_id`` (idempotent no-op).
    """
    if location.id is None:
        raise ValueError("location must be persisted")
    tid = int(target_canonical_id)
    canon = session.get(StylebookLocationCanonical, tid)
    if canon is None or int(canon.stylebook_id) != int(stylebook_id):
        raise ValueError("target canonical not in this stylebook")
    lid = int(location.id)
    prev = location.stylebook_location_canonical_id
    prev_int = int(prev) if prev is not None else None
    st = str(location.canonical_link_status)
    if st not in (CANONICAL_LINK_PENDING, CANONICAL_LINK_LINKED):
        raise ValueError("location canonical_link_status does not allow manual link")
    if st == CANONICAL_LINK_PENDING and prev_int is not None:
        raise ValueError("invalid state: pending with non-null canonical FK")
    if prev_int == tid and st == CANONICAL_LINK_LINKED:
        return False

    if st == CANONICAL_LINK_PENDING:
        location.canonical_review_reasons_json = [
            {"code": "linked_to_canonical", "canonical_id": tid, "provenance": provenance}
        ]
    else:
        location.canonical_review_reasons_json = [
            {
                "code": "relinked_canonical",
                "from_canonical_id": prev_int,
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
    if prev_int is not None and prev_int != tid:
        delete_canonical_alias_if_no_other_linked_substrate(
            session,
            canonical_id=prev_int,
            normalized_name=str(location.normalized_name),
            exclude_substrate_location_id=lid,
        )
    return True
