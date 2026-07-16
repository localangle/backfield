"""Organization canonical persist policy: tier-1 identity, recall defer, materialize."""

from __future__ import annotations

from typing import Any

from backfield_db import StylebookOrganizationCanonical, SubstrateOrganization
from sqlmodel import Session, select

from backfield_entities.canonical.plan_types import (
    CanonicalPersistDecision,
    CanonicalPersistPlan,
)
from backfield_entities.entities.organization.recall import (
    ORGANIZATION_RECALL_DEFAULT_LIMIT,
    canonical_ids_from_organization_name_keys,
    retrieve_organization_canonical_candidates,
)
from backfield_entities.entities.organization.types import (
    normalize_organization_text,
    normalize_organization_type,
    organization_looks_like_acronym,
    organization_match_key,
    organization_tier1_identity_compatible,
    organization_types_are_link_compatible,
)

AMBIGUOUS_ORGANIZATION_CANONICAL_MATCH = "ambiguous_organization_canonical_match"
ORGANIZATION_CANONICAL_TYPE_MISMATCH = "organization_canonical_type_mismatch"
ORGANIZATION_MATERIALIZE_NEW_CODE = "materialized_new_canonical"


def organization_name_matches_canonical(
    organization: SubstrateOrganization,
    canon: StylebookOrganizationCanonical,
) -> bool:
    if not organization_match_key(organization.normalized_name or organization.name):
        return False
    return organization_match_key(canon.label) == organization_match_key(
        organization.normalized_name or organization.name
    )


def organization_type_matches_canonical(
    organization: SubstrateOrganization,
    canon: StylebookOrganizationCanonical,
) -> bool:
    org_type = normalize_organization_type(organization.organization_type)
    canon_type = normalize_organization_type(canon.organization_type)
    return org_type == canon_type


def organization_strong_identity_matches_canonical(
    organization: SubstrateOrganization,
    canon: StylebookOrganizationCanonical,
) -> bool:
    """Tier-1 auto-link: exact normalized label + organization_type."""
    name_ok = organization_name_matches_canonical(organization, canon)
    type_ok = organization_type_matches_canonical(organization, canon)
    return name_ok and type_ok


def find_existing_organization_canonical_id_by_alias(
    session: Session,
    *,
    stylebook_id: int,
    normalized_name: str,
) -> str | None:
    """Return canonical id when a non-suppressed alias matches ``normalized_name``."""
    matches = canonical_ids_from_organization_name_keys(
        session,
        stylebook_id=stylebook_id,
        name_or_norm=normalized_name,
        trusted_alias_only=True,
    )
    if not matches:
        return None
    return matches[0]


def _identity_name_norms(
    organization: SubstrateOrganization,
    *,
    extra_lookup_names: tuple[str, ...] = (),
) -> tuple[str, ...]:
    norms: list[str] = []
    seen: set[str] = set()
    for source in (organization.normalized_name or organization.name, *extra_lookup_names):
        norm = normalize_organization_text(source)
        if norm and norm not in seen:
            seen.add(norm)
            norms.append(norm)
    return tuple(norms)


def _strong_identity_canonical_ids(
    session: Session,
    *,
    stylebook_id: int,
    organization: SubstrateOrganization,
    extra_lookup_names: tuple[str, ...] = (),
) -> list[str]:
    name_norms = _identity_name_norms(organization, extra_lookup_names=extra_lookup_names)
    if not name_norms:
        return []
    matches: list[str] = []
    seen: set[str] = set()

    for name_norm in name_norms:
        for cid in canonical_ids_from_organization_name_keys(
            session,
            stylebook_id=stylebook_id,
            name_or_norm=name_norm,
            trusted_alias_only=True,
        ):
            canon = session.get(StylebookOrganizationCanonical, cid)
            if canon is None or canon.id is None:
                continue
            if not organization_type_matches_canonical(organization, canon):
                continue
            canon_label_norm = normalize_organization_text(canon.label)
            if not organization_tier1_identity_compatible(
                substrate_norm=name_norm,
                canonical_label_norm=canon_label_norm,
            ):
                continue
            if cid not in seen:
                seen.add(cid)
                matches.append(cid)

    label_stmt = select(StylebookOrganizationCanonical).where(
        StylebookOrganizationCanonical.stylebook_id == stylebook_id,
    )
    for canon in session.exec(label_stmt).all():
        if canon.id is None:
            continue
        label_norm = normalize_organization_text(canon.label)
        label_hit = label_norm in name_norms or organization_strong_identity_matches_canonical(
            organization, canon
        )
        if not label_hit:
            continue
        if not any(
            organization_tier1_identity_compatible(
                substrate_norm=name_norm,
                canonical_label_norm=label_norm,
            )
            for name_norm in name_norms
        ):
            continue
        if not organization_type_matches_canonical(organization, canon):
            continue
        cid = str(canon.id)
        if cid not in seen:
            seen.add(cid)
            matches.append(cid)
    return matches


