"""Per-request model timeouts and node wall-clock messages for extract nodes."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from agate_nodes.extraction.shared_llm import llm_attempt_timeout
from agate_runtime import Edge, GraphSpec, NodeConfig, execute_graph
from agate_runtime.executor import GraphExecutionError, _run_node_async


def test_attempt_timeout_defaults_to_two_minutes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EXTRACT_LLM_ATTEMPT_TIMEOUT_S", raising=False)
    assert llm_attempt_timeout(600.0) == 120.0


def test_attempt_timeout_never_exceeds_the_node_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EXTRACT_LLM_ATTEMPT_TIMEOUT_S", raising=False)
    assert llm_attempt_timeout(90.0) == 90.0


def test_attempt_timeout_can_be_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXTRACT_LLM_ATTEMPT_TIMEOUT_S", "45")
    assert llm_attempt_timeout(600.0) == 45.0


def test_attempt_timeout_zero_uses_whole_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXTRACT_LLM_ATTEMPT_TIMEOUT_S", "0")
    assert llm_attempt_timeout(600.0) == 600.0


def test_attempt_timeout_ignores_unparseable_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXTRACT_LLM_ATTEMPT_TIMEOUT_S", "soon")
    assert llm_attempt_timeout(600.0) == 120.0


def _run_with_async_runner(runner: Any) -> None:
    node = NodeConfig(id="n", type="Slow", params={})
    asyncio.run(
        _run_node_async(
            node,
            {},
            {},
            before_each_node=None,
            after_each_node=None,
            ctx=MagicMock(),
            async_runners={"Slow": runner},
        )
    )


def test_node_that_overruns_its_limit_reports_the_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGATE_NODE_TIMEOUT_S", "1")

    async def never_finishes(*_args: Any) -> dict[str, Any]:
        await asyncio.sleep(30)
        return {}

    with pytest.raises(GraphExecutionError, match="exceeded 1s wall-clock limit"):
        _run_with_async_runner(never_finishes)


def test_timeout_raised_inside_a_node_is_not_reported_as_the_node_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGATE_NODE_TIMEOUT_S", "1200")

    async def model_call_timed_out(*_args: Any) -> dict[str, Any]:
        raise TimeoutError("OrganizationExtract LLM call exceeded timeout of 600.0s")

    with pytest.raises(GraphExecutionError) as excinfo:
        _run_with_async_runner(model_call_timed_out)

    message = str(excinfo.value)
    assert "wall-clock limit" not in message
    assert "OrganizationExtract LLM call exceeded timeout of 600.0s" in message


def test_inner_timeout_is_reported_when_node_limit_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGATE_NODE_TIMEOUT_S", "off")

    async def model_call_timed_out(*_args: Any) -> dict[str, Any]:
        raise TimeoutError("model call timed out")

    with pytest.raises(GraphExecutionError, match="model call timed out"):
        _run_with_async_runner(model_call_timed_out)


def test_organization_extract_gives_each_model_request_the_short_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("EXTRACT_LLM_ATTEMPT_TIMEOUT_S", raising=False)
    spec = GraphSpec(
        name="org-timeout",
        nodes=[
            NodeConfig(id="a", type="TextInput", params={"text": "Cook County approved funding."}),
            NodeConfig(id="b", type="OrganizationExtract", params={"llmTimeout": 600}),
        ],
        edges=[Edge(source="a", target="b", sourceHandle="text", targetHandle="text")],
    )
    with patch(
        "agate_nodes.organization_extract.node_port.call_llm",
        return_value='{"organizations": []}',
    ) as call_llm:
        execute_graph(spec)

    assert call_llm.call_args.kwargs["timeout"] == 120.0
