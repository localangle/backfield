"""Tests for model-aware prompt budget helpers."""

from __future__ import annotations

import pytest
from backfield_ai.prompt_budget import (
    UNKNOWN_MODEL_CONTEXT_TOKENS,
    PromptBudgetError,
    assert_prompt_fits,
    check_prompt_budget,
    resolve_model_context_limits,
)


def test_unknown_model_uses_8000_fallback() -> None:
    limits = resolve_model_context_limits("totally-unknown-model-xyz-123")
    assert limits.max_input_tokens == UNKNOWN_MODEL_CONTEXT_TOKENS
    assert limits.source == "fallback_8000"


def test_check_prompt_budget_rejects_oversized_prompt() -> None:
    huge = "word " * 20_000
    check = check_prompt_budget(
        litellm_model="totally-unknown-model-xyz-123",
        messages=[{"role": "user", "content": huge}],
        reserved_output_tokens=1500,
        safety_margin_tokens=256,
    )
    assert check.fits is False


def test_assert_prompt_fits_mentions_chunker() -> None:
    huge = "word " * 20_000
    with pytest.raises(PromptBudgetError, match="Document Chunker"):
        assert_prompt_fits(
            litellm_model="totally-unknown-model-xyz-123",
            system_message="System",
            user_prompt=huge,
            chunker_guidance=True,
        )
