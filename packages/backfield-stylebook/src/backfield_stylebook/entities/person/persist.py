"""Person canonical + alias persistence and Stylebook link operations."""

from __future__ import annotations

import re
from typing import Any

from backfield_db import StylebookPersonAlias, StylebookPersonCanonical, SubstratePerson
from sqlmodel import Session, col, func, select

from backfield_stylebook.canonical.link import (
    CANONICAL_LINK_LINKED,
    CANONICAL_LINK_PENDING,
    CANONICAL_LINK_UNLINKED,
    CANONICAL_LINK_WAIVED,
)
from backfield_stylebook.canonical.plan_types import CanonicalPersistDecision, CanonicalPersistPlan
from backfield_stylebook.entities.person.policy import (
    find_existing_person_canonical_id_by_alias,
    plan_has_ambiguous_person_canonical_match,
    rank_person_canonical_recall_matches,
)
from backfield_stylebook.entities.person.review import (
    plan_includes_auto_waive_person_review,
    plan_includes_flag_person_review,
)
from backfield_stylebook.entities.person.types import derive_person_sort_key


def _slugify_person_label(label: str) -> str:
    s = label.lower().strip().replace(" ", "-")
    s = re.sub(r"[^a-z0-9-]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "person"


def allocate_unique_person_canonical_slug(
    session: Session,
    *,
    stylebook_id: int,
    label: str,
) -> str:
    base = _slugify_person_label(label)
    slug = base
    n = 2
    while True:
        hit = session.exec(
            select(StylebookPersonCanonical.id).where(
                StylebookPersonCanonical.stylebook_id == stylebook_id,
                col(StylebookPersonCanonical.slug) == slug,
            )
        ).first()
        if hit is None:
            return slug
        slug = f"{base}-{n}"
        n += 1


def assert_canonical_link_invariant(person: SubstratePerson) -> None:
    """Debug invariant: ``linked`` iff FK set; other statuses require null FK."""
    if person.canonical_link_status == CANONICAL_LINK_LINKED:
        if person.stylebook_person_canonical_id is None:
            raise AssertionError(
                "canonical_link_status=linked requires stylebook_person_canonical_id"
            )
    else:
        if person.stylebook_person_canonical_id is not None:
            raise AssertionError(
                f"canonical_link_status={person.canonical_link_status!r} requires null "
                "stylebook_person_canonical_id"
            )


def _normalize_alias_text(text: str) -> str:
    return text.strip().lower()


def _mirror_fields_from_substrate(person: SubstratePerson) -> dict[str, Any]:
    sort_key = person.sort_key or derive_person_sort_key(person.name)
    return {
        "title": person.title,
        "affiliation": person.affiliation,
        "public_figure": bool(person.public_figure),
        "person_type": person.person_type,
        "sort_key": sort_key,
    }


def upsert_alias_for_canonical_text(
    session: Session,
    *,
    canon_id: str,
    alias_text: str,
    normalized_alias: str,
    provenance: str,
) -> None:
    norm = str(normalized_alias)
    existing = session.exec(
        select(StylebookPersonAlias).where(
            StylebookPersonAlias.person_canonical_id == canon_id,
            StylebookPersonAlias.normalized_alias == norm,
        )
    ).first()
    if existing is None:
        session.add(
            StylebookPersonAlias(
                person_canonical_id=canon_id,
                alias_text=str(alias_text),
                normalized_alias=norm,
                provenance=provenance,
                suppressed=False,
            )
        )
    else:
        existing.alias_text = str(alias_text)
        existing.provenance = provenance
        existing.suppressed = False
        session.add(existing)


def _upsert_alias_for_substrate(
    session: Session,
    *,
    canon_id: str,
    person: SubstratePerson,
    provenance: str,
) -> None:
    upsert_alias_for_canonical_text(
        session,
        canon_id=canon_id,
        alias_text=str(person.name),
        normalized_alias=str(person.normalized_name),
        provenance=provenance,
    )


def refresh_aliases_for_linked_person(
    session: Session,
    *,
    stylebook_id: int,
    person: SubstratePerson,
    provenance: str = "substrate_ingest",
) -> None:
    if person.id is None or person.stylebook_person_canonical_id is None:
        return
    canon_id = str(person.stylebook_person_canonical_id)
    canon = session.get(StylebookPersonCanonical, canon_id)
    if canon is None or int(canon.stylebook_id) != int(stylebook_id):
        return
    _upsert_alias_for_substrate(
        session,
        canon_id=canon_id,
        person=person,
        provenance=provenance,
    )


def link_to_existing_canonical(
    session: Session,
    *,
    stylebook_id: int,
    person: SubstratePerson,
    canonical_id: str,
    provenance: str = "substrate_ingest",
    audit_reasons: list[dict[str, Any]] | None = None,
) -> None:
    if person.id is None:
        return
    canon = session.get(StylebookPersonCanonical, canonical_id)
    if canon is None or int(canon.stylebook_id) != int(stylebook_id):
        return
    person.stylebook_person_canonical_id = str(canon.id)
    person.canonical_link_status = CANONICAL_LINK_LINKED
    person.canonical_review_reasons_json = (
        [dict(r) for r in audit_reasons] if audit_reasons is not None else None
    )
    session.add(person)
    session.flush()
    _upsert_alias_for_substrate(
        session,
        canon_id=str(canon.id),
        person=person,
        provenance=provenance,
    )


def create_standalone_canonical(
    session: Session,
    *,
    stylebook_id: int,
    label: str,
    title: str | None = None,
    affiliation: str | None = None,
    public_figure: bool = False,
    person_type: str | None = None,
    sort_key: str | None = None,
    provenance: str = "stylebook_ui_manual",
) -> StylebookPersonCanonical:
    clean = label.strip()
    if not clean:
        raise ValueError("label is required")
    slug = allocate_unique_person_canonical_slug(session, stylebook_id=stylebook_id, label=clean)
    resolved_sort_key = derive_person_sort_key(clean, explicit=sort_key)
    canon = StylebookPersonCanonical(
        stylebook_id=stylebook_id,
        label=clean,
        slug=slug,
        title=(title or "").strip() or None,
        affiliation=(affiliation or "").strip() or None,
        public_figure=public_figure,
        person_type=(person_type or "").strip() or None,
        sort_key=resolved_sort_key,
        primary_substrate_person_id=None,
        status="active",
    )
    session.add(canon)
    session.flush()
    cid = str(canon.id)
    upsert_alias_for_canonical_text(
        session,
        canon_id=cid,
        alias_text=clean,
        normalized_alias=_normalize_alias_text(clean),
        provenance=provenance,
    )
    session.flush()
    return canon


def materialize_new_canonical_and_link(
    session: Session,
    *,
    stylebook_id: int,
    person: SubstratePerson,
    label: str | None = None,
    provenance: str = "substrate_ingest",
    audit_reasons: list[dict[str, Any]] | None = None,
) -> None:
    if person.id is None:
        return
    clean = (label or person.name or "").strip()
    if not clean:
        return
    slug = allocate_unique_person_canonical_slug(session, stylebook_id=stylebook_id, label=clean)
    fields = _mirror_fields_from_substrate(person)
    canon = StylebookPersonCanonical(
        stylebook_id=stylebook_id,
        label=clean,
        slug=slug,
        primary_substrate_person_id=None,
        status="active",
        **fields,
    )
    session.add(canon)
    session.flush()
    cid = str(canon.id)
    person.stylebook_person_canonical_id = cid
    person.canonical_link_status = CANONICAL_LINK_LINKED
    person.canonical_review_reasons_json = (
        [dict(r) for r in audit_reasons] if audit_reasons is not None else None
    )
    session.add(person)
    session.flush()
    _upsert_alias_for_substrate(
        session,
        canon_id=cid,
        person=person,
        provenance=provenance,
    )


def _canonical_suggestion_from_plan(plan: CanonicalPersistPlan) -> dict[str, Any] | None:
    if plan.decision == CanonicalPersistDecision.DEFER and (
        plan_includes_flag_person_review(plan.resolution_reasons)
        or plan_has_ambiguous_person_canonical_match(plan)
    ):
        return None
    if (
        plan.decision == CanonicalPersistDecision.LINK_EXISTING
        and plan.existing_canonical_id is not None
    ):
        return {
            "code": "canonical_suggestion",
            "source": "rules_plan",
            "suggested_action": "link_existing",
            "stylebook_person_canonical_id": str(plan.existing_canonical_id),
        }
    if plan.decision == CanonicalPersistDecision.MATERIALIZE_NEW:
        return {
            "code": "canonical_suggestion",
            "source": "rules_plan",
            "suggested_action": "materialize_new",
        }
    if plan.decision == CanonicalPersistDecision.DEFER:
        if plan_includes_auto_waive_person_review(plan.resolution_reasons):
            return None
        return {
            "code": "canonical_suggestion",
            "source": "rules_plan",
            "suggested_action": "defer",
        }
    return None


def apply_canonical_persist_plan_review_only(
    session: Session,
    *,
    stylebook_id: int,
    person: SubstratePerson,
    plan: CanonicalPersistPlan,
    people_bucket: str,
) -> None:
    _ = stylebook_id
    _ = people_bucket
    reasons: list[dict[str, Any]] = [dict(r) for r in plan.resolution_reasons]
    extra = _canonical_suggestion_from_plan(plan)
    if extra is not None:
        reasons.append(extra)
    person.stylebook_person_canonical_id = None
    person.canonical_link_status = CANONICAL_LINK_PENDING
    person.canonical_review_reasons_json = reasons
    session.add(person)


def apply_canonical_persist_plan(
    session: Session,
    *,
    stylebook_id: int,
    person: SubstratePerson,
    plan: CanonicalPersistPlan,
    people_bucket: str,
    provenance: str = "substrate_ingest",
    auto_apply_canonicalization: bool = False,
) -> None:
    _ = people_bucket
    _ = auto_apply_canonicalization
    reasons = [dict(r) for r in plan.resolution_reasons]
    if plan.decision == CanonicalPersistDecision.DEFER:
        person.stylebook_person_canonical_id = None
        if auto_apply_canonicalization and plan_includes_auto_waive_person_review(
            plan.resolution_reasons
        ):
            person.canonical_link_status = CANONICAL_LINK_WAIVED
        else:
            person.canonical_link_status = CANONICAL_LINK_PENDING
        person.canonical_review_reasons_json = reasons
        session.add(person)
        return
    if plan.decision == CanonicalPersistDecision.LINK_EXISTING:
        if plan.existing_canonical_id is None:
            return
        link_to_existing_canonical(
            session,
            stylebook_id=stylebook_id,
            person=person,
            canonical_id=str(plan.existing_canonical_id),
            provenance=provenance,
            audit_reasons=reasons,
        )
        return
    materialize_new_canonical_and_link(
        session,
        stylebook_id=stylebook_id,
        person=person,
        provenance=provenance,
        audit_reasons=reasons,
    )


def sync_substrate_person_into_stylebook(
    session: Session,
    *,
    stylebook_id: int,
    person: SubstratePerson,
    provenance: str = "substrate_ingest",
) -> None:
    if person.stylebook_person_canonical_id is not None:
        refresh_aliases_for_linked_person(
            session,
            stylebook_id=stylebook_id,
            person=person,
            provenance=provenance,
        )


def rank_canonical_suggestions_for_substrate(
    session: Session,
    *,
    stylebook_id: int,
    person: SubstratePerson,
    limit: int = 24,
) -> list[tuple[str, str]]:
    """Ordered ``(canonical_id, label)`` for UI: exact alias first, then ranked recall."""
    exact_cid = find_existing_person_canonical_id_by_alias(
        session,
        stylebook_id=stylebook_id,
        normalized_name=str(person.normalized_name),
    )
    ranked = rank_person_canonical_recall_matches(
        session,
        stylebook_id=stylebook_id,
        person=person,
        limit=limit,
    )
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    if exact_cid is not None:
        canon = session.get(StylebookPersonCanonical, str(exact_cid))
        if canon is not None and int(canon.stylebook_id) == int(stylebook_id):
            eid = str(exact_cid)
            out.append((eid, str(canon.label)))
            seen.add(eid)
    for cid, label in ranked:
        if cid in seen:
            continue
        out.append((cid, label))
        seen.add(cid)
        if len(out) >= limit:
            break
    return out[:limit]


def delete_canonical_alias_if_no_other_linked_substrate(
    session: Session,
    *,
    canonical_id: str,
    normalized_name: str,
    exclude_substrate_person_id: int,
) -> bool:
    norm = str(normalized_name).strip()
    if not norm:
        return False
    cnt_stmt = (
        select(func.count())
        .select_from(SubstratePerson)
        .where(
            col(SubstratePerson.stylebook_person_canonical_id) == str(canonical_id),
            SubstratePerson.normalized_name == norm,
            col(SubstratePerson.id) != int(exclude_substrate_person_id),
        )
    )
    other = int(session.scalar(cnt_stmt) or 0)
    if other > 0:
        return False
    alias = session.exec(
        select(StylebookPersonAlias).where(
            StylebookPersonAlias.person_canonical_id == str(canonical_id),
            StylebookPersonAlias.normalized_alias == norm,
            StylebookPersonAlias.suppressed.is_(False),
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
    person: SubstratePerson,
    provenance: str = "stylebook_ui_unlink",
    requeue_after_unlink: bool = True,
) -> None:
    if person.id is None:
        raise ValueError("person must be persisted")
    if str(person.canonical_link_status) != CANONICAL_LINK_LINKED:
        raise ValueError("person is not linked to a canonical")
    cid = person.stylebook_person_canonical_id
    if cid is None:
        raise ValueError("linked person missing stylebook_person_canonical_id")
    canon = session.get(StylebookPersonCanonical, str(cid))
    if canon is None or int(canon.stylebook_id) != int(stylebook_id):
        raise ValueError("canonical not in this stylebook")
    pid = int(person.id)
    old = str(cid)
    delete_canonical_alias_if_no_other_linked_substrate(
        session,
        canonical_id=old,
        normalized_name=str(person.normalized_name),
        exclude_substrate_person_id=pid,
    )
    person.stylebook_person_canonical_id = None
    person.canonical_link_status = (
        CANONICAL_LINK_PENDING if requeue_after_unlink else CANONICAL_LINK_UNLINKED
    )
    person.canonical_review_reasons_json = [
        {
            "code": "unlinked_from_canonical" if requeue_after_unlink else "removed_from_story",
            "previous_canonical_id": old,
            "provenance": provenance,
        }
    ]
    session.add(person)


def link_substrate_to_canonical_atomic(
    session: Session,
    *,
    stylebook_id: int,
    person: SubstratePerson,
    target_canonical_id: str,
    provenance: str = "stylebook_ui_link",
) -> bool:
    if person.id is None:
        raise ValueError("person must be persisted")
    tid = str(target_canonical_id)
    canon = session.get(StylebookPersonCanonical, tid)
    if canon is None or int(canon.stylebook_id) != int(stylebook_id):
        raise ValueError("target canonical not in this stylebook")
    pid = int(person.id)
    prev = person.stylebook_person_canonical_id
    prev_str = str(prev) if prev is not None else None
    st = str(person.canonical_link_status)
    if st not in (CANONICAL_LINK_PENDING, CANONICAL_LINK_LINKED):
        raise ValueError("person canonical_link_status does not allow manual link")
    if st == CANONICAL_LINK_PENDING and prev_str is not None:
        raise ValueError("invalid state: pending with non-null canonical FK")
    if prev_str == tid and st == CANONICAL_LINK_LINKED:
        return False

    if st == CANONICAL_LINK_PENDING:
        person.canonical_review_reasons_json = [
            {"code": "linked_to_canonical", "canonical_id": tid, "provenance": provenance}
        ]
    else:
        person.canonical_review_reasons_json = [
            {
                "code": "relinked_canonical",
                "from_canonical_id": prev_str,
                "to_canonical_id": tid,
                "provenance": provenance,
            }
        ]
    person.stylebook_person_canonical_id = tid
    person.canonical_link_status = CANONICAL_LINK_LINKED
    session.add(person)
    session.flush()
    refresh_aliases_for_linked_person(
        session,
        stylebook_id=stylebook_id,
        person=person,
        provenance=provenance,
    )
    if prev_str is not None and prev_str != tid:
        delete_canonical_alias_if_no_other_linked_substrate(
            session,
            canonical_id=prev_str,
            normalized_name=str(person.normalized_name),
            exclude_substrate_person_id=pid,
        )
    return True


def requeue_substrate_after_story_remove(
    session: Session,
    *,
    stylebook_id: int,
    person: SubstratePerson,
    provenance: str = "agate_review_delete",
) -> bool:
    if person.id is None:
        raise ValueError("person must be persisted")
    st = str(person.canonical_link_status or "")
    if st == CANONICAL_LINK_LINKED and person.stylebook_person_canonical_id is not None:
        unlink_substrate_from_canonical(
            session,
            stylebook_id=stylebook_id,
            person=person,
            provenance=provenance,
        )
        return True
    if st in (CANONICAL_LINK_WAIVED, CANONICAL_LINK_UNLINKED):
        person.canonical_link_status = CANONICAL_LINK_PENDING
        person.stylebook_person_canonical_id = None
        session.add(person)
        return True
    if st == CANONICAL_LINK_PENDING and person.stylebook_person_canonical_id is not None:
        person.stylebook_person_canonical_id = None
        session.add(person)
        return True
    return False
