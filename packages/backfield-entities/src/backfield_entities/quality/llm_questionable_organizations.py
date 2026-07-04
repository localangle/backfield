"""Batched LLM review for questionable organization canonicals."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextvars import copy_context
from dataclasses import dataclass
from typing import Any, Literal

logger = logging.getLogger(__name__)

DEFAULT_QUESTIONABLE_ORG_LLM_MODEL = "gpt-5-nano"
DEFAULT_QUESTIONABLE_ORG_BATCH_SIZE = 50
DEFAULT_SAMPLE_MENTION_MAX_COUNT = 3
DEFAULT_SAMPLE_MENTION_MAX_LEN = 220

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


def trim_sample_mentions_for_prompt(
    mentions: tuple[str, ...],
    *,
    max_count: int = DEFAULT_SAMPLE_MENTION_MAX_COUNT,
    max_len: int = DEFAULT_SAMPLE_MENTION_MAX_LEN,
) -> tuple[str, ...]:
    """Cap mention count and length for LLM prompt payload."""
    trimmed: list[str] = []
    for text in mentions[:max_count]:
        value = str(text).strip()
        if not value:
            continue
        if len(value) > max_len:
            value = value[: max_len - 1] + "…"
        trimmed.append(value)
    return tuple(trimmed)


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
        "- people and person names (including athletes, officials, artists)",
        "- places, neighborhoods, parks, landmarks, historic sites, cities",
        "- laws, acts, bills, policies, grants, programs, and funds",
        "- events, awards, competitions, historical events",
        "- films, performances, shows, albums, books, and other creative-work titles",
        "- publications, surveys, reports, and dataset titles",
        "- broad descriptors and generic social categories without a proper-noun institution",
        "- generic role groups without a named institution",
        "- works, titles, topics, concepts",
        "",
        "Require a proper-noun institution. Flag broad labels like "
        "'American civil society', 'Arizona families', or 'Arizona grand jury'.",
        "",
        "Paired examples (flag, not organizations):",
        "- A Mighty Wind, Angelo My Love → work_or_topic",
        "- American Community Survey → work_or_topic",
        "- Anne Frank House, Arc de Triomphe → place_like",
        "- American civil society, Arizona families, Arizona grand jury → generic_group",
        "- Antonio Martínez Ocasio, Ayo Dosunmu → person_like",
        "- Anti-Weaponization Fund → law_policy_program",
        "Likely organizations:",
        (
            "- agencies, departments, offices, councils, boards, companies, schools, teams, "
            "nonprofits, hospitals, unions, leagues, museums, foundations, and similar "
            "institutions"
        ),
        "",
        "Catalog collisions (important):",
        (
            "- cross_catalog_person means a person canonical shares this exact label. "
            "That is ambiguous — do NOT auto-flag as person. Use organization type and "
            "mention context. Keep companies, schools, nonprofits, and similar institutions "
            "even when a mistaken person row exists."
        ),
        (
            "- cross_catalog_location means a location canonical shares this exact label. "
            "Same rule: use context; institutions named after places can still be organizations."
        ),
        "",
        "Paired keep examples (omit from results — these are real organizations):",
        "- Gibson Guitars (company)",
        "- Glenbard East (school)",
        "- Elect Chicago Women (nonprofit)",
        "- Engaged Capital (financial_institution)",
        "",
        "Rules:",
        (
            "- Use decision=flag when editors should review because the label is likely not "
            "an organization."
        ),
        "- Use decision=unsure only when evidence is genuinely ambiguous.",
        "- Omit rows that are real organizations or institutions; absence means keep.",
        "- When type is company, school, university, nonprofit, financial_institution, or "
        "similar, prefer keep unless mentions clearly show a lone person, not an institution.",
        "- Prefer flag over unsure when the label looks like a person, place, law, program, "
        "fund, film/show title, publication/survey, landmark, broad descriptor, event, "
        "or generic group.",
        (
            "- A named administration or office can be an organization when the institution "
            "is the actor."
        ),
        "",
        "Return JSON only with flagged or unsure rows:",
        '{"results":[{"canonical_id":"...","decision":"flag|unsure",'
        '"category":"person_like|place_like|law_policy_program|event_award_history|'
        'generic_group|work_or_topic|other_non_organization",'
        '"confidence":"high|medium|low","explanation":"one short sentence",'
        '"suggested_entity_type":"person|location|none|unknown"}]}',
        "",
        "Candidates:",
    ]
    for candidate in candidates:
        mention_part = ""
        prompt_mentions = trim_sample_mentions_for_prompt(candidate.sample_mentions)
        if prompt_mentions:
            samples = ", ".join(repr(text) for text in prompt_mentions)
            mention_part = f" mentions=[{samples}]"
        signals = ", ".join(candidate.prefilter_signals) or "none"
        collision_part = ""
        if "cross_catalog_person" in candidate.prefilter_signals:
            collision_part = " catalog_collision=person_canonical_same_label"
        elif "cross_catalog_location" in candidate.prefilter_signals:
            collision_part = " catalog_collision=location_canonical_same_label"
        lines.append(
            "- "
            f"id={candidate.canonical_id} "
            f"label={candidate.label!r} "
            f"type={candidate.organization_type or 'unknown'!r} "
            f"prefilter_score={candidate.prefilter_score} "
            f"signals={signals}{collision_part} "
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


def _run_questionable_organization_batch(
    batch: list[QuestionableOrganizationCandidate],
    *,
    call_llm: Callable[..., str],
    model: str,
    model_config_id: str | None,
) -> dict[str, QuestionableOrganizationReviewResult]:
    valid_ids = {candidate.canonical_id for candidate in batch}
    prompt = build_questionable_organization_batch_prompt(batch)
    raw = call_llm(
        prompt,
        model=model,
        force_json=True,
        temperature=0.0,
        model_config_id=model_config_id,
    )
    return parse_questionable_organization_batch_response(
        _parse_llm_json(raw),
        valid_ids=valid_ids,
    )


def review_questionable_organization_batches(
    candidates: list[QuestionableOrganizationCandidate],
    *,
    call_llm: Callable[..., str],
    model: str = DEFAULT_QUESTIONABLE_ORG_LLM_MODEL,
    model_config_id: str | None = None,
    batch_size: int = DEFAULT_QUESTIONABLE_ORG_BATCH_SIZE,
    max_workers: int = 1,
) -> dict[str, QuestionableOrganizationReviewResult]:
    """Run batched LLM review and return parsed results keyed by canonical id."""
    if not candidates:
        return {}
    accepted: dict[str, QuestionableOrganizationReviewResult] = {}
    batches = list(_chunked(candidates, batch_size))
    total_batches = len(batches)
    failed_batches = 0
    completed_batches = 0
    logger.info(
        "Starting questionable org LLM review: %d candidates in %d batches (max_workers=%d)",
        len(candidates),
        total_batches,
        max_workers,
    )

    def run_batch(
        batch: list[QuestionableOrganizationCandidate],
    ) -> dict[str, QuestionableOrganizationReviewResult]:
        return _run_questionable_organization_batch(
            batch,
            call_llm=call_llm,
            model=model,
            model_config_id=model_config_id,
        )

    if max_workers <= 1 or total_batches <= 1:
        for batch in batches:
            try:
                parsed = run_batch(batch)
            except Exception as exc:
                logger.warning("Questionable org batch failed: %s", exc)
                failed_batches += 1
                continue
            completed_batches += 1
            accepted.update(parsed)
            logger.info(
                "Questionable org batch complete: %d/%d batches done, %d results so far",
                completed_batches,
                total_batches,
                len(accepted),
            )
    else:
        workers = min(max_workers, total_batches)

        def run_batch_in_context(
            batch: list[QuestionableOrganizationCandidate],
        ) -> dict[str, QuestionableOrganizationReviewResult]:
            return copy_context().run(run_batch, batch)

        with ThreadPoolExecutor(max_workers=workers) as pool:
            future_to_size = {
                pool.submit(run_batch_in_context, batch): len(batch) for batch in batches
            }
            for future in as_completed(future_to_size):
                batch_size_actual = future_to_size[future]
                try:
                    parsed = future.result()
                except Exception as exc:
                    logger.warning(
                        "Questionable org batch failed (%d candidates): %s",
                        batch_size_actual,
                        exc,
                    )
                    failed_batches += 1
                    continue
                completed_batches += 1
                accepted.update(parsed)
                logger.info(
                    "Questionable org batch complete: %d/%d batches done, %d results so far",
                    completed_batches,
                    total_batches,
                    len(accepted),
                )

    if failed_batches == total_batches:
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
