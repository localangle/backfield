"""LLM adjudication for ambiguous canonical matches (DBOutput / Stylebook ingest)."""

from __future__ import annotations

import json
import os
from typing import Any

from agate_utils.llm import call_llm
from backfield_db import StylebookLocationCanonical, SubstrateLocation
from backfield_stylebook.canonical.plan_types import (
    ADJUDICATION_LINK_MIN_CONFIDENCE,
    CanonicalPersistDecision,
    CanonicalPersistPlan,
)
from backfield_stylebook.canonical_jurisdiction import (
    district_identity_from_components,
    district_identity_key,
    place_extract_components_from_entry,
)
from backfield_stylebook.canonical_link_matrix import (
    autolink_container_to_fine_denied,
    link_pair_allowed,
)
from backfield_stylebook.entities.location.policy import (
    substrate_may_materialize_canonical_after_recall,
)
from sqlmodel import Session, select


def _recall_context_for_adjudication(
    plan: CanonicalPersistPlan,
    location: SubstrateLocation,
) -> dict[str, Any] | None:
    """Return recall context for ambiguous matches or forced ``political_district`` adjudication."""
    for r in plan.resolution_reasons:
        if not isinstance(r, dict):
            continue
        if str(r.get("code") or "") == "ambiguous_canonical_match":
            ids = r.get("recall_canonical_ids")
            if isinstance(ids, list) and ids:
                return r
    lt = (location.location_type or "").strip().lower()
    if lt == "political_district" and plan.decision == CanonicalPersistDecision.LINK_EXISTING:
        for r in plan.resolution_reasons:
            if not isinstance(r, dict):
                continue
            if str(r.get("code") or "") == "linked_fuzzy_autolink":
                ids = r.get("recall_canonical_ids")
                if isinstance(ids, list) and ids:
                    return {
                        "recall_canonical_ids": list(ids),
                        "code": "linked_fuzzy_autolink",
                    }
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
) -> list[tuple[str, str, str | None, str | None, str | None, str | None]]:
    if not canonical_ids:
        return []
    rows = session.exec(
        select(StylebookLocationCanonical).where(
            StylebookLocationCanonical.stylebook_id == stylebook_id,
            StylebookLocationCanonical.id.in_(canonical_ids[:24]),
        )
    ).all()
    out: list[tuple[str, str, str | None, str | None, str | None, str | None]] = []
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
            )
        )
    return out


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
    ctx = _recall_context_for_adjudication(plan, location)
    if ctx is None:
        return plan
    raw_ids = ctx.get("recall_canonical_ids")
    if not isinstance(raw_ids, list) or not raw_ids:
        return plan
    cids: list[str] = []
    for x in raw_ids:
        if x is None:
            continue
        s = str(x).strip()
        if s:
            cids.append(s)
    if not cids:
        return plan
    candidates = _candidate_rows(session, stylebook_id=stylebook_id, canonical_ids=cids)
    if not candidates:
        return plan

    lines = "\n".join(
        f"- id={cid} label={label!r} location_type={lt!r} district_key={dk!r} "
        f"district_kind={kind!r} district_number={num!r}"
        for cid, label, lt, dk, kind, num in candidates
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
        f"{district_rules}"
        "- When any candidate is only a rough geographic association, return canonical_id null. "
        "Prefer null (new canonical / human review) over a stretched link.\n"
        f"- Use confidence {floor} or higher only for definitive same-place identity you would "
        f"publish in a catalog; otherwise use confidence below {floor} "
        f"(the system will not link).\n\n"
        "Return JSON only: canonical_id (UUID string matching one candidate id, or null), "
        "confidence (0.0-1.0), rationale (short string)."
    )
    try:
        raw = call_llm(
            prompt,
            model=model,
            force_json=True,
            temperature=0.0,
            max_tokens=800,
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            model_config_id=model_config_id,
        )
        data = json.loads(raw)
    except Exception:
        return plan
    if not isinstance(data, dict):
        return plan
    cid_raw = data.get("canonical_id")
    conf_raw = data.get("confidence", 0.0)
    rationale = str(data.get("rationale") or "").strip()
    chosen: str | None
    if cid_raw is None or cid_raw == "":
        chosen = None
    else:
        chosen = str(cid_raw).strip() or None
    try:
        confidence = float(conf_raw)
    except (TypeError, ValueError):
        confidence = 0.0
    canon = session.get(StylebookLocationCanonical, str(chosen)) if chosen is not None else None

    def _reject_link_extra(
        *,
        outcome: str,
        district_detail: dict[str, Any] | None = None,
    ) -> CanonicalPersistPlan:
        extra: dict[str, Any] = {
            "code": "canonical_adjudication",
            "model": model,
            "canonical_id": chosen,
            "confidence": confidence,
            "rationale": rationale or None,
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

    if (
        chosen is None
        or chosen not in {str(c[0]) for c in candidates}
        or confidence < ADJUDICATION_LINK_MIN_CONFIDENCE
        or canon is None
        or not link_pair_allowed(location.location_type, canon.location_type)
        or autolink_container_to_fine_denied(location.location_type, canon.location_type)
    ):
        return _reject_link_extra(outcome="no_high_confidence_link")

    sub_key = district_identity_key(
        district_identity_from_components(place_extract_components_from_entry(location, None))
    )
    if (location.location_type or "").strip().lower() == "political_district" and sub_key:
        ck = (canon.district_key or "").strip()
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
        "canonical_id": str(chosen),
        "confidence": float(confidence),
        "rationale": rationale or None,
        "outcome": "link_existing",
        "min_confidence_for_link": ADJUDICATION_LINK_MIN_CONFIDENCE,
    }
    merged = tuple(list(plan.resolution_reasons) + [extra])
    return CanonicalPersistPlan(
        decision=CanonicalPersistDecision.LINK_EXISTING,
        existing_canonical_id=str(chosen),
        resolution_reasons=merged,
    )
