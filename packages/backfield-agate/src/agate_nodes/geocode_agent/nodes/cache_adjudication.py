"""LLM adjudication for Stylebook canonical cache when strict deterministic tiers miss."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from agate_utils.geocoding.geocoding_types import stylebook_match_to_geocoding_result
from agate_utils.llm import call_llm

from ..types import AgentState, normalized_geocode_hints

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "choose_stylebook_cache_canonical.md"


class StylebookCacheAdjudicationAnswer(BaseModel):
    chosen_canonical_id: str | None = None
    needs_review: bool = False
    rationale: str | None = Field(default=None)


def _advanced_quiet(state: AgentState) -> bool:
    return bool(state.get("advanced_quiet_logs"))


def _adv_info(state: AgentState, msg: str, *args: object) -> None:
    if _advanced_quiet(state):
        logger.debug(msg, *args)
    else:
        logger.info(msg, *args)


def _should_run_cache_llm_adjudication(state: AgentState, outcome: dict[str, object]) -> bool:
    ambiguous = bool(outcome.get("ambiguous_tier1"))
    sanity_failed = bool(outcome.get("tier2_sanity_failed"))
    match_was_none = outcome.get("match_dict") is None

    if ambiguous or sanity_failed:
        return bool(state.get("use_cache_llm_ambiguous_sanity", True))

    if match_was_none and not ambiguous and not sanity_failed:
        return bool(state.get("use_cache_llm_miss_recall", False))

    return False


async def adjudicate_stylebook_cache_node(state: AgentState) -> AgentState:
    """Optional LLM pick among permissive canonical recall after strict cache miss paths."""
    if state.get("geocoding_result") is not None:
        return state

    bundle = state.get("geocode_cache_bundle")
    if not isinstance(bundle, dict):
        return state

    cand_fn = bundle.get("adjudication_candidates")
    mat_fn = bundle.get("materialize_canonical")
    if not (callable(cand_fn) and callable(mat_fn)):
        return state

    outcome = state.get("cache_strict_outcome")
    if not isinstance(outcome, dict):
        return state

    if not _should_run_cache_llm_adjudication(state, outcome):
        return state

    openai_key = state.get("openai_api_key")
    eval_model = state.get("evaluation_llm_model")
    if not openai_key or not eval_model:
        _adv_info(state, "[CACHE ADJUDICATION SKIP] Missing OpenAI key or evaluation model")
        return state

    location_text = state.get("location_text") or ""
    location_type = (state.get("location_type") or "").strip()
    components = state.get("location_components") or {}
    if not isinstance(components, dict):
        components = {}

    try:
        candidates = await asyncio.to_thread(
            cand_fn,
            location_text,
            location_type,
            components,
        )
    except Exception as exc:
        logger.warning("Cache adjudication candidate retrieval failed: %s", exc)
        return state

    if not candidates:
        _adv_info(state, "[CACHE ADJUDICATION SKIP] No candidates for '%s'", location_text)
        return state

    hints_raw = (state.get("geocode_hints") or "").strip()
    if not hints_raw:
        hints_raw = normalized_geocode_hints(state.get("extra_fields")) or ""
    geocode_hints_prompt = hints_raw if hints_raw else "(none)"

    template = _PROMPT_PATH.read_text(encoding="utf-8")
    user_block = (
        f"location_type: {location_type}\n"
        f"location_text: {location_text}\n"
        f"original_text: {state.get('original_text') or ''}\n"
        f"geocode_hints: {geocode_hints_prompt}\n"
        f"components_json:\n{json.dumps(components, default=str)[:6000]}\n\n"
        f"candidates_json:\n{json.dumps(candidates, indent=2, default=str)[:12000]}\n"
    )
    prompt = f"{template.strip()}\n\n---\n\n## Current mention\n\n{user_block}"

    def _sync_llm() -> str:
        return call_llm(
            prompt,
            model=eval_model,
            system_message=None,
            force_json=True,
            max_retries=1,
            temperature=0.0,
            max_tokens=1024,
            openai_api_key=openai_key,
            anthropic_api_key=None,
            project_system_prompt=None,
            timeout=120.0,
            model_config_id=state.get("evaluation_ai_model_config_id"),
        )

    try:
        raw = await asyncio.to_thread(_sync_llm)
        answer = StylebookCacheAdjudicationAnswer.model_validate_json(raw)
    except (ValidationError, json.JSONDecodeError) as exc:
        logger.warning("Cache adjudication LLM JSON invalid for '%s': %s", location_text, exc)
        return state
    except Exception as exc:
        logger.warning("Cache adjudication LLM failed for '%s': %s", location_text, exc)
        return state

    if answer.needs_review or not (answer.chosen_canonical_id or "").strip():
        _adv_info(
            state,
            "[CACHE ADJUDICATION] No canonical chosen for '%s' (needs_review=%s)",
            location_text,
            answer.needs_review,
        )
        return state

    cid = answer.chosen_canonical_id.strip()
    allowed = {str(c.get("id")) for c in candidates if isinstance(c, dict) and c.get("id")}
    if cid not in allowed:
        logger.warning(
            "Cache adjudication LLM returned unknown canonical id %r for '%s'",
            cid,
            location_text,
        )
        return state

    substrate_lt = location_type.strip() if isinstance(location_type, str) and location_type.strip() else None

    try:
        match_dict = await asyncio.to_thread(mat_fn, cid, substrate_lt)
    except Exception as exc:
        logger.warning("Materialize canonical %r failed: %s", cid, exc)
        return state

    if not match_dict:
        logger.warning("Materialize canonical %r returned empty for '%s'", cid, location_text)
        return state

    src = (match_dict.get("confidence") or {}).get("source")
    if src != "canonical_db":
        logger.warning("Unexpected materialized cache source %r for '%s'", src, location_text)
        return state

    try:
        geocoding_result = stylebook_match_to_geocoding_result(match_dict, location_text)
        if geocoding_result and geocoding_result.result.geometry:
            state["geocoding_result"] = geocoding_result
            state["geocoding_model"] = None
            state["geocoding_failure_reason"] = None
            state["cache_adjudication_audit"] = {
                "chosen_canonical_id": cid,
                "rationale": answer.rationale,
                "candidate_count": len(candidates),
            }
            _adv_info(
                state,
                "[CACHE ADJUDICATION HIT] Canonical %s for '%s'",
                cid,
                location_text,
            )
        else:
            logger.warning(
                "Adjudicated canonical %r for '%s' has no geometry; skipping",
                cid,
                location_text,
            )
    except Exception as exc:
        logger.warning("Converting adjudicated match for '%s': %s", location_text, exc)

    return state
