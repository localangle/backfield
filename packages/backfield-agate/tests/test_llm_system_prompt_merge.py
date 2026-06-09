"""Project system prompt merge helpers."""

from __future__ import annotations

import pytest
from agate_runtime.runners import default_context
from agate_utils.llm import merge_system_messages, resolve_project_system_prompt


def test_merge_appends_project_prompt_after_node_message() -> None:
    merged = merge_system_messages(
        "You are a specialized people extractor.",
        "Use Chicago ward labels consistently.",
        force_json=True,
    )
    assert merged.startswith("You are a specialized people extractor.")
    assert merged.endswith("Use Chicago ward labels consistently.")
    assert "\n\n" in merged


def test_merge_uses_default_when_base_missing() -> None:
    merged = merge_system_messages(None, "Project overlay.", force_json=True)
    assert "structured JSON" in merged
    assert merged.endswith("Project overlay.")


def test_merge_returns_base_when_overlay_missing() -> None:
    merged = merge_system_messages("Node role only.", None, force_json=True)
    assert merged == "Node role only."


def test_resolve_project_system_prompt_prefers_kwarg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BACKFIELD_PROJECT_SYSTEM_PROMPT", "from env")
    assert resolve_project_system_prompt("from kwarg") == "from kwarg"


def test_resolve_project_system_prompt_falls_back_to_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BACKFIELD_PROJECT_SYSTEM_PROMPT", "from env")
    assert resolve_project_system_prompt() == "from env"


def test_default_context_reads_project_system_prompt_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BACKFIELD_PROJECT_SYSTEM_PROMPT", "Chicago editorial rules")
    monkeypatch.setenv("BACKFIELD_RUN_ID", "run-abc")
    monkeypatch.setenv("BACKFIELD_PROJECT_ID", "7")
    ctx = default_context()
    assert ctx.project_system_prompt == "Chicago editorial rules"
    assert ctx.run_id == "run-abc"
    assert ctx.project_id == 7