def _alias_type_mismatch_adjudication_plan(
    session: Session,
    *,
    stylebook_id: int,
    organization: SubstrateOrganization,
) -> CanonicalPersistPlan | None:
    """Name hits a catalog alias but organization_type differs — defer for LLM link/create."""
    norm = normalize_organization_text(organization.normalized_name or organization.name)
    if not norm:
        return None
    type_aligned: list[str] = []
    type_mismatched: list[tuple[str, StylebookOrganizationCanonical]] = []
    for cid in canonical_ids_from_organization_name_keys(
        session,
        stylebook_id=stylebook_id,
        name_or_norm=norm,
        trusted_alias_only=True,
    ):
        canon = session.get(StylebookOrganizationCanonical, cid)
        if canon is None:
            continue
        if organization_type_matches_canonical(organization, canon):
            type_aligned.append(cid)
            continue
        type_mismatched.append((cid, canon))
    if type_aligned:
        return None
    if not type_mismatched:
        return None

    compatible_mismatches = [
        (cid, canon)
        for cid, canon in type_mismatched
        if organization_types_are_link_compatible(
            organization.organization_type,
            canon.organization_type,
        )
    ]
    incompatible_mismatches = [
        (cid, canon)
        for cid, canon in type_mismatched
        if not organization_types_are_link_compatible(
            organization.organization_type,
            canon.organization_type,
        )
    ]
    if len(compatible_mismatches) == 1 and not incompatible_mismatches:
        from backfield_entities.canonical.link_commit_gate import gate_or_coerce_link_plan

        cid, canon = compatible_mismatches[0]
        return gate_or_coerce_link_plan(
            session,
            CanonicalPersistPlan(
                decision=CanonicalPersistDecision.LINK_EXISTING,
                existing_canonical_id=cid,
                resolution_reasons=(
                    {
                        "code": "linked_exact_identity",
                        "canonical_id": cid,
                        "match_basis": "name_and_compatible_organization_type",
                        "substrate_type": normalize_organization_type(
                            organization.organization_type
                        ),
                        "canonical_type": normalize_organization_type(canon.organization_type),
                    },
                ),
            ),
            entity_type="organization",
            substrate_row=organization,
            stylebook_id=stylebook_id,
        )

    recall_ids = [cid for cid, _ in type_mismatched]
    cid, canon = type_mismatched[0]
    return CanonicalPersistPlan(
        decision=CanonicalPersistDecision.DEFER,
        resolution_reasons=(
            {
                "code": ORGANIZATION_CANONICAL_TYPE_MISMATCH,
                "canonical_id": cid,
                "recall_canonical_ids": recall_ids,
                "substrate_type": normalize_organization_type(organization.organization_type),
                "canonical_type": normalize_organization_type(canon.organization_type),
            },
        ),
    )


def rank_organization_canonical_recall_matches(
    session: Session,
    *,
    stylebook_id: int,
    organization: SubstrateOrganization,
    limit: int = ORGANIZATION_RECALL_DEFAULT_LIMIT,
) -> list[tuple[str, str]]:
    return retrieve_organization_canonical_candidates(
        session,
        stylebook_id=stylebook_id,
        organization=organization,
        limit=limit,
    )


def _ambiguous_organization_defer_plan(
    *,
    recall: list[tuple[str, str]],
    best_canonical_id: str | None = None,
) -> CanonicalPersistPlan:
    recall_ids = [cid for cid, _ in recall[:ORGANIZATION_RECALL_DEFAULT_LIMIT]]
    reason: dict[str, Any] = {
        "code": AMBIGUOUS_ORGANIZATION_CANONICAL_MATCH,
        "recall_canonical_ids": recall_ids,
    }
    if best_canonical_id is not None:
        reason["best_canonical_id"] = str(best_canonical_id)
    return CanonicalPersistPlan(
        decision=CanonicalPersistDecision.DEFER,
        resolution_reasons=(reason,),
    )


def plan_has_ambiguous_organization_canonical_match(plan: CanonicalPersistPlan) -> bool:
    for r in plan.resolution_reasons:
        code = str(r.get("code") or "") if isinstance(r, dict) else ""
        if code == AMBIGUOUS_ORGANIZATION_CANONICAL_MATCH:
            return True
    return False


def plan_has_organization_canonical_type_mismatch(plan: CanonicalPersistPlan) -> bool:
    for r in plan.resolution_reasons:
        code = str(r.get("code") or "") if isinstance(r, dict) else ""
        if code == ORGANIZATION_CANONICAL_TYPE_MISMATCH:
            return True
    return False


