"""GeocodeAgent stylebook id handling."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_EMPTY_PLACES: dict = {
    "areas": {
        "states": [],
        "counties": [],
        "cities": [],
        "neighborhoods": [],
        "regions": [],
        "other": [],
    },
    "points": [],
    "needs_review": [],
}


def _warm_geocode_import_graph() -> None:
    """Prime runner imports so geocode node models can load without a cycle."""
    from agate_runtime.nodes.geocode_agent import run_geocode_agent as _run_geocode_agent

    del _run_geocode_agent


def test_geocode_params_accepts_stylebook_id_snake_case() -> None:
    _warm_geocode_import_graph()
    from agate_nodes.geocode_agent.node import GeocodeAgentParams

    params = GeocodeAgentParams.model_validate({"useCache": True, "stylebook_id": 2})
    assert params.stylebookId == 2


def test_geocode_raises_when_stylebook_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    from agate_runtime.nodes.geocode_agent import run_geocode_agent

    monkeypatch.setenv("BACKFIELD_PROJECT_ID", "1")
    mock_cm = MagicMock()
    mock_sess = MagicMock()
    mock_sess.get.return_value = None
    mock_cm.__enter__.return_value = mock_sess
    mock_cm.__exit__.return_value = None

    with patch("sqlmodel.Session", return_value=mock_cm):
        with pytest.raises(ValueError, match="Stylebook that no longer exists"):
            run_geocode_agent({"useCache": True, "stylebook_id": 99999}, {})


def test_geocode_agent_run_attaches_cache_bundle(monkeypatch: pytest.MonkeyPatch) -> None:
    _warm_geocode_import_graph()
    from agate_nodes.geocode_agent.node import (
        GeocodeAgent,
        GeocodeAgentInput,
        GeocodeAgentOutput,
        GeocodeAgentParams,
    )
    from agate_runtime.context import AgateEnvContext

    monkeypatch.setenv("BACKFIELD_PROJECT_ID", "1")
    ctx = AgateEnvContext()
    params = GeocodeAgentParams.model_validate({"useCache": True, "stylebook_id": 2})

    mock_cm = MagicMock()
    mock_sess = MagicMock()
    mock_sess.get.return_value = MagicMock()
    mock_cm.__enter__.return_value = mock_sess
    mock_cm.__exit__.return_value = None

    async def run_agent() -> None:
        with patch("sqlmodel.Session", return_value=mock_cm):
            with patch(
                "agate_nodes.geocode_agent.node.run_geocode_agent_pipeline",
                new_callable=AsyncMock,
            ) as mock_pipeline:
                mock_pipeline.return_value = GeocodeAgentOutput(places=_EMPTY_PLACES)
                await GeocodeAgent().run(GeocodeAgentInput(), params, ctx)

    asyncio.run(run_agent())

    bundle = ctx.metadata.get("geocode_cache_bundle")
    assert isinstance(bundle, dict)
    assert callable(bundle.get("strict_resolve_with_outcome"))


def test_geocode_agent_async_runner_attaches_cache_bundle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _warm_geocode_import_graph()
    from agate_nodes.geocode_agent.node import (
        GeocodeAgentInput,
        GeocodeAgentOutput,
        GeocodeAgentParams,
    )
    from agate_runtime.context import AgateEnvContext
    from agate_runtime.runners import run_geocode_agent_async

    monkeypatch.setenv("BACKFIELD_PROJECT_ID", "1")
    mock_cm = MagicMock()
    mock_sess = MagicMock()
    mock_sess.get.return_value = MagicMock()
    mock_cm.__enter__.return_value = mock_sess
    mock_cm.__exit__.return_value = None

    captured_ctx: AgateEnvContext | None = None

    async def capture_pipeline(
        _inp: GeocodeAgentInput,
        _params: GeocodeAgentParams,
        ctx: AgateEnvContext,
    ) -> GeocodeAgentOutput:
        nonlocal captured_ctx
        captured_ctx = ctx
        return GeocodeAgentOutput(places=_EMPTY_PLACES)

    async def run_runner() -> None:
        with patch("sqlmodel.Session", return_value=mock_cm):
            with patch(
                "agate_nodes.geocode_agent.node.run_geocode_agent_pipeline",
                side_effect=capture_pipeline,
            ):
                await run_geocode_agent_async(
                    {"useCache": True, "stylebook_id": 2},
                    {},
                    AgateEnvContext(),
                )

    asyncio.run(run_runner())

    assert captured_ctx is not None
    bundle = captured_ctx.metadata.get("geocode_cache_bundle")
    assert isinstance(bundle, dict)
    assert callable(bundle.get("strict_resolve_with_outcome"))
