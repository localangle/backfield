"""Person canonical persist policy: alias/identity match, defer, materialize."""

from __future__ import annotations

from typing import Any

from backfield_db import StylebookPersonAlias, StylebookPersonCanonical, SubstratePerson
from sqlmodel import Session, col, select

from backfield_stylebook.canonical.policy import (
    CanonicalPersistDecision,
    CanonicalPersistPlan,
)
from backfield_stylebook.entities.person.review import (
    REVIEW_HANDLING_AUTO_DEFER,
    REVIEW_HANDLING_FLAG,
    default_review_message,
    review_context_from_source_details,
    review_reason_dict,
)
from backfield_stylebook.entities.person.types import normalize_person_text


def find_existing_person_canonical_id_by_alias(
    session: Session,
    *,
    stylebook_id: int,
    normalized_name: str,
) -> str | None:
    """Return canonical id when a non-suppressed alias matches ``normalized_name``."""
    norm = str(normalized_name).strip()
    if not norm:
        return None
    stmt = (
        select(StylebookPersonCanonical)
        .join(
            StylebookPersonAlias,
            StylebookPersonAlias.person_canonical_id == StylebookPersonCanonical.id,
        )
        .where(
            StylebookPersonCanonical.stylebook_id == stylebook_id,
            StylebookPersonAlias.normalized_alias == norm,
            StylebookPersonAlias.suppressed.is_(False),
        )
        .limit(1)
    )
    canon = session.exec(stmt).first()
    if canon is None or canon.id is None:
        return None
    return str(canon.id)


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
    """True when label + title + affiliation all match substrate identity."""
    name_ok = normalize_person_text(canon.label) == normalize_person_text(
        person.name
    ) or normalize_person_text(canon.label) == normalize_person_text(person.normalized_name)
    if not name_ok:
        return False
    return person_title_affiliation_match(person, canon)


def find_existing_person_canonical_id_by_identity(
    session: Session,
    *,
    stylebook_id: int,
    person: SubstratePerson,
) -> str | None:
    """Exact identity match on label + title + affiliation within a Stylebook."""
    stmt = select(StylebookPersonCanonical).where(
        StylebookPersonCanonical.stylebook_id == stylebook_id,
    )
    matches: list[str] = []
    for canon in session.exec(stmt).all():
        if canon.id is None:
            continue
        if person_identity_matches_canonical(person, canon):
            matches.append(str(canon.id))
    if len(matches) == 1:
        return matches[0]
    return None


def rank_person_canonical_recall_matches(
    session: Session,
    *,
    stylebook_id: int,
    person: SubstratePerson,
    limit: int = 24,
) -> list[tuple[str, str]]:
    """Ranked ``(canonical_id, label)`` by alias/name overlap and identity field agreement."""
    norm = str(person.normalized_name).strip()
    if not norm:
        return []
    title_norm = normalize_person_text(person.title)
    aff_norm = normalize_person_text(person.affiliation)
    stmt = (
        select(StylebookPersonCanonical)
        .where(StylebookPersonCanonical.stylebook_id == stylebook_id)
        .order_by(col(StylebookPersonCanonical.label).asc())
        .limit(max(limit * 3, 48))
    )
    scored: list[tuple[int, str, str]] = []
    for canon in session.exec(stmt).all():
        if canon.id is None:
            continue
        score = 0
        label_norm = normalize_person_text(canon.label)
        if label_norm == norm:
            score += 100
        elif norm in label_norm or label_norm in norm:
            score += 40
        if title_norm and normalize_person_text(canon.title) == title_norm:
            score += 20
        if aff_norm and normalize_person_text(canon.affiliation) == aff_norm:
            score += 20
        if score > 0:
            scored.append((score, str(canon.id), str(canon.label)))
    scored.sort(key=lambda row: (-row[0], row[2].lower()))
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for _score, cid, label in scored:
        if cid in seen:
            continue
        out.append((cid, label))
        seen.add(cid)
        if len(out) >= limit:
            break
    return out


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
        limit=24,
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


def decide_person_canonical_persist_plan(
    session: Session,
    *,
    stylebook_id: int,
    person: SubstratePerson,
    people_bucket: str = "ready",
    auto_apply_canonicalization: bool = False,
) -> CanonicalPersistPlan:
    """Decide link, materialize, or defer (review routing) for a substrate person row."""
    _ = people_bucket
    _ = auto_apply_canonicalization
    review_plan = _review_defer_plan(person)
    if review_plan is not None:
        return review_plan

    reasons: list[dict[str, Any]] = []

    by_identity = find_existing_person_canonical_id_by_identity(
        session, stylebook_id=stylebook_id, person=person
    )
    if by_identity is not None:
        reasons.append({"code": "linked_exact_identity", "canonical_id": by_identity})
        return CanonicalPersistPlan(
            decision=CanonicalPersistDecision.LINK_EXISTING,
            existing_canonical_id=by_identity,
            resolution_reasons=tuple(reasons),
        )

    alias_hits: list[str] = []
    norm = str(person.normalized_name).strip()
    if norm:
        stmt = (
            select(StylebookPersonCanonical.id)
            .join(
                StylebookPersonAlias,
                StylebookPersonAlias.person_canonical_id == StylebookPersonCanonical.id,
            )
            .where(
                StylebookPersonCanonical.stylebook_id == stylebook_id,
                StylebookPersonAlias.normalized_alias == norm,
                StylebookPersonAlias.suppressed.is_(False),
            )
        )
        alias_hits = [str(row) for row in session.exec(stmt).all() if row is not None]

    if alias_hits:
        link_id = _pick_link_canonical_id(
            session,
            stylebook_id=stylebook_id,
            person=person,
            candidate_ids=alias_hits,
        )
        if link_id is not None:
            canon = session.get(StylebookPersonCanonical, link_id)
            if canon is not None and person_title_affiliation_match(person, canon):
                reasons.append({"code": "linked_exact_alias", "canonical_id": link_id})
            else:
                reasons.append(
                    {
                        "code": "linked_alias_recall",
                        "canonical_id": link_id,
                        "alias_match_count": len(alias_hits),
                    }
                )
            return CanonicalPersistPlan(
                decision=CanonicalPersistDecision.LINK_EXISTING,
                existing_canonical_id=link_id,
                resolution_reasons=tuple(reasons),
            )

    reasons.append({"code": "materialized_new_canonical"})
    return CanonicalPersistPlan(
        decision=CanonicalPersistDecision.MATERIALIZE_NEW,
        resolution_reasons=tuple(reasons),
    )
