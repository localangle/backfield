"""Person canonical persist policy: tier-1 identity, recall defer, materialize."""

from __future__ import annotations

from typing import Any

from backfield_db import StylebookPersonCanonical, SubstratePerson
from sqlmodel import Session, select

from backfield_entities.canonical.plan_types import (
    CanonicalPersistDecision,
    CanonicalPersistPlan,
)
from backfield_entities.entities.person.recall import (
    PERSON_RECALL_DEFAULT_LIMIT,
    canonical_ids_from_person_name_keys,
    retrieve_person_canonical_candidates,
)
from backfield_entities.entities.person.review import (
    REVIEW_HANDLING_AUTO_DEFER,
    REVIEW_HANDLING_FLAG,
    default_review_message,
    review_context_from_source_details,
    review_reason_dict,
)
from backfield_entities.entities.person.types import (
    normalize_person_text,
    person_match_key,
    person_names_match,
)

AMBIGUOUS_PERSON_CANONICAL_MATCH = "ambiguous_person_canonical_match"


def find_existing_person_canonical_id_by_alias(
    session: Session,
    *,
    stylebook_id: int,
    normalized_name: str,
) -> str | None:
    """Return canonical id when a non-suppressed alias matches ``normalized_name``."""
    if not str(normalized_name).strip():
        return None
    matches = canonical_ids_from_person_name_keys(
        session,
        stylebook_id=stylebook_id,
        name_or_norm=normalized_name,
    )
    if not matches:
        return None
    return matches[0]


def person_name_matches_canonical(
    person: SubstratePerson,
    canon: StylebookPersonCanonical,
) -> bool:
    person_name = str(person.normalized_name or person.name or "")
    if not person_match_key(person_name):
        return False
    return person_names_match(person_name, str(canon.label))


def person_affiliation_matches_canonical(
    person: SubstratePerson,
    canon: StylebookPersonCanonical,
) -> bool:
    return normalize_person_text(canon.affiliation) == normalize_person_text(person.affiliation)


def person_strong_identity_matches_canonical(
    person: SubstratePerson,
    canon: StylebookPersonCanonical,
) -> bool:
    """Tier-1 auto-link: exact normalized name (or label) + affiliation (title ignored)."""
    return person_name_matches_canonical(person, canon) and person_affiliation_matches_canonical(
        person, canon
    )


def person_title_affiliation_match(
    person: SubstratePerson,
    canon: StylebookPersonCanonical,
) -> bool:
    return normalize_person_text(canon.title) == normalize_person_text(
        person.title
    ) and normalize_person_text(canon.affiliation) == normalize_person_text(person.affiliation)


def person_identity_matches_canonical(
    person: SubstratePerson,
    canon: StylebookPersonCanonical,
) -> bool:
    """Full identity including title (used where stricter matching is required)."""
    if not person_name_matches_canonical(person, canon):
        return False
    return person_title_affiliation_match(person, canon)


def find_existing_person_canonical_id_by_strong_identity(
    session: Session,
    *,
    stylebook_id: int,
    person: SubstratePerson,
) -> str | None:
    """Single canonical match on name + affiliation within a Stylebook."""
    matches = _strong_identity_canonical_ids(session, stylebook_id=stylebook_id, person=person)
    if len(matches) == 1:
        return matches[0]
    return None


def _strong_identity_canonical_ids(
    session: Session,
    *,
    stylebook_id: int,
    person: SubstratePerson,
) -> list[str]:
    norm = normalize_person_text(person.normalized_name or person.name)
    if not norm:
        return []
    matches: list[str] = []
    seen: set[str] = set()

    for cid in canonical_ids_from_person_name_keys(
        session,
        stylebook_id=stylebook_id,
        name_or_norm=str(person.normalized_name or person.name),
    ):
        canon = session.get(StylebookPersonCanonical, cid)
        if canon is None or canon.id is None:
            continue
        if person_strong_identity_matches_canonical(person, canon):
            if cid not in seen:
                seen.add(cid)
                matches.append(cid)

    label_stmt = select(StylebookPersonCanonical).where(
        StylebookPersonCanonical.stylebook_id == stylebook_id,
    )
    for canon in session.exec(label_stmt).all():
        if canon.id is None:
            continue
        if not person_strong_identity_matches_canonical(person, canon):
            continue
        cid = str(canon.id)
        if cid not in seen:
            seen.add(cid)
            matches.append(cid)
    return matches


def rank_person_canonical_recall_matches(
    session: Session,
    *,
    stylebook_id: int,
    person: SubstratePerson,
    limit: int = PERSON_RECALL_DEFAULT_LIMIT,
) -> list[tuple[str, str]]:
    """Ranked ``(canonical_id, label)`` for UI suggestions (delegates to recall module)."""
    return retrieve_person_canonical_candidates(
        session,
        stylebook_id=stylebook_id,
        person=person,
        limit=limit,
    )