def plan_requires_llm_organization_canonical_adjudication(
    plan: CanonicalPersistPlan,
    organization: SubstrateOrganization,
) -> bool:
    _ = organization
    return plan_has_ambiguous_organization_canonical_match(
        plan
    ) or plan_has_organization_canonical_type_mismatch(plan)


def plan_is_materialize_new_canonical(plan: CanonicalPersistPlan) -> bool:
    if plan.decision != CanonicalPersistDecision.MATERIALIZE_NEW:
        return False
    for reason in plan.resolution_reasons:
        if not isinstance(reason, dict):
            continue
        if str(reason.get("code") or "") == ORGANIZATION_MATERIALIZE_NEW_CODE:
            return True
    return False


def plan_requires_llm_organization_name_variant_recall(
    plan: CanonicalPersistPlan,
    organization: SubstrateOrganization,
) -> bool:
    """True when LLM name variants may rescue a would-be duplicate canonical."""
    if not plan_is_materialize_new_canonical(plan):
        return False
    norm = normalize_organization_text(organization.normalized_name or organization.name)
    if not norm:
        return False
    return organization_looks_like_acronym(norm) or len(norm.split()) >= 2


def replan_organization_canonical_after_name_variants(
    session: Session,
    *,
    stylebook_id: int,
    organization: SubstrateOrganization,
    variant_names: tuple[str, ...],
    organizations_bucket: str = "ready",
    auto_apply_canonicalization: bool = False,
) -> CanonicalPersistPlan:
    """Re-run link/defer/materialize using LLM-suggested alternate names for recall."""
    cleaned = tuple(
        s
        for s in (str(v).strip() for v in variant_names)
        if s and normalize_organization_text(s)
    )
    plan = decide_organization_canonical_persist_plan(
        session,
        stylebook_id=stylebook_id,
        organization=organization,
        organizations_bucket=organizations_bucket,
        auto_apply_canonicalization=auto_apply_canonicalization,
        extra_lookup_names=cleaned,
    )
    if not cleaned:
        return plan
    extra: dict[str, Any] = {
        "code": "organization_name_variant_recall",
        "variant_names": list(cleaned),
        "outcome_plan": plan.decision.value,
    }
    return CanonicalPersistPlan(
        decision=plan.decision,
        existing_canonical_id=plan.existing_canonical_id,
        resolution_reasons=tuple(list(plan.resolution_reasons) + [extra]),
    )


def organization_may_materialize_canonical_after_recall(
    organization: SubstrateOrganization,
) -> bool:
    if not normalize_organization_text(organization.normalized_name or organization.name):
        return False
    return True


def decide_organization_canonical_persist_plan(
    session: Session,
    *,
    stylebook_id: int,
    organization: SubstrateOrganization,
    organizations_bucket: str = "ready",
    auto_apply_canonicalization: bool = False,
    extra_lookup_names: tuple[str, ...] = (),
) -> CanonicalPersistPlan:
    """Decide link, materialize, or defer for a substrate organization row."""
    _ = organizations_bucket
    _ = auto_apply_canonicalization

    type_mismatch = _alias_type_mismatch_adjudication_plan(
        session,
        stylebook_id=stylebook_id,
        organization=organization,
    )
    if type_mismatch is not None:
        return type_mismatch

    strong_matches = _strong_identity_canonical_ids(
        session,
        stylebook_id=stylebook_id,
        organization=organization,
        extra_lookup_names=extra_lookup_names,
    )
    if len(strong_matches) == 1:
        from backfield_entities.canonical.link_commit_gate import gate_or_coerce_link_plan

        cid = strong_matches[0]
        return gate_or_coerce_link_plan(
            session,
            CanonicalPersistPlan(
                decision=CanonicalPersistDecision.LINK_EXISTING,
                existing_canonical_id=cid,
                resolution_reasons=(
                    {
                        "code": "linked_exact_identity",
                        "canonical_id": cid,
                        "match_basis": "name_and_organization_type",
                    },
                ),
            ),
            entity_type="organization",
            substrate_row=organization,
            stylebook_id=stylebook_id,
        )
    if len(strong_matches) > 1:
        recall = [(cid, "") for cid in strong_matches]
        return _ambiguous_organization_defer_plan(
            recall=recall,
            best_canonical_id=strong_matches[0],
        )

    recall = retrieve_organization_canonical_candidates(
        session,
        stylebook_id=stylebook_id,
        organization=organization,
        limit=ORGANIZATION_RECALL_DEFAULT_LIMIT,
        extra_lookup_names=extra_lookup_names,
    )
    if not recall:
        return CanonicalPersistPlan(
            decision=CanonicalPersistDecision.MATERIALIZE_NEW,
            resolution_reasons=({"code": ORGANIZATION_MATERIALIZE_NEW_CODE},),
        )

    return _ambiguous_organization_defer_plan(recall=recall, best_canonical_id=recall[0][0])
