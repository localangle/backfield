"""Advanced-only LLM router: closed strategy enum after cache miss."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from agate_utils.llm import call_llm

from ..llm_auth import has_llm_auth
from ..types import AgentState

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "route_strategy.md"

STRATEGY_WEB_SEARCH = "web_search"
STRATEGY_NO_WEB_SEARCH = "no_web_search"

GeocodeStrategyLiteral = Literal["web_search", "no_web_search"]

# Types that never use Brave/DuckDuckGo for resolution (structured geocoding only).
_STRUCTURAL_LOCATION_TYPES: frozenset[str] = frozenset(
    {
        "state",
        "county",
        "city",
        "neighborhood",
        "address",
        "natural",
        "street_road",
        "span",
        "intersection_road",
        "intersection_highway",
    }
)


class GeocodeRoutePlan(BaseModel):
    """Structured router output (validated JSON)."""

    strategy: GeocodeStrategyLiteral
    rationale: str | None = Field(default=None)


def fallback_strategy_for_location_type(location_type: str) -> GeocodeStrategyLiteral:
    """Per-type default when the router fails or is unavailable."""
    lt = (location_type or "").lower()
    if lt == "place":
        return STRATEGY_WEB_SEARCH
    if lt.startswith("region") or lt in _STRUCTURAL_LOCATION_TYPES:
        return STRATEGY_NO_WEB_SEARCH
    return STRATEGY_NO_WEB_SEARCH


def _apply_strategy(state: AgentState, strategy: GeocodeStrategyLiteral) -> None:
    state["geocode_strategy"] = strategy
    state["allow_web_search"] = strategy == STRATEGY_WEB_SEARCH


def _load_prompt_template() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _router_audit_log(payload: dict) -> None:
    logger.info("geocode_router_audit %s", json.dumps(payload, default=str))


async def route_strategy_node(state: AgentState) -> AgentState:
    """After ``resolve_cache_or_miss``: LLM-picks strategy, or skip on cache hit."""
    if state.get("geocoding_result") is not None:
        state["router_audit"] = None
        state.pop("allow_web_search", None)
        return state

    location_type = (state.get("location_type") or "").lower()
    location_text = state.get("location_text") or ""
    fallback = fallback_strategy_for_location_type(location_type)

    attempts: list[dict] = []

    hints_raw = (state.get("geocode_hints") or "").strip()
    geocode_hints_prompt = hints_raw if hints_raw else "(none)"
    audit_core: dict = {
        "node": "route_strategy",
        "location_type": location_type,
        "location_text_snippet": location_text[:200],
        "geocode_hints_snippet": hints_raw[:200] if hints_raw else "",
    }

    openai_key = state.get("openai_api_key")
    router_model = state.get("router_llm_model")
    router_model_config_id = state.get("router_ai_model_config_id")

    if not has_llm_auth(openai_key, router_model_config_id):
        _apply_strategy(state, fallback)
        audit = {
            **audit_core,
            "outcome": "fallback_no_llm_auth",
            "strategy_selected": fallback,
            "attempts": attempts,
        }
        state["router_audit"] = audit
        _router_audit_log(audit)
        return state

    if not router_model:
        _apply_strategy(state, fallback)
        audit = {
            **audit_core,
            "outcome": "fallback_no_router_model",
            "strategy_selected": fallback,
            "attempts": attempts,
        }
        state["router_audit"] = audit
        _router_audit_log(audit)
        return state

    components = state.get("location_components") or {}
    if not isinstance(components, dict):
        components = {}

    template = _load_prompt_template()
    user_prompt = template.format(
        location_type=location_type,
        location_text=location_text,
        original_text=state.get("original_text") or "",
        geocode_hints=geocode_hints_prompt,
        components_json=json.dumps(components, default=str)[:8000],
    )

    last_err: str | None = None
    cap_sleep = 1.0

    def _sync_llm() -> str:
        return call_llm(
            user_prompt,
            model=router_model,
            system_message=None,
            force_json=True,
            max_retries=1,
            temperature=0.0,
            max_tokens=1024,
            openai_api_key=openai_key,
            anthropic_api_key=None,
            project_system_prompt=None,
            timeout=120.0,
            model_config_id=state.get("router_ai_model_config_id"),
        )

    for attempt_idx in range(3):
        try:
            raw = await asyncio.to_thread(_sync_llm)
            plan = GeocodeRoutePlan.model_validate_json(raw)
            attempts.append({"n": attempt_idx + 1, "ok": True})
            _apply_strategy(state, plan.strategy)
            audit = {
                **audit_core,
                "outcome": "llm_ok",
                "strategy_selected": plan.strategy,
                "rationale": plan.rationale,
                "attempts": attempts,
            }
            state["router_audit"] = audit
            _router_audit_log(audit)
            return state
        except ValidationError as e:
            last_err = str(e)
            attempts.append({"n": attempt_idx + 1, "kind": "validation", "error": last_err})
        except Exception as e:
            last_err = str(e)
            attempts.append({"n": attempt_idx + 1, "kind": "transient", "error": last_err})

        if attempt_idx < 2:
            delay = min(cap_sleep, 0.25 * (2**attempt_idx))
            await asyncio.sleep(delay)

    _apply_strategy(state, fallback)
    audit = {
        **audit_core,
        "outcome": "fallback_after_retries",
        "failure_class": "hard",
        "strategy_selected": fallback,
        "last_error": last_err,
        "attempts": attempts,
    }
    state["router_audit"] = audit
    _router_audit_log(audit)
    return state
