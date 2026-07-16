"""LLM adjudication and name-variant recall for organization canonical matches."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from agate_utils.llm import call_llm
from backfield_db import (
    StylebookOrganizationAlias,
    StylebookOrganizationCanonical,
    SubstrateOrganization,
)
from backfield_entities.canonical.link_commit_gate import gate_or_coerce_link_plan
from backfield_entities.canonical.plan_types import (
    ADJUDICATION_COMPATIBLE_TYPE_LINK_MIN_CONFIDENCE,
    ADJUDICATION_LINK_MIN_CONFIDENCE,
    CanonicalPersistDecision,
    CanonicalPersistPlan,
)
from backfield_entities.entities.organization.policy import (
    AMBIGUOUS_ORGANIZATION_CANONICAL_MATCH,
    ORGANIZATION_CANONICAL_TYPE_MISMATCH,
    organization_may_materialize_canonical_after_recall,
    plan_has_organization_canonical_type_mismatch,
    plan_is_materialize_new_canonical,
    replan_organization_canonical_after_name_variants,
)
from backfield_entities.entities.organization.types import (
    multiword_organization_names_share_ambiguous_acronym,
    normalize_organization_text,
    normalize_organization_type,
    organization_types_are_link_compatible,
)
from sqlmodel import Session, select

from worker.substrate.canonical.llm_call_policy import (
    ADJUDICATION_LLM_MAX_RETRIES,
    ADJUDICATION_LLM_TIMEOUT_S,
)


@dataclass(frozen=True)
class OrganizationAdjudicationPrepared:
    organization: SubstrateOrganization
    model: str
    model_config_id: str | None
    candidates: tuple[tuple[str, str, str | None, tuple[str, ...]], ...]
    prompt: str


def _recall_context_for_adjudication(plan: CanonicalPersistPlan) -> dict[str, Any] | None:
    for r in plan.resolution_reasons:
        if not isinstance(r, dict):
            continue
        code = str(r.get("code") or "")
        if code == AMBIGUOUS_ORGANIZATION_CANONICAL_MATCH:
            ids = r.get("recall_canonical_ids")
            if isinstance(ids, list) and ids:
                return r
        if code == ORGANIZATION_CANONICAL_TYPE_MISMATCH:
            ids = r.get("recall_canonical_ids")
            if isinstance(ids, list) and ids:
                return r
            cid = r.get("canonical_id")
            if cid is not None and str(cid).strip():
                merged = dict(r)
                merged["recall_canonical_ids"] = [str(cid).strip()]
                return merged
    return None


def _alias_texts_for_canonical(
    session: Session,
    *,
    canon_id: str,
    limit: int = 8,
) -> list[str]:
    rows = session.exec(
        select(StylebookOrganizationAlias.alias_text).where(
            StylebookOrganizationAlias.organization_canonical_id == canon_id,
            StylebookOrganizationAlias.suppressed.is_(False),
        )
    ).all()
    out: list[str] = []
    seen: set[str] = set()
    for alias_text in rows:
        clean = str(alias_text or "").strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        out.append(clean)
        if len(out) >= limit:
            break
    return out


def _candidate_rows(
    session: Session,
    *,
    stylebook_id: int,
    canonical_ids: list[str],
) -> list[tuple[str, str, str | None, list[str]]]:
    if not canonical_ids:
        return []
    rows = session.exec(
        select(StylebookOrganizationCanonical).where(
            StylebookOrganizationCanonical.stylebook_id == stylebook_id,
            StylebookOrganizationCanonical.id.in_(canonical_ids[:24]),
        )
    ).all()
    out: list[tuple[str, str, str | None, list[str]]] = []
    for c in rows:
        if c.id is None:
            continue
        cid = str(c.id)
        out.append(
            (
                cid,
                str(c.label),
                (c.organization_type or "").strip() or None,
                _alias_texts_for_canonical(session, canon_id=cid),
            )
        )
    return out


def _canonical_ids_from_recall(plan: CanonicalPersistPlan) -> list[str]:
    ctx = _recall_context_for_adjudication(plan)
    if ctx is None:
        return []
    raw_ids = ctx.get("recall_canonical_ids")
    if not isinstance(raw_ids, list) or not raw_ids:
        return []
    cids: list[str] = []
    for x in raw_ids:
        if x is None:
            continue
        s = str(x).strip()
        if s:
            cids.append(s)
    return cids


def llm_suggest_organization_name_variants(
    *,
    name: str,
    normalized_name: str,
    organization_type: str | None,
    model: str,
    model_config_id: str | None = None,
) -> tuple[str, ...]:
    """Return 0-2 alternate conventional names (acronym or expanded form) for recall."""
    org_type = (organization_type or "").strip() or "other"
    prompt = (
        "You help match news-article organization mentions to a Stylebook catalog.\n\n"
        f"Substrate name: {name!r}\n"
        f"Normalized name: {normalized_name!r}\n"
        f"Organization type: {org_type!r}\n\n"
        "Return JSON only: variant_names (array of 0-2 strings).\n"
        "Each variant must denote the SAME real-world institution as the substrate row, "
        "given the organization type (e.g. acronym ↔ expanded form).\n"
        "Examples: CPS + school_district → Chicago Public Schools; "
        "CPS + government agency context → Child Protective Services only when type fits.\n"
        "Return an empty array when no confident alternate conventional name exists, "
        "or when the acronym is ambiguous without stronger story context than type alone."
    )
    try:
        raw = call_llm(
            prompt,
            model=model,
            force_json=True,
            temperature=0.0,
            max_retries=ADJUDICATION_LLM_MAX_RETRIES,
            timeout=ADJUDICATION_LLM_TIMEOUT_S,
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            model_config_id=model_config_id,
        )
        data = json.loads(raw)
    except Exception:
        return ()
    if not isinstance(data, dict):
        return ()
    raw_names = data.get("variant_names")
    if not isinstance(raw_names, list):
        return ()
    out: list[str] = []
    seen: set[str] = set()
    for item in raw_names[:2]:
        clean = str(item or "").strip()
        if not clean:
            continue
        key = clean.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(clean)
    return tuple(out)


def enrich_materialize_plan_with_name_variant_recall(
    session: Session,
    *,
    plan: CanonicalPersistPlan,
    organization: SubstrateOrganization,
    stylebook_id: int,
    model: str,
    model_config_id: str | None = None,
    organizations_bucket: str = "ready",
    auto_apply_canonicalization: bool = False,
) -> CanonicalPersistPlan:
    """When policy would materialize, try LLM-suggested name variants before creating a row."""
    if not plan_is_materialize_new_canonical(plan):
        return plan
    variants = llm_suggest_organization_name_variants(
        name=str(organization.name),
        normalized_name=str(organization.normalized_name),
        organization_type=organization.organization_type,
        model=model,
        model_config_id=model_config_id,
    )
    if not variants:
        return plan
    return replan_organization_canonical_after_name_variants(
        session,
        stylebook_id=stylebook_id,
        organization=organization,
        variant_names=variants,
        organizations_bucket=organizations_bucket,
        auto_apply_canonicalization=auto_apply_canonicalization,
    )


def prepare_organization_adjudication(
    session: Session,
    *,
    plan: CanonicalPersistPlan,
    organization: SubstrateOrganization,
    stylebook_id: int,
    model: str,
    model_config_id: str | None = None,
) -> OrganizationAdjudicationPrepared | None:
    cids = _canonical_ids_from_recall(plan)
    if not cids:
        return None
    candidates = _candidate_rows(session, stylebook_id=stylebook_id, canonical_ids=cids)
    if not candidates:
        return None

    lines = "\n".join(
        f"- id={cid} label={label!r} organization_type={org_type!r} aliases={aliases!r}"
        for cid, label, org_type, aliases in candidates
    )
    floor = ADJUDICATION_LINK_MIN_CONFIDENCE
    type_mismatch = plan_has_organization_canonical_type_mismatch(plan)
    if type_mismatch:
        type_rules = (
            "- The substrate row matched a catalog alias but organization_type differed.\n"
            "- When the name or alias match is exact and types differ only within editorially "
            "compatible pairs, link with high confidence — these are labeling differences, not "
            "different institutions. Examples: local_business vs company for a named shop or "
            "brewery; nonprofit vs community_group for the same named group; "
            "financial_institution vs company for a named bank.\n"
            "- Compatible pairs include company↔local_business, nonprofit↔community_group, "
            "financial_institution↔company, media↔company.\n"
            f"- Use confidence {floor} or higher when name/alias match and types are compatible.\n"
            "- Set canonical_id to null only when types indicate genuinely different entities "
            "with a similar name (e.g. sports_team vs government, school_district vs "
            "public_services), or when uncertain.\n"
        )
    else:
        type_rules = (
            "- organization_type must agree; do not link across types even when names or aliases "
            "look similar.\n"
        )
    prompt = (
        "You decide whether exactly ONE canonical row denotes the SAME real-world organization "
        "as the substrate row (editorial identity in a news catalog), not a namesake.\n\n"
        f"Substrate name: {organization.name!r}\n"
        f"Normalized name: {organization.normalized_name!r}\n"
        f"Organization type: {(organization.organization_type or '')!r}\n\n"
        "Candidates (at most one id may be chosen):\n"
        f"{lines}\n\n"
        "Rules:\n"
        "- Set canonical_id only when the candidate is the SAME institution the substrate row "
        "represents (same organization despite minor spelling variants).\n"
        "- Well-known acronyms and their expanded forms may denote the same institution when "
        "organization_type aligns (e.g. NBA / National Basketball Association). "
        "The same acronym can denote different institutions by type "
        "(e.g. CPS as school_district vs public_services / child protective).\n"
        f"{type_rules}"
        "- Set canonical_id to null when organization type, role, or context indicates a "
        "different entity with a similar name, or when you are not certain.\n"
        "- Prefer null (human review) over a stretched link between namesakes.\n"
        "- Different sports teams with similar shorthand (e.g. Colorado Rockies vs "
        "Cincinnati Reds) are never the same organization even when both are "
        "sports_team.\n"
        f"- Use confidence {floor} or higher only for definitive same-organization identity; "
        f"otherwise use confidence below {floor} (the system will not auto-link).\n\n"
        "Return JSON only: canonical_id (UUID string matching one candidate id, or null), "
        "confidence (0.0-1.0), rationale (short string)."
    )
    return OrganizationAdjudicationPrepared(
        organization=organization,
        model=model,
        model_config_id=model_config_id,
        candidates=tuple(
            (cid, label, org_type, tuple(aliases))
            for cid, label, org_type, aliases in candidates
        ),
        prompt=prompt,
    )


def run_organization_adjudication_llm(
    prepared: OrganizationAdjudicationPrepared,
) -> dict[str, Any] | None:
    try:
        raw = call_llm(
            prepared.prompt,
            model=prepared.model,
            force_json=True,
            temperature=0.0,
            max_retries=ADJUDICATION_LLM_MAX_RETRIES,
            timeout=ADJUDICATION_LLM_TIMEOUT_S,
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            model_config_id=prepared.model_config_id,
        )
        data = json.loads(raw)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    return data


def _organization_type_matches_candidate(
    organization: SubstrateOrganization,
    *,
    canon_organization_type: str | None,
) -> bool:
    org_type = normalize_organization_type(organization.organization_type)
    canon_type = normalize_organization_type(canon_organization_type)
    return org_type == canon_type


def resolve_organization_adjudication_plan(
    plan: CanonicalPersistPlan,
    *,
    prepared: OrganizationAdjudicationPrepared,
    llm_data: dict[str, Any] | None,
    session: Session | None = None,
    stylebook_id: int | None = None,
) -> CanonicalPersistPlan:
    if llm_data is None:
        return plan

    organization = prepared.organization
    candidates = prepared.candidates
    model = prepared.model
    candidates_by_id = {str(c[0]): c for c in candidates}

    cid_raw = llm_data.get("canonical_id")
    conf_raw = llm_data.get("confidence", 0.0)
    rationale = str(llm_data.get("rationale") or "").strip()
    chosen: str | None
    if cid_raw is None or cid_raw == "":
        chosen = None
    else:
        chosen = str(cid_raw).strip() or None
    try:
        confidence = float(conf_raw)
    except (TypeError, ValueError):
        confidence = 0.0

    def _reject_link() -> CanonicalPersistPlan:
        extra: dict[str, Any] = {
            "code": "canonical_adjudication",
            "model": model,
            "canonical_id": chosen,
            "confidence": confidence,
            "rationale": rationale or None,
            "outcome": "no_high_confidence_link",
            "min_confidence_for_link": ADJUDICATION_LINK_MIN_CONFIDENCE,
        }
        merged = tuple(list(plan.resolution_reasons) + [extra])
        if organization_may_materialize_canonical_after_recall(organization):
            return CanonicalPersistPlan(
                decision=CanonicalPersistDecision.MATERIALIZE_NEW,
                resolution_reasons=merged,
            )
        return CanonicalPersistPlan(
            decision=CanonicalPersistDecision.DEFER,
            resolution_reasons=merged,
        )

    candidate_row = candidates_by_id.get(str(chosen)) if chosen is not None else None

    allow_cross_type = plan_has_organization_canonical_type_mismatch(plan)
    min_confidence = ADJUDICATION_LINK_MIN_CONFIDENCE
    if (
        allow_cross_type
        and candidate_row is not None
        and organization_types_are_link_compatible(
            organization.organization_type,
            candidate_row[2],
        )
    ):
        min_confidence = ADJUDICATION_COMPATIBLE_TYPE_LINK_MIN_CONFIDENCE

    if chosen is None or confidence < min_confidence:
        return _reject_link()

    if candidate_row is None:
        return _reject_link()

    _cid, canon_label, canon_org_type, _aliases = candidate_row
    if not allow_cross_type and not _organization_type_matches_candidate(
        organization,
        canon_organization_type=canon_org_type,
    ):
        return _reject_link()

    substrate_norm = normalize_organization_text(organization.normalized_name or organization.name)
    canon_label_norm = normalize_organization_text(canon_label)
    if multiword_organization_names_share_ambiguous_acronym(
        substrate_norm,
        canon_label_norm,
    ):
        return _reject_link()

    extra = {
        "code": "canonical_adjudication",
        "model": model,
        "canonical_id": str(chosen),
        "confidence": float(confidence),
        "rationale": rationale or None,
        "outcome": "link_existing",
        "min_confidence_for_link": ADJUDICATION_LINK_MIN_CONFIDENCE,
    }
    merged = tuple(list(plan.resolution_reasons) + [extra])
    linked = CanonicalPersistPlan(
        decision=CanonicalPersistDecision.LINK_EXISTING,
        existing_canonical_id=str(chosen),
        resolution_reasons=merged,
    )
    if session is not None and stylebook_id is not None:
        return gate_or_coerce_link_plan(
            session,
            linked,
            entity_type="organization",
            substrate_row=organization,
            stylebook_id=stylebook_id,
        )
    return linked


def adjudicate_ambiguous_organization_plan_with_llm(
    session: Session,
    *,
    plan: CanonicalPersistPlan,
    organization: SubstrateOrganization,
    stylebook_id: int,
    model: str,
    model_config_id: str | None = None,
) -> CanonicalPersistPlan:
    """LLM pick among recalled organization canonicals; declined link may materialize."""
    prepared = prepare_organization_adjudication(
        session,
        plan=plan,
        organization=organization,
        stylebook_id=stylebook_id,
        model=model,
        model_config_id=model_config_id,
    )
    if prepared is None:
        return plan
    llm_data = run_organization_adjudication_llm(prepared)
    return resolve_organization_adjudication_plan(
        plan,
        prepared=prepared,
        llm_data=llm_data,
        session=session,
        stylebook_id=stylebook_id,
    )
