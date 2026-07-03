"""Batched LLM review for questionable organization canonicals."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, Literal

logger = logging.getLogger(__name__)

DEFAULT_QUESTIONABLE_ORG_LLM_MODEL = "gpt-5-nano"
DEFAULT_QUESTIONABLE_ORG_BATCH_SIZE = 50

QuestionableOrgDecision = Literal["flag", "keep", "unsure"]
QuestionableOrgCategory = Literal[
    "person_like",
    "place_like",
    "law_policy_program",
    "event_award_history",
    "generic_group",
    "work_or_topic",
    "other_non_organization",
]
QuestionableOrgConfidence = Literal["high", "medium", "low"]
SuggestedEntityType = Literal["person", "location", "none", "unknown"]

_DECISIONS: frozenset[str] = frozenset({"flag", "keep", "unsure"})
_CATEGORIES: frozenset[str] = frozenset(
    {
        "person_like",
        "place_like",
        "law_policy_program",
        "event_award_history",
        "generic_group",
        "work_or_topic",
        "other_non_organization",
    }
)
_CONFIDENCE: frozenset[str] = frozenset({"high", "medium", "low"})
_SUGGESTED_TYPES: frozenset[str] = frozenset({"person", "location", "none", "unknown"})


@dataclass(frozen=True)
class QuestionableOrganizationCandidate:
    canonical_id: str
    label: str
    slug: str
    organization_type: str | None
    prefilter_score: int
    prefilter_signals: tuple[str, ...]
    linked_count: int
    mention_count: int
    sample_mentions: tuple[str, ...]


@dataclass(frozen=True)
class QuestionableOrganizationReviewResult:
    canonical_id: str
    decision: QuestionableOrgDecision
    category: QuestionableOrgCategory
    confidence: QuestionableOrgConfidence
    explanation: str
    suggested_entity_type: SuggestedEntityType


def build_questionable_organization_batch_prompt(
    candidates: list[QuestionableOrganizationCandidate],
) -> str:
    lines: list[str] = [
        "You are reviewing organization canonical catalog rows that may not be real organizations.",
        "Each row is an existing organization canonical label in a newsroom stylebook.",
        "Decide whether editors should review it because it is likely NOT a durable institution "
        "or organized body of people.",
        "",
        "Likely NOT organizations:",
        "- people and person-role phrases",
        "- places, neighborhoods, parks, landmarks, cities",
        "- laws, acts, bills, policies, grants, programs",
        "- events, awards, competitions, historical events",
        "- generic role groups without a named institution",
        "- works, titles, topics, concepts",
        "",
        "Likely organizations:",
        (
            "- agencies, departments, offices, councils, boards, companies, schools, teams, "
            "nonprofits, hospitals, unions, leagues, museums, foundations, and similar "
            "institutions"
        ),
        "",
        "Rules:",
        (
            "- Use decision=flag when editors should review because the label is likely not "
            "an organization."
        ),
        "- Use decision=keep when the label is a real organization or institution.",
        "- Use decision=unsure only when evidence is genuinely ambiguous.",
        "- Prefer flag over unsure when the label looks like a person, place, law, program, event, "
        "or generic group.",
        (
            "- A named administration or office can be an organization when the institution "
            "is the actor."
        ),
        "",
        "Return JSON only:",
        '{"results":[{"canonical_id":"...","decision":"flag|keep|unsure",'
        '"category":"person_like|place_like|law_policy_program|event_award_history|'
        'generic_group|work_or_topic|other_non_organization",'
        '"confidence":"high|medium|low","explanation":"short editor-facing reason",'
        '"suggested_entity_type":"person|location|none|unknown"}]}',
        "",
        "Candidates:",
    ]
    for candidate in candidates:
        mention_part = ""
        if candidate.sample_mentions:
            samples = ", ".join(repr(text) for text in candidate.sample_mentions)
            mention_part = f" mentions=[{samples}]"
        signals = ", ".join(candidate.prefilter_signals) or "none"
        lines.append(
            "- "
            f"id={candidate.canonical_id} "
            f"label={candidate.label!r} "
            f"type={candidate.organization_type or 'unknown'!r} "
            f"prefilter_score={candidate.prefilter_score} "
            f"signals={signals} "
            f"linked={candidate.linked_count} "
            f"mention_count={candidate.mention_count}"
            f"{mention_part}"
        )
    return "\n".join(lines)


def _parse_llm_json(raw: str) -> dict[str, Any] | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def parse_questionable_organization_batch_response(
    data: dict[str, Any] | None,
    *,
    valid_ids: set[str],
) -> dict[str, QuestionableOrganizationReviewResult]:
    if data is None:
        return {}
    raw_results = data.get("results")
    if not isinstance(raw_results, list):
        return {}
    out: dict[str, QuestionableOrganizationReviewResult] = {}
    for raw in raw_results:
        if not isinstance(raw, dict):
            continue
        canonical_id = str(raw.get("canonical_id") or "").strip()
        if not canonical_id or canonical_id not in valid_ids or canonical_id in out:
            continue
        decision = str(raw.get("decision") or "").strip().lower()
        if decision not in _DECISIONS:
            continue
        category = str(raw.get("category") or "other_non_organization").strip().lower()
        if category not in _CATEGORIES:
            category = "other_non_organization"
        confidence = str(raw.get("confidence") or "medium").strip().lower()
        if confidence not in _CONFIDENCE:
            confidence = "medium"
        explanation = str(raw.get("explanation") or "").strip()
        if not explanation:
            continue
        suggested = str(raw.get("suggested_entity_type") or "unknown").strip().lower()
        if suggested not in _SUGGESTED_TYPES:
            suggested = "unknown"
        out[canonical_id] = QuestionableOrganizationReviewResult(
            canonical_id=canonical_id,
            decision=decision,  # type: ignore[arg-type]
            category=category,  # type: ignore[arg-type]
            confidence=confidence,  # type: ignore[arg-type]
            explanation=explanation,
            suggested_entity_type=suggested,  # type: ignore[arg-type]
        )
    return out


def should_persist_questionable_organization_review(
    result: QuestionableOrganizationReviewResult,
) -> bool:
    if result.decision == "flag":
        return True
    if result.decision == "unsure" and result.confidence in {"high", "medium"}:
        return True
    return False


def review_questionable_organization_batches(
    candidates: list[QuestionableOrganizationCandidate],
    *,
    call_llm: Callable[..., str],
    model: str = DEFAULT_QUESTIONABLE_ORG_LLM_MODEL,
    model_config_id: str | None = None,
    batch_size: int = DEFAULT_QUESTIONABLE_ORG_BATCH_SIZE,
) -> dict[str, QuestionableOrganizationReviewResult]:
    """Run batched LLM review and return parsed results keyed by canonical id."""
    if not candidates:
        return {}
    accepted: dict[str, QuestionableOrganizationReviewResult] = {}
    batches = list(_chunked(candidates, batch_size))
    failed_batches = 0
    for batch in batches:
        valid_ids = {candidate.canonical_id for candidate in batch}
        prompt = build_questionable_organization_batch_prompt(batch)
        try:
            raw = call_llm(
                prompt,
                model=model,
                force_json=True,
                temperature=0.0,
                model_config_id=model_config_id,
            )
        except Exception as exc:
            logger.warning("Questionable organization LLM batch failed: %s", exc)
            failed_batches += 1
            continue
        parsed = parse_questionable_organization_batch_response(
            _parse_llm_json(raw),
            valid_ids=valid_ids,
        )
        accepted.update(parsed)
    if failed_batches == len(batches):
        raise RuntimeError(
            "Questionable organization LLM review failed for all batches. "
            "Check organization AI credentials and default generative model settings."
        )
    return accepted


def _chunked(
    items: list[QuestionableOrganizationCandidate],
    size: int,
) -> Iterable[list[QuestionableOrganizationCandidate]]:
    if size <= 0:
        yield items
        return
    for index in range(0, len(items), size):
        yield items[index : index + size]
