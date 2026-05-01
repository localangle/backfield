"""Unit tests for AdvancedGeocodeAgent route_strategy node."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import patch

from agate_nodes.geocode_agent.nodes.route_strategy import route_strategy_node


def test_route_strategy_skips_audit_when_cache_hit() -> None:
    async def _run() -> None:
        state: dict = {
            "location_type": "city",
            "location_text": "Springfield",
            "geocoding_result": {"mock": True},
        }
        await route_strategy_node(state)
        assert state.get("router_audit") is None

    asyncio.run(_run())


def test_route_strategy_fallback_without_openai_key() -> None:
    async def _run() -> None:
        state: dict = {
            "location_type": "place",
            "location_text": "Joe's Coffee",
            "location_components": {},
            "original_text": "",
            "openai_api_key": None,
            "router_llm_model": "gpt-4o-mini",
        }
        await route_strategy_node(state)
        assert state.get("geocode_strategy") == "legacy_default"
        assert state.get("suppress_brave_search") is False
        audit = state.get("router_audit")
        assert isinstance(audit, dict)
        assert audit.get("outcome") == "fallback_no_openai_key"
        assert "geocode_hints_snippet" in audit
        assert audit.get("geocode_hints_snippet") == ""

    asyncio.run(_run())


def test_route_strategy_llm_selects_no_web_search() -> None:
    async def _run() -> None:
        captured: dict[str, str] = {}

        def _fake_llm(prompt: str, *_a: object, **_k: object) -> str:
            captured["prompt"] = prompt
            return json.dumps({"strategy": "no_web_search", "rationale": "unit"})

        long_hint = "x" * 250
        state: dict = {
            "location_type": "place",
            "location_text": "Example",
            "location_components": {},
            "original_text": "",
            "geocode_hints": long_hint,
            "openai_api_key": "sk-test",
            "router_llm_model": "gpt-4o-mini",
        }
        with patch("agate_nodes.geocode_agent.nodes.route_strategy.call_llm", _fake_llm):
            await route_strategy_node(state)
        assert state.get("suppress_brave_search") is True
        audit = state.get("router_audit")
        assert isinstance(audit, dict)
        assert audit.get("outcome") == "llm_ok"
        assert audit.get("strategy_selected") == "no_web_search"
        assert "geocode_hints:" in captured["prompt"]
        assert long_hint[:200] in captured["prompt"]
        assert audit.get("geocode_hints_snippet") == long_hint[:200]

    asyncio.run(_run())


def test_route_strategy_fallback_after_invalid_llm_json() -> None:
    async def _run() -> None:
        def _bad_llm(*_a: object, **_k: object) -> str:
            return "not-json"

        state: dict = {
            "location_type": "city",
            "location_text": "X",
            "location_components": {},
            "original_text": "",
            "openai_api_key": "sk-test",
            "router_llm_model": "gpt-4o-mini",
        }
        with patch("agate_nodes.geocode_agent.nodes.route_strategy.call_llm", _bad_llm):
            await route_strategy_node(state)
        assert state.get("geocode_strategy") == "legacy_default"
        audit = state.get("router_audit")
        assert isinstance(audit, dict)
        assert audit.get("outcome") == "fallback_after_retries"
        assert len(audit.get("attempts") or []) == 3

    asyncio.run(_run())
