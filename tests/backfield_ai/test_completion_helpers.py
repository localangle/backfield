"""Unit tests for LiteLLM completion helpers (content extraction, JSON mode routing)."""

from __future__ import annotations

import pytest
from backfield_ai.completion import (
    _extract_message_content_text,
    _litellm_json_object_response_format_supported,
)


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
