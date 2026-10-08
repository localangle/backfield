"""``call_llm(reasoning_effort=...)`` reaches the LiteLLM request in worker runs."""

from __future__ import annotations

from unittest.mock import patch

import litellm
import pytest
from agate_utils.llm import call_llm


class _Msg:
    refusal = None
    content = '{"locations": []}'


class _Choice:
    finish_reason = "stop"
    message = _Msg()


class _Resp:
    choices = [_Choice()]
    usage = {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}


@pytest.mark.parametrize(("requested", "expected"), [("low", "low"), (None, "minimal")])
def test_call_llm_forwards_reasoning_effort_to_litellm(
    monkeypatch: pytest.MonkeyPatch,
    requested: str | None,
    expected: str,
) -> None:
    monkeypatch.setenv("BACKFIELD_RUN_ID", "1")
    captured: dict[str, object] = {}

    def fake_completion(**kwargs: object) -> _Resp:
        captured.update(kwargs)
        return _Resp()

    monkeypatch.setattr(litellm, "completion", fake_completion)
    monkeypatch.setattr(litellm, "completion_cost", lambda **_kw: 0.0)

    with patch("backfield_ai.agate_llm_bridge.persist_llm_attempt"):
        call_llm(
            prompt="Extract places.",
            model="gpt-5-nano",
            openai_api_key="sk-test",
            reasoning_effort=requested,
        )

    assert captured["model"] == "gpt-5-nano"
    assert captured.get("reasoning_effort") == expected
