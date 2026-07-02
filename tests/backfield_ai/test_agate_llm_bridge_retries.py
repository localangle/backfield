"""Tests for tracked LiteLLM bridge retry behavior."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from backfield_ai.agate_llm_bridge import call_llm_tracked_sync
from backfield_ai.completion import LiteLLMCompletionRejectedError, LiteLLMCompletionResult


def _rejected_result() -> LiteLLMCompletionResult:
    return LiteLLMCompletionResult(
        text="",
        provider="openai",
        provider_model_id="gpt-4o-mini",
        prompt_tokens=10,
        completion_tokens=0,
        total_tokens=10,
        estimated_cost=Decimal("0"),
        currency="USD",
        cost_estimate_incomplete=False,
        cost_estimate_source="litellm",
        latency_ms=56000,
    )


@patch("backfield_ai.agate_llm_bridge.persist_llm_attempt")
@patch("backfield_ai.agate_llm_bridge.completion_text_sync")
def test_rejected_error_is_not_retried(
    mock_completion: MagicMock,
    mock_persist: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    partial = _rejected_result()
    mock_completion.side_effect = LiteLLMCompletionRejectedError(
        "empty JSON",
        result=partial,
    )

    with pytest.raises(Exception, match="LLM call failed"):
        call_llm_tracked_sync(
            prompt="pick canonical",
            model="gpt-4o-mini",
            system_message=None,
            force_json=True,
            max_retries=3,
            temperature=0.0,
            openai_api_key="test-key",
            anthropic_api_key=None,
            gemini_api_key=None,
            openrouter_api_key=None,
            azure_api_key=None,
            azure_api_base=None,
            project_system_prompt=None,
            timeout=90.0,
            max_tokens=800,
        )

    assert mock_completion.call_count == 1
    assert mock_persist.call_count == 1
    assert mock_persist.call_args.kwargs["status"] == "failed"
    assert mock_persist.call_args.kwargs["attempt_number"] == 1


@patch("backfield_ai.agate_llm_bridge.persist_llm_attempt")
@patch("backfield_ai.agate_llm_bridge.completion_text_sync")
@patch("backfield_ai.agate_llm_bridge.time.sleep")
def test_transient_error_retries_up_to_max_retries(
    mock_sleep: MagicMock,
    mock_completion: MagicMock,
    mock_persist: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    mock_completion.side_effect = TimeoutError("provider timeout")

    with pytest.raises(Exception, match="LLM call failed after 3 attempts"):
        call_llm_tracked_sync(
            prompt="pick canonical",
            model="gpt-4o-mini",
            system_message=None,
            force_json=True,
            max_retries=3,
            temperature=0.0,
            openai_api_key="test-key",
            anthropic_api_key=None,
            gemini_api_key=None,
            openrouter_api_key=None,
            azure_api_key=None,
            azure_api_base=None,
            project_system_prompt=None,
            timeout=90.0,
            max_tokens=800,
        )

    assert mock_completion.call_count == 3
    assert mock_persist.call_count == 3
    assert mock_sleep.call_count == 2
