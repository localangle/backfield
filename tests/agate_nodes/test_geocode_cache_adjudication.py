"""Unit tests for Stylebook cache adjudication JSON schema and auth guards."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import patch

from agate_nodes.geocode_agent.nodes.cache_adjudication import (
    StylebookCacheAdjudicationAnswer,
    adjudicate_stylebook_cache_node,
)


def test_stylebook_cache_adjudication_answer_json_roundtrip() -> None:
    raw = (
        '{"chosen_canonical_id": "550e8400-e29b-41d4-a716-446655440000", '
        '"needs_review": false, "rationale": "Same city label"}'
    )
    ans = StylebookCacheAdjudicationAnswer.model_validate_json(raw)
    assert ans.chosen_canonical_id == "550e8400-e29b-41d4-a716-446655440000"
    assert ans.needs_review is False


def test_stylebook_cache_adjudication_none_choice() -> None:
    raw = '{"chosen_canonical_id": null, "needs_review": true, "rationale": "ambiguous"}'
    ans = StylebookCacheAdjudicationAnswer.model_validate_json(raw)
    assert ans.chosen_canonical_id is None
    assert ans.needs_review is True


def test_cache_adjudication_skips_without_llm_auth() -> None:
    async def _run() -> None:
        called = {"cand": False}

        def _cand(*_a: object, **_k: object) -> list:
            called["cand"] = True
            return []

        state: dict = {
            "geocode_cache_bundle": {
                "adjudication_candidates": _cand,
                "materialize_canonical": lambda *_a, **_k: None,
            },
            "cache_strict_outcome": {"ambiguous_tier1": True},
            "use_cache_llm_ambiguous_sanity": True,
            "openai_api_key": None,
            "evaluation_llm_model": "gpt-4o-mini",
            "evaluation_ai_model_config_id": None,
            "location_text": "Springfield",
            "location_type": "city",
            "location_components": {},
        }
        await adjudicate_stylebook_cache_node(state)
        assert called["cand"] is False
        assert state.get("geocoding_result") is None

    asyncio.run(_run())


def test_cache_adjudication_proceeds_with_catalog_model_config_without_openai_key() -> None:
    async def _run() -> None:
        llm_called = {"ok": False}

        def _cand(*_a: object, **_k: object) -> list[dict]:
            return [{"id": "550e8400-e29b-41d4-a716-446655440000", "display_name": "Springfield"}]

        def _fake_llm(*_a: object, **kwargs: object) -> str:
            llm_called["ok"] = True
            assert kwargs.get("openai_api_key") is None
            assert kwargs.get("model_config_id") == "cfg-eval-1"
            return json.dumps(
                {
                    "chosen_canonical_id": None,
                    "needs_review": True,
                    "rationale": "catalog auth path",
                }
            )

        state: dict = {
            "geocode_cache_bundle": {
                "adjudication_candidates": _cand,
                "materialize_canonical": lambda *_a, **_k: None,
            },
            "cache_strict_outcome": {"ambiguous_tier1": True},
            "use_cache_llm_ambiguous_sanity": True,
            "openai_api_key": None,
            "evaluation_llm_model": "gpt-4o-mini",
            "evaluation_ai_model_config_id": "cfg-eval-1",
            "location_text": "Springfield",
            "location_type": "city",
            "location_components": {},
        }
        with patch(
            "agate_nodes.geocode_agent.nodes.cache_adjudication.call_llm",
            _fake_llm,
        ):
            await adjudicate_stylebook_cache_node(state)
        assert llm_called["ok"] is True

    asyncio.run(_run())
