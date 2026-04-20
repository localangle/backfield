"""LLM adjudication for ambiguous canonical matches (DBOutput / Stylebook ingest)."""

from __future__ import annotations

import json
import os
from typing import Any

from agate_utils.llm import call_llm
from backfield_db import StylebookLocationCanonical, SubstrateLocation
from backfield_stylebook.canonical_policy import (
    CanonicalPersistDecision,
    CanonicalPersistPlan,
)
from sqlmodel import Session, select


def _ambiguous_reason(plan: CanonicalPersistPlan) -> dict[str, Any] | None:
    for r in plan.resolution_reasons:
        if isinstance(r, dict) and str(r.get("code") or "") == "ambiguous_canonical_match":
            return r
    return None


def _candidate_rows(
    session: Session,
    *,
    stylebook_id: int,
    canonical_ids: list[int],
) -> list[tuple[int, str]]:
    if not canonical_ids:
        return []
    rows = session.exec(
        select(StylebookLocationCanonical).where(
            StylebookLocationCanonical.stylebook_id == stylebook_id,
            StylebookLocationCanonical.id.in_(canonical_ids[:24]),
        )
    ).all()
    out: list[tuple[int, str]] = []
    for c in rows:
        if c.id is None:
            continue
        out.append((int(c.id), str(c.label)))
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
    cids: list[int] = []
    for x in raw_ids:
        try:
            cids.append(int(x))
        except (TypeError, ValueError):
            continue
    if not cids:
        return plan
    candidates = _candidate_rows(session, stylebook_id=stylebook_id, canonical_ids=cids)
    if not candidates:
        return plan

    lines = "\n".join(f"- id={cid} label={label!r}" for cid, label in candidates)
    prompt = (
        "You adjudicate which canonical location row best matches a substrate location "
        "candidate.\n"
        f"Substrate name: {location.name!r}\n"
        f"Normalized name: {location.normalized_name!r}\n"
        f"Location type: {location.location_type!r}\n"
        f"Formatted address: {location.formatted_address!r}\n\n"
        "Candidates (choose at most one id):\n"
        f"{lines}\n\n"
        "Return JSON only with keys canonical_id (int or null), "
        "confidence (0.0-1.0), and rationale (string). "
        "Pick null if none fit."
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
    try:
        chosen = int(cid_raw) if cid_raw is not None else None
    except (TypeError, ValueError):
        chosen = None
    try:
        confidence = float(conf_raw)
    except (TypeError, ValueError):
        confidence = 0.0
    if chosen is None or chosen not in {c[0] for c in candidates} or confidence < 0.65:
        extra = {
            "code": "canonical_adjudication",
            "model": model,
            "canonical_id": chosen,
            "confidence": confidence,
            "rationale": rationale or None,
            "outcome": "no_high_confidence_link",
        }
        merged = tuple(list(plan.resolution_reasons) + [extra])
        return CanonicalPersistPlan(decision=plan.decision, resolution_reasons=merged)

    extra = {
        "code": "canonical_adjudication",
        "model": model,
        "canonical_id": int(chosen),
        "confidence": float(confidence),
        "rationale": rationale or None,
        "outcome": "link_existing",
    }
    merged = tuple(list(plan.resolution_reasons) + [extra])
    return CanonicalPersistPlan(
        decision=CanonicalPersistDecision.LINK_EXISTING,
        existing_canonical_id=int(chosen),
        resolution_reasons=merged,
    )
