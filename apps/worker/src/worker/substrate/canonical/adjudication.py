"""LLM adjudication for ambiguous canonical matches (DBOutput / Stylebook ingest)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from agate_utils.llm import call_llm
from backfield_db import StylebookLocationCanonical, SubstrateLocation
from backfield_entities.canonical.jurisdiction import (
    district_identity_from_components,
    district_identity_key,
    district_kind_keywords_conflict,
    place_extract_components_from_entry,
)
from backfield_entities.canonical.link_commit_gate import gate_or_coerce_link_plan
from backfield_entities.canonical.link_matrix import (
    autolink_container_to_fine_denied,
    link_pair_allowed,
)
from backfield_entities.canonical.plan_types import (
    ADJUDICATION_LINK_MIN_CONFIDENCE,
    CanonicalPersistDecision,
    CanonicalPersistPlan,
)
from backfield_entities.entities.location.policy import (
    substrate_may_materialize_canonical_after_recall,
)
from backfield_entities.ingest.geocode_cache.sanity import (
    substrate_canonical_link_blocked_by_content_sanity,
)
from sqlmodel import Session, select

from worker.substrate.canonical.adjudication_result import (
    ADJUDICATION_CORRECTIVE_SUFFIX,
    ADJUDICATION_JSON_CONTRACT,
    adjudication_allows_link,
    adjudication_audit_fields,
    parse_canonical_adjudication_result,
)
from worker.substrate.canonical.llm_call_policy import (
    ADJUDICATION_LLM_MAX_RETRIES,
    ADJUDICATION_LLM_TIMEOUT_S,
)


@dataclass(frozen=True)
class LocationAdjudicationPrepared:
    location: SubstrateLocation
    model: str
    model_config_id: str | None
    candidates: tuple[
        tuple[str, str, str | None, str | None, str | None, str | None, str | None, str | None],
        ...,
    ]
    prompt: str


def _recall_context_for_adjudication(
    plan: CanonicalPersistPlan,
    location: SubstrateLocation,
) -> dict[str, Any] | None:
    """Return the closed recall set for ambiguous or fuzzy-match adjudication."""
    _ = location
    for r in plan.resolution_reasons:
        if not isinstance(r, dict):
            continue
        if str(r.get("code") or "") in {
            "ambiguous_canonical_match",
            "ambiguous_exact_canonical_match",
            "linked_fuzzy_autolink",
        }:
            ids = r.get("recall_canonical_ids")
            if isinstance(ids, list) and ids:
                return r
    return None


def _substrate_district_identity_line(location: SubstrateLocation) -> str:
    comps = place_extract_components_from_entry(location, None)
    ident = district_identity_from_components(comps)
    key = district_identity_key(ident)
    raw = comps.get("district") if isinstance(comps.get("district"), dict) else {}
    if not key and not raw:
        return "District identity: (not structured in PlaceExtract components)"
    return (
        f"District identity key: {key!r}; components: kind={raw.get('kind')!r}, "
        f"number={raw.get('number')!r}, ordinal={raw.get('ordinal')!r}, scope={raw.get('scope')!r}"
    )


def _candidate_rows(
    session: Session,
    *,
    stylebook_id: int,
    canonical_ids: list[str],
) -> list[tuple[str, str, str | None, str | None, str | None, str | None, str | None, str | None]]:
    if not canonical_ids:
        return []
    rows = session.exec(
        select(StylebookLocationCanonical).where(
            StylebookLocationCanonical.stylebook_id == stylebook_id,
            StylebookLocationCanonical.id.in_(canonical_ids[:24]),
        )
    ).all()
    out: list[
        tuple[str, str, str | None, str | None, str | None, str | None, str | None, str | None]
    ] = []
    for c in rows:
        if c.id is None:
            continue
        out.append(
            (
                str(c.id),
                str(c.label),
                c.location_type,
                c.district_key,
                c.district_kind,
                c.district_number,
                c.formatted_address,
                c.geometry_type,
            )
        )
    return out


def _canonical_ids_from_recall(
    plan: CanonicalPersistPlan,
    location: SubstrateLocation,
) -> list[str]:
    ctx = _recall_context_for_adjudication(plan, location)
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


def prepare_location_adjudication(
    session: Session,
    *,
    plan: CanonicalPersistPlan,
    location: SubstrateLocation,
    stylebook_id: int,
    model: str,
    model_config_id: str | None = None,
) -> LocationAdjudicationPrepared | None:
    cids = _canonical_ids_from_recall(plan, location)
    if not cids:
        return None
    candidates = _candidate_rows(session, stylebook_id=stylebook_id, canonical_ids=cids)
    if not candidates:
        return None

    lines = "\n".join(
        f"- id={cid} label={label!r} location_type={lt!r} district_key={dk!r} "
        f"district_kind={kind!r} district_number={num!r} formatted_address={fa!r} "
        f"geometry_type={gt!r}"
        for cid, label, lt, dk, kind, num, fa, gt in candidates
    )
    floor = ADJUDICATION_LINK_MIN_CONFIDENCE
    district_block = ""
    if (location.location_type or "").strip().lower() == "political_district":
        district_block = _substrate_district_identity_line(location) + "\n"
        district_rules = (
            "- For political districts (wards, legislative districts, numbered precincts): "
            "different district **number** or **kind** means a different jurisdiction. "
            "Return canonical_id **null** unless the chosen candidate's district_key matches "
            "the substrate district identity key when both are present.\n"
        )
    else:
        district_rules = ""

    prompt = (
        "You decide whether exactly ONE canonical row denotes the SAME real-world place as "
        "the substrate row (gazetteer identity), not geographic convenience.\n\n"
        f"Substrate name: {location.name!r}\n"
        f"Normalized name: {location.normalized_name!r}\n"
        f"Location type: {location.location_type!r}\n"
        f"Formatted address: {location.formatted_address!r}\n"
        f"{district_block}\n"
        "Candidates (at most one id may be chosen):\n"
        f"{lines}\n\n"
        "Rules:\n"
        "- Set canonical_id only when the candidate is the SAME place (same city/town/POI/"
        "named region the row was created to represent). Minor spelling or formatting variants "
        "of that same place are OK.\n"
        "- Set canonical_id to null if the substrate is a different municipality, "
        "neighborhood, colloquial region, or POI than every candidate—even if one candidate is "
        "nearby, admin-contained, in the same metro, or the closest listed name.\n"
        "- Do NOT link: suburb to parent core city; city A to city B because they are in the "
        "same metro; a regional nickname (e.g. southern part of a state) to the whole state; "
        "two distinct places that only share a broader region.\n"
        "- When the substrate name's leading segment (before the first comma) names a distinct "
        "venue, building, or landmark, do NOT link to a broader park or place canonical that "
        "only appears as geographic context in the suffix (e.g. a restaurant inside a park).\n"
        f"{district_rules}"
        "- When any candidate is only a rough geographic association, choose decision="
        '"no_match" or "uncertain". Prefer that over a stretched link.\n'
        "- Missing coordinates or a missing formatted address are unknown evidence, not a "
        "conflict. Do not reject an otherwise definitive same-place identity only because "
        "geography is absent.\n"
        f"- Use confidence {floor} or higher only for definitive same-place identity you would "
        f"publish in a catalog; otherwise use confidence below {floor} "
        f"(the system will not link).\n\n"
        f"{ADJUDICATION_JSON_CONTRACT}"
    )
    return LocationAdjudicationPrepared(
        location=location,
        model=model,
        model_config_id=model_config_id,
        candidates=tuple(candidates),
        prompt=prompt,
    )


def _call_location_adjudication_raw(
    prepared: LocationAdjudicationPrepared, prompt: str
) -> dict[str, Any] | None:
    try:
        raw = call_llm(
            prompt,
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
    return data if isinstance(data, dict) else None


def run_location_adjudication_llm(prepared: LocationAdjudicationPrepared) -> dict[str, Any] | None:
    candidate_ids = {str(c[0]) for c in prepared.candidates}
    data = _call_location_adjudication_raw(prepared, prepared.prompt)
    if parse_canonical_adjudication_result(data, candidate_ids=candidate_ids) is not None:
        return data
    retried = _call_location_adjudication_raw(
        prepared, prepared.prompt + ADJUDICATION_CORRECTIVE_SUFFIX
    )
    if parse_canonical_adjudication_result(retried, candidate_ids=candidate_ids) is not None:
        return retried
    return None


def resolve_location_adjudication_plan(
    plan: CanonicalPersistPlan,
    *,
    prepared: LocationAdjudicationPrepared,
    llm_data: dict[str, Any] | None,
    session: Session | None = None,
    stylebook_id: int | None = None,
    entry: dict[str, Any] | None = None,
) -> CanonicalPersistPlan:
    if llm_data is None:
        return plan

    location = prepared.location
    candidates = prepared.candidates
    model = prepared.model
    candidates_by_id = {str(c[0]): c for c in candidates}
    parsed = parse_canonical_adjudication_result(
        llm_data, candidate_ids=set(candidates_by_id)
    )
    if parsed is None:
        return plan

    def _reject_link_extra(
        *,
        outcome: str,
        district_detail: dict[str, Any] | None = None,
    ) -> CanonicalPersistPlan:
        extra: dict[str, Any] = {
            "code": "canonical_adjudication",
            "model": model,
            **adjudication_audit_fields(parsed, linked=False),
            "outcome": outcome,
            "min_confidence_for_link": ADJUDICATION_LINK_MIN_CONFIDENCE,
        }
        if district_detail:
            extra["district_gate"] = district_detail
        merged = tuple(list(plan.resolution_reasons) + [extra])
        if substrate_may_materialize_canonical_after_recall(location):
            return CanonicalPersistPlan(
                decision=CanonicalPersistDecision.MATERIALIZE_NEW,
                resolution_reasons=merged,
            )
        return CanonicalPersistPlan(
            decision=CanonicalPersistDecision.DEFER,
            resolution_reasons=merged,
        )

    if not adjudication_allows_link(
        parsed, min_confidence=ADJUDICATION_LINK_MIN_CONFIDENCE
    ):
        return _reject_link_extra(outcome="no_high_confidence_link")

    chosen = str(parsed.canonical_id)
    candidate_row = candidates_by_id.get(chosen)
    if candidate_row is None:
        return _reject_link_extra(outcome="no_high_confidence_link")

    _cid, canon_label, canon_location_type, canon_district_key, _kind, _num, canon_fa, canon_gt = (
        candidate_row
    )
    if not link_pair_allowed(location.location_type, canon_location_type):
        return _reject_link_extra(outcome="no_high_confidence_link")
    if autolink_container_to_fine_denied(location.location_type, canon_location_type):
        return _reject_link_extra(outcome="no_high_confidence_link")

    comps = place_extract_components_from_entry(location, entry)
    if substrate_canonical_link_blocked_by_content_sanity(
        substrate_location_type=location.location_type,
        location_text=str(location.name),
        components=comps,
        match_label=str(canon_label),
        match_formatted_address=canon_fa,
        match_location_type=canon_location_type,
        match_geometry_type=canon_gt,
    ):
        return _reject_link_extra(outcome="content_sanity_coerced")

    s_lt = (location.location_type or "").strip().lower()
    c_lt = (canon_location_type or "").strip().lower()
    if ("political_district" in (s_lt, c_lt)) and district_kind_keywords_conflict(
        (str(location.name or ""), str(location.formatted_address or "")),
        (str(canon_label or ""), str(canon_fa or "")),
    ):
        # e.g. a judicial "subcircuit" row must not link to a same-numbered
        # congressional district / ward / state legislative district canonical.
        return _reject_link_extra(
            outcome="district_kind_mismatch_coerced",
            district_detail={
                "substrate_texts": [
                    str(location.name or ""),
                    str(location.formatted_address or ""),
                ],
                "canonical_label": str(canon_label),
            },
        )

    sub_key = district_identity_key(district_identity_from_components(comps))
    if s_lt == "political_district" and sub_key:
        ck = (canon_district_key or "").strip()
        if ck != sub_key:
            return _reject_link_extra(
                outcome="district_key_mismatch_coerced",
                district_detail={
                    "substrate_district_key": sub_key,
                    "canonical_district_key": ck or None,
                },
            )

    extra = {
        "code": "canonical_adjudication",
        "model": model,
        **adjudication_audit_fields(parsed, linked=True),
        "min_confidence_for_link": ADJUDICATION_LINK_MIN_CONFIDENCE,
    }
    merged = tuple(list(plan.resolution_reasons) + [extra])
    linked = CanonicalPersistPlan(
        decision=CanonicalPersistDecision.LINK_EXISTING,
        existing_canonical_id=chosen,
        resolution_reasons=merged,
    )
    if session is not None and stylebook_id is not None:
        return gate_or_coerce_link_plan(
            session,
            linked,
            entity_type="location",
            substrate_row=location,
            stylebook_id=stylebook_id,
            entry=entry,
        )
    return linked


def adjudicate_ambiguous_plan_with_llm(
    session: Session,
    *,
    plan: CanonicalPersistPlan,
    location: SubstrateLocation,
    stylebook_id: int,
    model: str,
    model_config_id: str | None = None,
) -> CanonicalPersistPlan:
    """LLM pick for ambiguous recall or ``political_district`` fuzzy autolink."""
    prepared = prepare_location_adjudication(
        session,
        plan=plan,
        location=location,
        stylebook_id=stylebook_id,
        model=model,
        model_config_id=model_config_id,
    )
    if prepared is None:
        return plan
    llm_data = run_location_adjudication_llm(prepared)
    return resolve_location_adjudication_plan(
        plan,
        prepared=prepared,
        llm_data=llm_data,
        session=session,
        stylebook_id=stylebook_id,
    )