def _pick_link_canonical_id(
    session: Session,
    *,
    stylebook_id: int,
    person: SubstratePerson,
    candidate_ids: list[str] | None = None,
) -> str | None:
    """Best ranked canonical id for a link suggestion, optionally limited to candidates."""
    allowed = set(candidate_ids) if candidate_ids else None
    ranked = rank_person_canonical_recall_matches(
        session,
        stylebook_id=stylebook_id,
        person=person,
        limit=PERSON_RECALL_DEFAULT_LIMIT,
    )
    for cid, _label in ranked:
        if allowed is not None and cid not in allowed:
            continue
        return cid
    if allowed and candidate_ids:
        return candidate_ids[0]
    return None


def _review_defer_plan(person: SubstratePerson) -> CanonicalPersistPlan | None:
    details = person.source_details_json if isinstance(person.source_details_json, dict) else {}
    handling, code, message = review_context_from_source_details(details)
    if handling not in (REVIEW_HANDLING_AUTO_DEFER, REVIEW_HANDLING_FLAG) or not code:
        return None
    msg = message or default_review_message(code)
    return CanonicalPersistPlan(
        decision=CanonicalPersistDecision.DEFER,
        resolution_reasons=(review_reason_dict(code=code, message=msg),),
    )


def _ambiguous_person_defer_plan(
    *,
    recall: list[tuple[str, str]],
    best_canonical_id: str | None = None,
) -> CanonicalPersistPlan:
    recall_ids = [cid for cid, _ in recall[:PERSON_RECALL_DEFAULT_LIMIT]]
    reason: dict[str, Any] = {
        "code": AMBIGUOUS_PERSON_CANONICAL_MATCH,
        "recall_canonical_ids": recall_ids,
    }
    if best_canonical_id is not None:
        reason["best_canonical_id"] = str(best_canonical_id)
    return CanonicalPersistPlan(
        decision=CanonicalPersistDecision.DEFER,
        resolution_reasons=(reason,),
    )


def plan_has_ambiguous_person_canonical_match(plan: CanonicalPersistPlan) -> bool:
    for r in plan.resolution_reasons:
        if isinstance(r, dict) and str(r.get("code") or "") == AMBIGUOUS_PERSON_CANONICAL_MATCH:
            return True
    return False


def plan_requires_llm_person_canonical_adjudication(
    plan: CanonicalPersistPlan,
    person: SubstratePerson,
) -> bool:
    _ = person
    return plan_has_ambiguous_person_canonical_match(plan)


def person_may_materialize_canonical_after_recall(person: SubstratePerson) -> bool:
    """True when ``MATERIALIZE_NEW`` is allowed after LLM declines linking recalled canonicals.

    Mirrors location ``substrate_may_materialize_canonical_after_recall``: blocked when
    PersonExtract review routing would defer (flag/auto-defer), or when identity text is empty.
    """
    if _review_defer_plan(person) is not None:
        return False
    if not normalize_person_text(person.normalized_name or person.name):
        return False
    return True


def decide_person_canonical_persist_plan(
    session: Session,
    *,
    stylebook_id: int,
    person: SubstratePerson,
    people_bucket: str = "ready",
    auto_apply_canonicalization: bool = False,
) -> CanonicalPersistPlan:
    """Decide link, materialize, or defer for a substrate person row.

    Tier-1 auto-link uses exact normalized name + affiliation only (title is soft in recall/LLM).
    Substrate dedupe fingerprints may still include title; tier-1 criteria are narrower.
    """
    _ = people_bucket
    _ = auto_apply_canonicalization
    review_plan = _review_defer_plan(person)
    if review_plan is not None:
        return review_plan

    strong_matches = _strong_identity_canonical_ids(
        session, stylebook_id=stylebook_id, person=person
    )
    if len(strong_matches) == 1:
        cid = strong_matches[0]
        return CanonicalPersistPlan(
            decision=CanonicalPersistDecision.LINK_EXISTING,
            existing_canonical_id=cid,
            resolution_reasons=(
                {
                    "code": "linked_exact_identity",
                    "canonical_id": cid,
                    "match_basis": "name_and_affiliation",
                },
            ),
        )
    if len(strong_matches) > 1:
        recall = [(cid, "") for cid in strong_matches]
        return _ambiguous_person_defer_plan(recall=recall, best_canonical_id=strong_matches[0])

    recall = retrieve_person_canonical_candidates(
        session,
        stylebook_id=stylebook_id,
        person=person,
        limit=PERSON_RECALL_DEFAULT_LIMIT,
    )
    if not recall:
        return CanonicalPersistPlan(
            decision=CanonicalPersistDecision.MATERIALIZE_NEW,
            resolution_reasons=({"code": "materialized_new_canonical"},),
        )

    return _ambiguous_person_defer_plan(recall=recall, best_canonical_id=recall[0][0])
