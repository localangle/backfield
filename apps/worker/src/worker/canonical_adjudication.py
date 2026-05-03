"""LLM adjudication for ambiguous canonical matches (DBOutput / Stylebook ingest)."""

from __future__ import annotations

import json
import os
from typing import Any

from agate_utils.llm import call_llm
from backfield_db import StylebookLocationCanonical, SubstrateLocation
from backfield_stylebook.canonical_link_matrix import (
    autolink_container_to_fine_denied,
    link_pair_allowed,
)
from backfield_stylebook.canonical_policy import (
    CanonicalPersistDecision,
    CanonicalPersistPlan,
    substrate_may_materialize_canonical_after_recall,
)
from sqlmodel import Session, select

# LLM must assert definitive same-place identity; below this we keep review / materialize.
ADJUDICATION_LINK_MIN_CONFIDENCE = 0.9


def _ambiguous_reason(plan: CanonicalPersistPlan) -> dict[str, Any] | None:
    for r in plan.resolution_reasons:
        if isinstance(r, dict) and str(r.get("code") or "") == "ambiguous_canonical_match":
            return r
    return None


def _candidate_rows(
    session: Session,
    *,
    stylebook_id: int,
    canonical_ids: list[str],
) -> list[tuple[str, str, str | None]]:
    if not canonical_ids:
        return []
    rows = session.exec(
        select(StylebookLocationCanonical).where(
            StylebookLocationCanonical.stylebook_id == stylebook_id,
            StylebookLocationCanonical.id.in_(canonical_ids[:24]),
        )
    ).all()
    out: list[tuple[str, str, str | None]] = []
    for c in rows:
        if c.id is None:
            continue
        out.append((str(c.id), str(c.label), c.location_type))
    return out


def adjudicate_ambiguous_plan_with_llm(
    session: Session,
    *,
    plan: CanonicalPersistPlan,
    location: SubstrateLocation,
    stylebook_id: int,
    model: str,
) -> CanonicalPersistPlan:
    """If rules returned ambiguous match, ask the LLM to pick a canonical id or null."""
    amb = _ambiguous_reason(plan)
    if amb is None:
        return plan
    raw_ids = amb.get("recall_canonical_ids")
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
        f"- id={cid} label={label!r} location_type={lt!r}" for cid, label, lt in candidates
    )
    floor = ADJUDICATION_LINK_MIN_CONFIDENCE
    prompt = (
        "You decide whether exactly ONE canonical row denotes the SAME real-world place as "
        "the substrate row (gazetteer identity), not geographic convenience.\n\n"
        f"Substrate name: {location.name!r}\n"
        f"Normalized name: {location.normalized_name!r}\n"
        f"Location type: {location.location_type!r}\n"
        f"Formatted address: {location.formatted_address!r}\n\n"
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
    if (
        chosen is None
        or chosen not in {str(c[0]) for c in candidates}
        or confidence < ADJUDICATION_LINK_MIN_CONFIDENCE
        or canon is None
        or not link_pair_allowed(location.location_type, canon.location_type)
        or autolink_container_to_fine_denied(location.location_type, canon.location_type)
    ):
        extra = {
            "code": "canonical_adjudication",
            "model": model,
            "canonical_id": chosen,
            "confidence": confidence,
            "rationale": rationale or None,
            "outcome": "no_high_confidence_link",
            "min_confidence_for_link": ADJUDICATION_LINK_MIN_CONFIDENCE,
        }
        merged = tuple(list(plan.resolution_reasons) + [extra])
        if substrate_may_materialize_canonical_after_recall(location):
            return CanonicalPersistPlan(
                decision=CanonicalPersistDecision.MATERIALIZE_NEW,
                resolution_reasons=merged,
            )
        return CanonicalPersistPlan(decision=plan.decision, resolution_reasons=merged)

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
