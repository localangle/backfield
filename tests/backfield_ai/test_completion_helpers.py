"""Unit tests for LiteLLM completion helpers (content extraction, JSON mode routing)."""

from __future__ import annotations

import litellm
import pytest
from backfield_ai.completion import (
    LiteLLMCompletionRejectedError,
    _extract_message_content_text,
    _litellm_completion_temperature,
    _litellm_json_object_response_format_supported,
    completion_text_sync,
)
from backfield_ai.constants import COST_ESTIMATE_SOURCE_LITELLM


class _Msg:
    def __init__(self, content: object) -> None:
        self.content = content


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        ("gpt-4o-mini", True),
        ("openai/gpt-4o", True),
        ("azure/my-deployment", True),
        ("anthropic/claude-sonnet-4-5-20250929", True),
        ("groq/llama-3.1-8b-instant", False),
    ],
)
def test_litellm_json_mode_flag(model: str, expected: bool) -> None:
    assert _litellm_json_object_response_format_supported(model) is expected


@pytest.mark.parametrize(
    ("model", "temperature", "expected"),
    [
        ("gpt-5-nano", 0.2, None),
        ("openai/gpt-5-mini", 0.2, None),
        ("gpt-4o-mini", 0.2, 0.2),
        ("anthropic/claude-sonnet-4-5-20250929", 0.2, 0.2),
        ("gpt-5-nano", None, None),
    ],
)
def test_litellm_completion_temperature(model: str, temperature: float | None, expected) -> None:
    assert _litellm_completion_temperature(model, temperature) == expected


def test_completion_text_sync_omits_temperature_for_gpt5(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class Msg:
        content = "ok"
        refusal = None

    class Choice:
        finish_reason = "stop"
        message = Msg()

    class Resp:
        choices = [Choice()]
        usage = {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}

    def fake_completion(**kwargs: object) -> Resp:
        captured.update(kwargs)
        return Resp()

    monkeypatch.setattr(litellm, "completion", fake_completion)
    monkeypatch.setattr(litellm, "completion_cost", lambda **_kw: 0.0)

    completion_text_sync(
        litellm_model="openai/gpt-5-nano",
        messages=[{"role": "user", "content": "hi"}],
        api_key="sk-test",
        max_tokens=32,
        temperature=0.2,
        timeout=30.0,
        force_json_response=False,
    )

    assert "temperature" not in captured


def test_extract_plain_string() -> None:
    assert _extract_message_content_text(_Msg('  {"a": 1}  ')) == '{"a": 1}'


def test_extract_none_content() -> None:
    assert _extract_message_content_text(_Msg(None)) == ""


def test_extract_list_text_blocks() -> None:
    msg = _Msg([{"type": "text", "text": '{"locations":[]}'}])
    assert _extract_message_content_text(msg) == '{"locations":[]}'


def test_extract_list_output_text_blocks() -> None:
    msg = _Msg([{"type": "output_text", "text": "[ ]"}])
    assert _extract_message_content_text(msg) == "[ ]"


def test_extract_object_blocks_with_text_attr() -> None:
    class Block:
        text = "ok"

    assert _extract_message_content_text(_Msg([Block()])) == "ok"


def test_extract_skips_reasoning_then_keeps_json_block() -> None:
    msg = _Msg(
        [
            {"type": "reasoning", "text": "internal chain of thought..."},
            {"type": "output_text", "text": '{"locations":[]}'},
        ],
    )
    assert _extract_message_content_text(msg) == '{"locations":[]}'


def test_empty_json_rejected_error_carries_tokens_and_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Failed JSON completions still get usage from LiteLLM so call rows can record tokens."""

    class Msg:
        content = ""
        refusal = None

    class Choice:
        finish_reason = "length"
        message = Msg()

    class Resp:
        choices = [Choice()]
        usage = {"prompt_tokens": 621, "completion_tokens": 633, "total_tokens": 1254}

    def fake_completion(**kwargs: object) -> Resp:
        return Resp()

    monkeypatch.setattr(litellm, "completion", fake_completion)
    monkeypatch.setattr(litellm, "completion_cost", lambda **_kw: 0.00028425)

    with pytest.raises(LiteLLMCompletionRejectedError) as ctx:
        completion_text_sync(
            litellm_model="gpt-5-nano",
            messages=[{"role": "system", "content": "s"}, {"role": "user", "content": "u"}],
            api_key="sk-test",
            max_tokens=None,
            temperature=None,
            timeout=60.0,
            force_json_response=True,
        )
    r = ctx.value.result
    assert r.prompt_tokens == 621
    assert r.completion_tokens == 633
    assert r.total_tokens == 1254
    assert r.provider == "openai"
    assert r.provider_model_id == "gpt-5-nano"
    assert r.latency_ms >= 0
    assert r.cost_estimate_source == COST_ESTIMATE_SOURCE_LITELLM
