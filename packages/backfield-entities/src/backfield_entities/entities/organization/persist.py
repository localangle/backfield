"""Organization canonical + alias persistence and Stylebook link operations."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from backfield_db import (
    StylebookOrganizationAlias,
    StylebookOrganizationCanonical,
    StylebookOrganizationMeta,
    SubstrateOrganization,
    SubstrateOrganizationMention,
)
from sqlmodel import Session, col, func, select

from backfield_entities.activity import (
    EVENT_CANONICAL_CREATED,
    EVENT_SUBSTRATE_LINKED,
    log_stylebook_activity_safe,
)
from backfield_entities.canonical.link import (
    CANONICAL_LINK_LINKED,
    CANONICAL_LINK_PENDING,
    CANONICAL_LINK_UNLINKED,
    CANONICAL_LINK_WAIVED,
)
from backfield_entities.canonical.plan_types import CanonicalPersistDecision, CanonicalPersistPlan
from backfield_entities.canonical.slug import flush_new_canonical_with_slug_retry
from backfield_entities.entities.organization.catalog_provenance import (
    is_organization_catalog_editorial_provenance,
)
from backfield_entities.entities.organization.policy import (
    find_existing_organization_canonical_id_by_alias,
    plan_has_ambiguous_organization_canonical_match,
    plan_has_organization_canonical_type_mismatch,
    rank_organization_canonical_recall_matches,
)
from backfield_entities.entities.organization.types import (
    GENERATED_ACRONYM_PROVENANCE,
    normalize_organization_type,
    organization_alias_surface_form,
    organization_canonical_alias_entries,
)


def _organization_alias_provenance_strength(provenance: str) -> int:
    value = str(provenance or "").strip()
    if value == GENERATED_ACRONYM_PROVENANCE:
        return 0
    if value == "substrate_ingest":
        return 1
    if is_organization_catalog_editorial_provenance(value):
        return 3
    return 2


def _slugify_organization_label(label: str) -> str:
    s = label.lower().strip().replace(" ", "-")
    s = re.sub(r"[^a-z0-9-]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "organization"


def allocate_unique_organization_canonical_slug(
    session: Session,
    *,
    stylebook_id: int,
    label: str,
) -> str:
    base = _slugify_organization_label(label)
    slug = base
    n = 2
    while True:
        hit = session.exec(
            select(StylebookOrganizationCanonical.id).where(
                StylebookOrganizationCanonical.stylebook_id == stylebook_id,
                col(StylebookOrganizationCanonical.slug) == slug,
            )
        ).first()
        if hit is None:
            return slug
        slug = f"{base}-{n}"
        n += 1


def assert_canonical_link_invariant(organization: SubstrateOrganization) -> None:
    if organization.canonical_link_status == CANONICAL_LINK_LINKED:
        if organization.stylebook_organization_canonical_id is None:
            raise AssertionError(
                "canonical_link_status=linked requires stylebook_organization_canonical_id"
            )
    else:
        if organization.stylebook_organization_canonical_id is not None:
            raise AssertionError(
                f"canonical_link_status={organization.canonical_link_status!r} requires null "
                "stylebook_organization_canonical_id"
            )


def _mirror_fields_from_substrate(organization: SubstrateOrganization) -> dict[str, Any]:
    return {
        "organization_type": normalize_organization_type(organization.organization_type),
    }


def seed_aliases_for_canonical_label(
    session: Session,
    *,
    canon_id: str,
    label: str,
    provenance: str,
) -> None:
    clean = label.strip()
    if not clean:
        return
    for norm, generated_acronym in organization_canonical_alias_entries(clean):
        upsert_alias_for_canonical_text(
            session,
            canon_id=canon_id,
            alias_text=organization_alias_surface_form(clean, norm),
            normalized_alias=norm,
            provenance=GENERATED_ACRONYM_PROVENANCE if generated_acronym else provenance,
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
        select(StylebookOrganizationAlias).where(
            StylebookOrganizationAlias.organization_canonical_id == canon_id,
            StylebookOrganizationAlias.normalized_alias == norm,
        )
    ).first()
    if existing is None:
        session.add(
            StylebookOrganizationAlias(
                organization_canonical_id=canon_id,
                alias_text=str(alias_text),
                normalized_alias=norm,
                provenance=provenance,
                suppressed=False,
            )
        )
    else:
        if _organization_alias_provenance_strength(
            provenance
        ) < _organization_alias_provenance_strength(str(existing.provenance)):
            return
        existing.alias_text = str(alias_text)
        existing.provenance = provenance
        existing.suppressed = False
        session.add(existing)


def _upsert_alias_for_substrate(
    session: Session,
    *,
    canon_id: str,
    organization: SubstrateOrganization,
    provenance: str,
) -> None:
    alias_text = str(organization.name)
    for norm, generated_acronym in organization_canonical_alias_entries(alias_text):
        upsert_alias_for_canonical_text(
            session,
            canon_id=canon_id,
            alias_text=organization_alias_surface_form(alias_text, norm),
            normalized_alias=norm,
            provenance=GENERATED_ACRONYM_PROVENANCE if generated_acronym else provenance,
        )


def refresh_aliases_for_linked_organization(
    session: Session,
    *,
    stylebook_id: int,
    organization: SubstrateOrganization,
    provenance: str = "substrate_ingest",
) -> None:
    if organization.id is None or organization.stylebook_organization_canonical_id is None:
        return
    canon_id = str(organization.stylebook_organization_canonical_id)
    canon = session.get(StylebookOrganizationCanonical, canon_id)
    if canon is None or int(canon.stylebook_id) != int(stylebook_id):
        return
    _upsert_alias_for_substrate(
        session,
        canon_id=canon_id,
        organization=organization,
        provenance=provenance,
    )
    if canon.label:
        seed_aliases_for_canonical_label(
            session,
            canon_id=canon_id,
            label=str(canon.label),
            provenance=provenance,
        )


def link_to_existing_canonical(
    session: Session,
    *,
    stylebook_id: int,
    organization: SubstrateOrganization,
    canonical_id: str,
    provenance: str = "substrate_ingest",
    audit_reasons: list[dict[str, Any]] | None = None,
) -> None:
    if organization.id is None:
        return
    canon = session.get(StylebookOrganizationCanonical, canonical_id)
    if canon is None or int(canon.stylebook_id) != int(stylebook_id):
        return
    organization.stylebook_organization_canonical_id = str(canon.id)
    organization.canonical_link_status = CANONICAL_LINK_LINKED
    organization.canonical_review_reasons_json = (
        [dict(r) for r in audit_reasons] if audit_reasons is not None else None
    )
    session.add(organization)
    session.flush()
    _upsert_alias_for_substrate(
        session,
        canon_id=str(canon.id),
        organization=organization,
        provenance=provenance,
    )


def create_standalone_canonical(
    session: Session,
    *,
    stylebook_id: int,
    label: str,
    organization_type: str | None = None,
    provenance: str = "stylebook_ui_manual",
) -> StylebookOrganizationCanonical:
    clean = label.strip()
    if not clean:
        raise ValueError("label is required")
    def _build_row(slug: str) -> StylebookOrganizationCanonical:
        return StylebookOrganizationCanonical(
            stylebook_id=stylebook_id,
            label=clean,
            slug=slug,
            organization_type=normalize_organization_type(organization_type),
            primary_substrate_organization_id=None,
            status="active",
        )

    canon = flush_new_canonical_with_slug_retry(
        session,
        stylebook_id=stylebook_id,
        label=clean,
        allocate_slug=lambda sess, sb_id, lbl: allocate_unique_organization_canonical_slug(
            sess, stylebook_id=sb_id, label=lbl
        ),
        build_row=_build_row,
    )
    cid = str(canon.id)
    for norm, generated_acronym in organization_canonical_alias_entries(clean):
        upsert_alias_for_canonical_text(
            session,
            canon_id=cid,
            alias_text=organization_alias_surface_form(clean, norm),
            normalized_alias=norm,
            provenance=GENERATED_ACRONYM_PROVENANCE if generated_acronym else provenance,
        )
    session.flush()
    return canon


def materialize_new_canonical_and_link(
    session: Session,
    *,
    stylebook_id: int,
    organization: SubstrateOrganization,
    label: str | None = None,
    provenance: str = "substrate_ingest",
    audit_reasons: list[dict[str, Any]] | None = None,
) -> None:
    if organization.id is None:
        return
    clean = (label or organization.name or "").strip()
    if not clean:
        return
    fields = _mirror_fields_from_substrate(organization)

    def _build_row(slug: str) -> StylebookOrganizationCanonical:
        return StylebookOrganizationCanonical(
            stylebook_id=stylebook_id,
            label=clean,
            slug=slug,
            primary_substrate_organization_id=None,
            status="active",
            **fields,
        )

    canon = flush_new_canonical_with_slug_retry(
        session,
        stylebook_id=stylebook_id,
        label=clean,
        allocate_slug=lambda sess, sb_id, lbl: allocate_unique_organization_canonical_slug(
            sess, stylebook_id=sb_id, label=lbl
        ),
        build_row=_build_row,
    )
    cid = str(canon.id)
    organization.stylebook_organization_canonical_id = cid
    organization.canonical_link_status = CANONICAL_LINK_LINKED
    organization.canonical_review_reasons_json = (
        [dict(r) for r in audit_reasons] if audit_reasons is not None else None
    )
    session.add(organization)
    session.flush()
    _upsert_alias_for_substrate(
        session,
        canon_id=cid,
        organization=organization,
        provenance=provenance,
    )


def _adjudication_item_from_plan(plan: CanonicalPersistPlan) -> dict[str, Any] | None:
    for r in plan.resolution_reasons:
        if isinstance(r, dict) and str(r.get("code") or "") == "canonical_adjudication":
            return dict(r)
    return None


def _canonical_suggestion_from_adjudication(
    adj: dict[str, Any],
    *,
    source: str = "canonical_adjudication",
) -> dict[str, Any] | None:
    outcome = str(adj.get("outcome") or "").strip()
    src = str(adj.get("source") or source)
    if outcome == "link_existing":
        cid = adj.get("canonical_id")
        if cid is not None and str(cid).strip():
            return {
                "code": "canonical_suggestion",
                "source": src,
                "suggested_action": "link_existing",
                "stylebook_organization_canonical_id": str(cid).strip(),
            }
    if outcome == "no_high_confidence_link":
        return {
            "code": "canonical_suggestion",
            "source": src,
            "suggested_action": "materialize_new",
        }
    return None


def _canonical_suggestion_from_plan(plan: CanonicalPersistPlan) -> dict[str, Any] | None:
    adj = _adjudication_item_from_plan(plan)
    if adj is not None:
        from_adj = _canonical_suggestion_from_adjudication(adj)
        if from_adj is not None:
            return from_adj

    ambiguous = plan_has_ambiguous_organization_canonical_match(plan)
    type_mismatch = plan_has_organization_canonical_type_mismatch(plan)
    if plan.decision == CanonicalPersistDecision.DEFER and adj is None:
        if ambiguous or type_mismatch:
            return None
    if (
        plan.decision == CanonicalPersistDecision.LINK_EXISTING
        and plan.existing_canonical_id is not None
    ):
        return {
            "code": "canonical_suggestion",
            "source": "rules_plan",
            "suggested_action": "link_existing",
            "stylebook_organization_canonical_id": str(plan.existing_canonical_id),
        }
    if plan.decision == CanonicalPersistDecision.MATERIALIZE_NEW:
        return {
            "code": "canonical_suggestion",
            "source": "rules_plan",
            "suggested_action": "materialize_new",
        }
    if plan.decision == CanonicalPersistDecision.DEFER:
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
    organization: SubstrateOrganization,
    plan: CanonicalPersistPlan,
    organizations_bucket: str,
) -> None:
    _ = stylebook_id
    _ = organizations_bucket
    reasons: list[dict[str, Any]] = [dict(r) for r in plan.resolution_reasons]
    has_suggestion = any(
        isinstance(r, dict) and str(r.get("code") or "") == "canonical_suggestion" for r in reasons
    )
    extra = _canonical_suggestion_from_plan(plan)
    if extra is not None and not has_suggestion:
        reasons.append(extra)
    organization.stylebook_organization_canonical_id = None
    organization.canonical_link_status = CANONICAL_LINK_PENDING
    organization.canonical_review_reasons_json = reasons
    session.add(organization)


CANDIDATE_AI_REVIEW_SOURCE = "candidate_ai_review"


def apply_candidate_ai_review_recommendation(
    session: Session,
    *,
    organization: SubstrateOrganization,
    plan: CanonicalPersistPlan,
) -> bool:
    if str(organization.canonical_link_status) != CANONICAL_LINK_PENDING:
        return False
    if organization.stylebook_organization_canonical_id is not None:
        return False
    raw = organization.canonical_review_reasons_json
    reasons: list[dict[str, Any]] = []
    if isinstance(raw, list):
        reasons = [dict(r) for r in raw if isinstance(r, dict)]
    elif isinstance(raw, dict):
        reasons = [dict(raw)]
    reasons = [
        r
        for r in reasons
        if str(r.get("code") or "") not in ("canonical_suggestion", "canonical_adjudication")
    ]
    for r in plan.resolution_reasons:
        if isinstance(r, dict):
            reasons.append(dict(r))
    extra = _canonical_suggestion_from_plan(plan)
    has_suggestion = False
    if extra is not None:
        suggestion = dict(extra)
        suggestion["source"] = CANDIDATE_AI_REVIEW_SOURCE
        reasons.append(suggestion)
        has_suggestion = True
    organization.canonical_review_reasons_json = reasons
    session.add(organization)
    return has_suggestion


def apply_canonical_persist_plan(
    session: Session,
    *,
    stylebook_id: int,
    organization: SubstrateOrganization,
    plan: CanonicalPersistPlan,
    organizations_bucket: str,
    provenance: str = "substrate_ingest",
    auto_apply_canonicalization: bool = False,
) -> None:
    _ = organizations_bucket
    _ = auto_apply_canonicalization
    reasons = [dict(r) for r in plan.resolution_reasons]
    has_suggestion = any(
        isinstance(r, dict) and str(r.get("code") or "") == "canonical_suggestion" for r in reasons
    )
    extra = _canonical_suggestion_from_plan(plan)
    if extra is not None and not has_suggestion:
        reasons.append(extra)
    if plan.decision == CanonicalPersistDecision.DEFER:
        organization.stylebook_organization_canonical_id = None
        organization.canonical_link_status = CANONICAL_LINK_PENDING
        organization.canonical_review_reasons_json = reasons
        session.add(organization)
        return
    if plan.decision == CanonicalPersistDecision.LINK_EXISTING:
        if plan.existing_canonical_id is None:
            return
        if provenance == "substrate_ingest":
            from backfield_entities.canonical.link_commit_gate import gate_or_coerce_link_plan

            gated = gate_or_coerce_link_plan(
                session,
                plan,
                entity_type="organization",
                substrate_row=organization,
                stylebook_id=stylebook_id,
            )
            if gated.decision != CanonicalPersistDecision.LINK_EXISTING:
                apply_canonical_persist_plan(
                    session,
                    stylebook_id=stylebook_id,
                    organization=organization,
                    plan=gated,
                    organizations_bucket=organizations_bucket,
                    provenance=provenance,
                    auto_apply_canonicalization=auto_apply_canonicalization,
                )
                return
        link_to_existing_canonical(
            session,
            stylebook_id=stylebook_id,
            organization=organization,
            canonical_id=str(plan.existing_canonical_id),
            provenance=provenance,
            audit_reasons=reasons,
        )
        log_stylebook_activity_safe(
            session,
            stylebook_id=stylebook_id,
            project_id=int(organization.project_id),
            actor_type="system",
            source="ingest_pipeline",
            event_type=EVENT_SUBSTRATE_LINKED,
            entity_type="organization",
            entity_id=str(organization.id) if organization.id is not None else None,
            entity_label=str(organization.name),
            related_entity_type="organization",
            related_entity_id=str(plan.existing_canonical_id),
            payload_json={"provenance": provenance},
        )
        return
    materialize_new_canonical_and_link(
        session,
        stylebook_id=stylebook_id,
        organization=organization,
        provenance=provenance,
        audit_reasons=reasons,
    )
    log_stylebook_activity_safe(
        session,
        stylebook_id=stylebook_id,
        project_id=int(organization.project_id),
        actor_type="system",
        source="ingest_pipeline",
        event_type=EVENT_CANONICAL_CREATED,
        entity_type="organization",
        entity_id=str(organization.stylebook_organization_canonical_id)
        if organization.stylebook_organization_canonical_id is not None
        else None,
        entity_label=str(organization.name),
        related_entity_type="organization",
        related_entity_id=str(organization.id) if organization.id is not None else None,
        payload_json={"provenance": provenance, "materialized_from_substrate": True},
    )


def rank_canonical_suggestions_for_substrate(
    session: Session,
    *,
    stylebook_id: int,
    organization: SubstrateOrganization,
    limit: int = 24,
) -> list[tuple[str, str]]:
    exact_cid = find_existing_organization_canonical_id_by_alias(
        session,
        stylebook_id=stylebook_id,
        normalized_name=str(organization.normalized_name),
    )
    ranked = rank_organization_canonical_recall_matches(
        session,
        stylebook_id=stylebook_id,
        organization=organization,
        limit=limit,
    )
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    if exact_cid is not None:
        canon = session.get(StylebookOrganizationCanonical, str(exact_cid))
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


def organization_canonical_to_export_dict(c: StylebookOrganizationCanonical) -> dict[str, Any]:
    created_at: datetime | None = c.created_at
    updated_at: datetime | None = c.updated_at

    def _iso_utc(dt: datetime | None) -> str | None:
        if dt is None:
            return None
        return dt.isoformat()

    return {
        "id": str(c.id),
        "label": c.label,
        "slug": c.slug,
        "organization_type": c.organization_type,
        "primary_substrate_organization_id": None,
        "status": c.status,
        "created_at": _iso_utc(created_at),
        "updated_at": _iso_utc(updated_at),
    }


def _linked_substrate_count_for_organization_canonical(
    session: Session,
    *,
    canonical_id: str,
) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(SubstrateOrganization)
            .where(
                col(SubstrateOrganization.stylebook_organization_canonical_id) == str(canonical_id)
            )
        )
        or 0
    )


def _active_mention_count_for_organization_canonical(
    session: Session,
    *,
    canonical_id: str,
) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(SubstrateOrganizationMention)
            .join(
                SubstrateOrganization,
                SubstrateOrganization.id == SubstrateOrganizationMention.organization_id,
            )
            .where(
                col(SubstrateOrganization.stylebook_organization_canonical_id) == str(canonical_id),
                col(SubstrateOrganizationMention.deleted).is_(False),
            )
        )
        or 0
    )


def organization_canonical_has_editorial_catalog_provenance(
    session: Session,
    *,
    canonical_id: str,
) -> bool:
    alias_rows = session.exec(
        select(StylebookOrganizationAlias.provenance).where(
            StylebookOrganizationAlias.organization_canonical_id == str(canonical_id),
        )
    ).all()
    if any(
        is_organization_catalog_editorial_provenance(str(p)) for p in alias_rows if p is not None
    ):
        return True
    meta_count = int(
        session.scalar(
            select(func.count())
            .select_from(StylebookOrganizationMeta)
            .where(
                col(StylebookOrganizationMeta.stylebook_organization_canonical_id)
                == str(canonical_id)
            )
        )
        or 0
    )
    return meta_count > 0


def maybe_prune_ingest_orphan_organization_canonical(
    session: Session,
    *,
    stylebook_id: int,
    canonical_id: str,
    removed_substrate_ingest_alias: bool = False,
) -> bool:
    cid = str(canonical_id)
    canon = session.get(StylebookOrganizationCanonical, cid)
    if canon is None or int(canon.stylebook_id) != int(stylebook_id):
        return False
    if organization_canonical_has_editorial_catalog_provenance(session, canonical_id=cid):
        return False
    if _linked_substrate_count_for_organization_canonical(session, canonical_id=cid) > 0:
        return False
    if _active_mention_count_for_organization_canonical(session, canonical_id=cid) > 0:
        return False

    alias_rows = session.exec(
        select(StylebookOrganizationAlias).where(
            StylebookOrganizationAlias.organization_canonical_id == cid
        )
    ).all()
    if alias_rows:
        if any(
            is_organization_catalog_editorial_provenance(str(row.provenance)) for row in alias_rows
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
    exclude_substrate_organization_id: int,
) -> str | None:
    norm = str(normalized_name).strip()
    if not norm:
        return None
    other = int(
        session.scalar(
            select(func.count())
            .select_from(SubstrateOrganization)
            .where(
                col(SubstrateOrganization.stylebook_organization_canonical_id) == str(canonical_id),
                SubstrateOrganization.normalized_name == norm,
                col(SubstrateOrganization.id) != int(exclude_substrate_organization_id),
            )
        )
        or 0
    )
    if other > 0:
        return None
    alias = session.exec(
        select(StylebookOrganizationAlias).where(
            StylebookOrganizationAlias.organization_canonical_id == str(canonical_id),
            StylebookOrganizationAlias.normalized_alias == norm,
            StylebookOrganizationAlias.suppressed.is_(False),
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
    organization: SubstrateOrganization,
    provenance: str = "stylebook_ui_unlink",
    requeue_after_unlink: bool = True,
) -> None:
    if organization.id is None:
        raise ValueError("organization must be persisted")
    if str(organization.canonical_link_status) != CANONICAL_LINK_LINKED:
        raise ValueError("organization is not linked to a canonical")
    cid = organization.stylebook_organization_canonical_id
    if cid is None:
        raise ValueError("linked organization missing stylebook_organization_canonical_id")
    canon = session.get(StylebookOrganizationCanonical, str(cid))
    if canon is None or int(canon.stylebook_id) != int(stylebook_id):
        raise ValueError("canonical not in this stylebook")
    oid = int(organization.id)
    old = str(cid)
    removed_alias_provenance = delete_canonical_alias_if_no_other_linked_substrate(
        session,
        canonical_id=old,
        normalized_name=str(organization.normalized_name),
        exclude_substrate_organization_id=oid,
    )
    organization.stylebook_organization_canonical_id = None
    organization.canonical_link_status = (
        CANONICAL_LINK_PENDING if requeue_after_unlink else CANONICAL_LINK_UNLINKED
    )
    organization.canonical_review_reasons_json = [
        {
            "code": "unlinked_from_canonical" if requeue_after_unlink else "removed_from_story",
            "previous_canonical_id": old,
            "provenance": provenance,
        }
    ]
    session.add(organization)
    maybe_prune_ingest_orphan_organization_canonical(
        session,
        stylebook_id=stylebook_id,
        canonical_id=old,
        removed_substrate_ingest_alias=removed_alias_provenance == "substrate_ingest",
    )


def requeue_substrate_after_story_remove(
    session: Session,
    *,
    stylebook_id: int,
    organization: SubstrateOrganization,
    provenance: str = "agate_review_delete",
) -> bool:
    if organization.id is None:
        raise ValueError("organization must be persisted")
    st = str(organization.canonical_link_status or "")
    if st == CANONICAL_LINK_LINKED and organization.stylebook_organization_canonical_id is not None:
        unlink_substrate_from_canonical(
            session,
            stylebook_id=stylebook_id,
            organization=organization,
            provenance=provenance,
        )
        return True
    if st in (CANONICAL_LINK_WAIVED, CANONICAL_LINK_UNLINKED):
        organization.canonical_link_status = CANONICAL_LINK_PENDING
        organization.stylebook_organization_canonical_id = None
        session.add(organization)
        return True
    if (
        st == CANONICAL_LINK_PENDING
        and organization.stylebook_organization_canonical_id is not None
    ):
        organization.stylebook_organization_canonical_id = None
        session.add(organization)
        return True
    return False


def link_substrate_to_canonical_atomic(
    session: Session,
    *,
    stylebook_id: int,
    organization: SubstrateOrganization,
    target_canonical_id: str,
    provenance: str = "stylebook_ui_link",
) -> bool:
    if organization.id is None:
        raise ValueError("organization must be persisted")
    tid = str(target_canonical_id)
    canon = session.get(StylebookOrganizationCanonical, tid)
    if canon is None or int(canon.stylebook_id) != int(stylebook_id):
        raise ValueError("target canonical not in this stylebook")
    oid = int(organization.id)
    prev = organization.stylebook_organization_canonical_id
    prev_str = str(prev) if prev is not None else None
    st = str(organization.canonical_link_status)
    if st not in (CANONICAL_LINK_PENDING, CANONICAL_LINK_LINKED, CANONICAL_LINK_WAIVED):
        raise ValueError("organization canonical_link_status does not allow manual link")
    if st in (CANONICAL_LINK_PENDING, CANONICAL_LINK_WAIVED) and prev_str is not None:
        raise ValueError("invalid state: pending with non-null canonical FK")
    if prev_str == tid and st == CANONICAL_LINK_LINKED:
        return False

    if st in (CANONICAL_LINK_PENDING, CANONICAL_LINK_WAIVED):
        organization.canonical_review_reasons_json = [
            {"code": "linked_to_canonical", "canonical_id": tid, "provenance": provenance}
        ]
    else:
        organization.canonical_review_reasons_json = [
            {
                "code": "relinked_canonical",
                "from_canonical_id": prev_str,
                "to_canonical_id": tid,
                "provenance": provenance,
            }
        ]
    organization.stylebook_organization_canonical_id = tid
    organization.canonical_link_status = CANONICAL_LINK_LINKED
    session.add(organization)
    session.flush()
    refresh_aliases_for_linked_organization(
        session,
        stylebook_id=stylebook_id,
        organization=organization,
        provenance=provenance,
    )
    if prev_str is not None and prev_str != tid:
        removed_alias_provenance = delete_canonical_alias_if_no_other_linked_substrate(
            session,
            canonical_id=prev_str,
            normalized_name=str(organization.normalized_name),
            exclude_substrate_organization_id=oid,
        )
        maybe_prune_ingest_orphan_organization_canonical(
            session,
            stylebook_id=stylebook_id,
            canonical_id=prev_str,
            removed_substrate_ingest_alias=removed_alias_provenance == "substrate_ingest",
        )
    return True
