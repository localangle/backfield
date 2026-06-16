"""LLM adjudication for ambiguous person canonical matches (DBOutput ingest)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from agate_utils.llm import call_llm
from backfield_db import StylebookPersonCanonical, SubstratePerson
from backfield_entities.canonical.plan_types import (
    ADJUDICATION_LINK_MIN_CONFIDENCE,
    CanonicalPersistDecision,
    CanonicalPersistPlan,
)
from backfield_entities.entities.person.policy import (
    AMBIGUOUS_PERSON_CANONICAL_MATCH,
    person_may_materialize_canonical_after_recall,
)
from sqlmodel import Session, select

from worker.substrate.canonical.llm_call_policy import (
    ADJUDICATION_LLM_MAX_RETRIES,
    ADJUDICATION_LLM_SKIP_MAX_TOKENS_BUMP,
    ADJUDICATION_LLM_TIMEOUT_S,
)


@dataclass(frozen=True)
class PersonAdjudicationPrepared:
    person: SubstratePerson
    model: str
    model_config_id: str | None
    candidates: tuple[tuple[str, str, str | None, str | None], ...]
    prompt: str


def _recall_context_for_adjudication(plan: CanonicalPersistPlan) -> dict[str, Any] | None:
    for r in plan.resolution_reasons:
        if not isinstance(r, dict):
            continue
        if str(r.get("code") or "") == AMBIGUOUS_PERSON_CANONICAL_MATCH:
            ids = r.get("recall_canonical_ids")
            if isinstance(ids, list) and ids:
                return r
    return None


def _candidate_rows(
    session: Session,
    *,
    stylebook_id: int,
    canonical_ids: list[str],
) -> list[tuple[str, str, str | None, str | None]]:
    if not canonical_ids:
        return []
    rows = session.exec(
        select(StylebookPersonCanonical).where(
            StylebookPersonCanonical.stylebook_id == stylebook_id,
            StylebookPersonCanonical.id.in_(canonical_ids[:24]),
        )
    ).all()
    out: list[tuple[str, str, str | None, str | None]] = []
    for c in rows:
        if c.id is None:
            continue
        out.append(
            (
                str(c.id),
                str(c.label),
                (c.title or "").strip() or None,
                (c.affiliation or "").strip() or None,
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


def prepare_person_adjudication(
    session: Session,
    *,
    plan: CanonicalPersistPlan,
    person: SubstratePerson,
    stylebook_id: int,
    model: str,
    model_config_id: str | None = None,
) -> PersonAdjudicationPrepared | None:
    cids = _canonical_ids_from_recall(plan)
    if not cids:
        return None
    candidates = _candidate_rows(session, stylebook_id=stylebook_id, canonical_ids=cids)
    if not candidates:
        return None

    lines = "\n".join(
        f"- id={cid} label={label!r} title={title!r} affiliation={aff!r}"
        for cid, label, title, aff in candidates
    )
    floor = ADJUDICATION_LINK_MIN_CONFIDENCE
    prompt = (
        "You decide whether exactly ONE canonical row denotes the SAME real-world person as "
        "the substrate row (editorial identity in a news catalog), not a namesake.\n\n"
        f"Substrate name: {person.name!r}\n"
        f"Normalized name: {person.normalized_name!r}\n"
        f"Title: {(person.title or '')!r}\n"
        f"Affiliation: {(person.affiliation or '')!r}\n\n"
        "Candidates (at most one id may be chosen):\n"
        f"{lines}\n\n"
        "Rules:\n"
        "- Set canonical_id only when the candidate is the SAME individual the substrate row "
        "represents (same person despite minor spelling variants).\n"
        "- Set canonical_id to null when affiliation, role, or context indicates a different "
        "person with a similar name, or when you are not certain.\n"
        "- Prefer null (human review) over a stretched link between namesakes.\n"
        f"- Use confidence {floor} or higher only for definitive same-person identity; "
        f"otherwise use confidence below {floor} (the system will not auto-link).\n\n"
        "Return JSON only: canonical_id (UUID string matching one candidate id, or null), "
        "confidence (0.0-1.0), rationale (short string)."
    )
    return PersonAdjudicationPrepared(
        person=person,
        model=model,
        model_config_id=model_config_id,
        candidates=tuple(candidates),
        prompt=prompt,
    )


def run_person_adjudication_llm(prepared: PersonAdjudicationPrepared) -> dict[str, Any] | None:
    try:
        raw = call_llm(
            prepared.prompt,
            model=prepared.model,
            force_json=True,
            temperature=0.0,
            max_tokens=800,
            max_retries=ADJUDICATION_LLM_MAX_RETRIES,
            timeout=ADJUDICATION_LLM_TIMEOUT_S,
            allow_max_tokens_bump=not ADJUDICATION_LLM_SKIP_MAX_TOKENS_BUMP,
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            model_config_id=prepared.model_config_id,
        )
        data = json.loads(raw)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    return data


def resolve_person_adjudication_plan(
    plan: CanonicalPersistPlan,
    *,
    prepared: PersonAdjudicationPrepared,
    llm_data: dict[str, Any] | None,
) -> CanonicalPersistPlan:
    if llm_data is None:
        return plan

    person = prepared.person
    candidates = prepared.candidates
    model = prepared.model

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

    candidate_ids = {str(c[0]) for c in candidates}

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
        if person_may_materialize_canonical_after_recall(person):
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
        or chosen not in candidate_ids
        or confidence < ADJUDICATION_LINK_MIN_CONFIDENCE
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
    return CanonicalPersistPlan(
        decision=CanonicalPersistDecision.LINK_EXISTING,
        existing_canonical_id=str(chosen),
        resolution_reasons=merged,
    )


def adjudicate_ambiguous_person_plan_with_llm(
    session: Session,
    *,
    plan: CanonicalPersistPlan,
    person: SubstratePerson,
    stylebook_id: int,
    model: str,
    model_config_id: str | None = None,
) -> CanonicalPersistPlan:
    """LLM pick among recalled person canonicals; declined link may materialize when allowed."""
    prepared = prepare_person_adjudication(
        session,
        plan=plan,
        person=person,
        stylebook_id=stylebook_id,
        model=model,
        model_config_id=model_config_id,
    )
    if prepared is None:
        return plan
    llm_data = run_person_adjudication_llm(prepared)
    return resolve_person_adjudication_plan(plan, prepared=prepared, llm_data=llm_data)
