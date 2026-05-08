"""LiteLLM routing strings and model_cost lookup aliases."""

from __future__ import annotations

from backfield_ai.litellm_model import (
    litellm_model_cost_lookup_keys,
    litellm_model_id,
)


def test_litellm_model_id_google_gemini_and_gemma_use_gemini_prefix() -> None:
    assert litellm_model_id("google", "gemini-2.5-flash") == "gemini/gemini-2.5-flash"
    assert litellm_model_id("google", "gemma-3-12b-it") == "gemini/gemma-3-12b-it"


def test_litellm_model_id_google_non_gemini_keeps_google_prefix() -> None:
    assert litellm_model_id("google", "some-other-route") == "google/some-other-route"


def test_litellm_model_cost_lookup_keys_google_includes_gemini_slash() -> None:
    keys = litellm_model_cost_lookup_keys("google", "gemini-2.5-flash")
    assert "gemini/gemini-2.5-flash" in keys


def test_litellm_model_cost_lookup_keys_flash_thinking_falls_back_to_flash() -> None:
    keys = litellm_model_cost_lookup_keys("google", "gemini-2.5-flash-thinking")
    assert "gemini-2.5-flash" in keys
    assert "gemini/gemini-2.5-flash" in keys


def test_litellm_model_cost_lookup_keys_openrouter_qwq_adds_deepinfra_alias() -> None:
    keys = litellm_model_cost_lookup_keys("openrouter", "qwen/qwq-32b")
    assert "deepinfra/Qwen/QwQ-32B" in keys
