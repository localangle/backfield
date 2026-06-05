"""Person canonical + alias persistence and Stylebook link operations."""

from __future__ import annotations

import re
from typing import Any

from backfield_db import (
    StylebookPersonAlias,
    StylebookPersonCanonical,
    StylebookPersonMeta,
    SubstratePerson,
    SubstratePersonMention,
)
from sqlmodel import Session, col, func, select

from backfield_entities.canonical.link import (
    CANONICAL_LINK_LINKED,
    CANONICAL_LINK_PENDING,
    CANONICAL_LINK_UNLINKED,
    CANONICAL_LINK_WAIVED,
)
from backfield_entities.canonical.plan_types import CanonicalPersistDecision, CanonicalPersistPlan
from backfield_entities.entities.person.catalog_provenance import (
    is_person_catalog_editorial_provenance,
)
from backfield_entities.entities.person.policy import (
    find_existing_person_canonical_id_by_alias,
    plan_has_ambiguous_person_canonical_match,
    rank_person_canonical_recall_matches,
)
from backfield_entities.entities.person.review import (
    plan_includes_auto_waive_person_review,
    plan_includes_flag_person_review,
)
from backfield_entities.entities.person.types import (
    derive_person_sort_key,
    person_alias_lookup_keys,
)


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


def seed_aliases_for_canonical_label(
    session: Session,
    *,
    canon_id: str,
    label: str,
    provenance: str,
) -> None:
    """Upsert normalized alias variants from a canonical label (import / manual create)."""
    clean = label.strip()
    if not clean:
        return
    for norm in person_alias_lookup_keys(clean):
        upsert_alias_for_canonical_text(
            session,
            canon_id=canon_id,
            alias_text=clean,
            normalized_alias=norm,
            provenance=provenance,
        )


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
    alias_text = str(person.name)
    for norm in person_alias_lookup_keys(alias_text):
        upsert_alias_for_canonical_text(
            session,
            canon_id=canon_id,
            alias_text=alias_text,
            normalized_alias=norm,
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
    for norm in person_alias_lookup_keys(clean):
        upsert_alias_for_canonical_text(
            session,
            canon_id=cid,
            alias_text=clean,
            normalized_alias=norm,
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


def _linked_substrate_count_for_person_canonical(
    session: Session,
    *,
    canonical_id: str,
) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(SubstratePerson)
            .where(col(SubstratePerson.stylebook_person_canonical_id) == str(canonical_id))
        )
        or 0
    )


def _active_mention_count_for_person_canonical(
    session: Session,
    *,
    canonical_id: str,
) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(SubstratePersonMention)
            .join(SubstratePerson, SubstratePerson.id == SubstratePersonMention.person_id)
            .where(
                col(SubstratePerson.stylebook_person_canonical_id) == str(canonical_id),
                col(SubstratePersonMention.deleted).is_(False),
            )
        )
        or 0
    )


def person_canonical_has_editorial_catalog_provenance(
    session: Session,
    *,
    canonical_id: str,
) -> bool:
    """True when aliases or meta indicate manual/import catalog intent."""
    alias_rows = session.exec(
        select(StylebookPersonAlias.provenance).where(
            StylebookPersonAlias.person_canonical_id == str(canonical_id),
        )
    ).all()
    if any(is_person_catalog_editorial_provenance(str(p)) for p in alias_rows if p is not None):
        return True
    meta_count = int(
        session.scalar(
            select(func.count())
            .select_from(StylebookPersonMeta)
            .where(col(StylebookPersonMeta.stylebook_person_canonical_id) == str(canonical_id))
        )
        or 0
    )
    return meta_count > 0


def maybe_prune_ingest_orphan_person_canonical(
    session: Session,
    *,
    stylebook_id: int,
    canonical_id: str,
    removed_substrate_ingest_alias: bool = False,
) -> bool:
    """Delete ingest-only canonical rows left with no substrates or mentions.

    Manual, CSV, bundle, and review-queue catalog rows are protected via editorial
    alias provenance (``PERSON_CATALOG_EDITORIAL_PROVENANCES``). Legacy bundle rows
    without aliases are also kept unless an ingest alias was removed in this same
    unlink/dispose step.
    """
    cid = str(canonical_id)
    canon = session.get(StylebookPersonCanonical, cid)
    if canon is None or int(canon.stylebook_id) != int(stylebook_id):
        return False
    if person_canonical_has_editorial_catalog_provenance(session, canonical_id=cid):
        return False
    if _linked_substrate_count_for_person_canonical(session, canonical_id=cid) > 0:
        return False
    if _active_mention_count_for_person_canonical(session, canonical_id=cid) > 0:
        return False

    alias_rows = session.exec(
        select(StylebookPersonAlias).where(StylebookPersonAlias.person_canonical_id == cid)
    ).all()
    if alias_rows:
        if any(
            is_person_catalog_editorial_provenance(str(row.provenance)) for row in alias_rows
        ):
            return False
        session.delete(canon)
        return True

    if not removed_substrate_ingest_alias:
        return False

    session.delete(canon)
    return True


def delete_canonical_alias_if_no_other_linked_substrate(
    session: Session,
    *,
    canonical_id: str,
    normalized_name: str,
    exclude_substrate_person_id: int,
) -> str | None:
    """Remove a name alias when no other linked substrate shares it.

    Returns the deleted alias provenance, or ``None`` when no row was removed.
    """
    norm = str(normalized_name).strip()
    if not norm:
        return None
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
        return None
    alias = session.exec(
        select(StylebookPersonAlias).where(
            StylebookPersonAlias.person_canonical_id == str(canonical_id),
            StylebookPersonAlias.normalized_alias == norm,
            StylebookPersonAlias.suppressed.is_(False),
        )
    ).first()
    if alias is None:
        return None
    provenance = str(alias.provenance)
    session.delete(alias)
    return provenance


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
    removed_alias_provenance = delete_canonical_alias_if_no_other_linked_substrate(
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
    maybe_prune_ingest_orphan_person_canonical(
        session,
        stylebook_id=stylebook_id,
        canonical_id=old,
        removed_substrate_ingest_alias=removed_alias_provenance == "substrate_ingest",
    )


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
        removed_alias_provenance = delete_canonical_alias_if_no_other_linked_substrate(
            session,
            canonical_id=prev_str,
            normalized_name=str(person.normalized_name),
            exclude_substrate_person_id=pid,
        )
        maybe_prune_ingest_orphan_person_canonical(
            session,
            stylebook_id=stylebook_id,
            canonical_id=prev_str,
            removed_substrate_ingest_alias=removed_alias_provenance == "substrate_ingest",
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
