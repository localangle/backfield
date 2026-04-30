"""Sync entrypoints for async ported nodes (asyncio.run per node)."""

from __future__ import annotations

import asyncio
from typing import Any

from backfield_agate.context import AgateEnvContext
from backfield_agate.output_node import OutputConsolidator
from agate_nodes.advanced_geocode_agent.node import (
    AdvancedGeocodeAgent,
    AdvancedGeocodeAgentParams,
)
from agate_nodes.geocode_agent.node import (
    GeocodeAgent,
    GeocodeAgentInput,
    GeocodeAgentOutput,
    GeocodeAgentParams,
)
from agate_nodes.place_extract.node_port import (
    PlaceExtractInput,
    PlaceExtractNode,
    PlaceExtractParams,
)


def default_context() -> AgateEnvContext:
    return AgateEnvContext()


async def _place_extract_async(
    params: dict[str, Any], input_state: dict[str, Any], ctx: AgateEnvContext
) -> dict[str, Any]:
    node = PlaceExtractNode()
    out = await node.run(
        PlaceExtractInput.model_validate(input_state),
        PlaceExtractParams.model_validate(params),
        ctx,
    )
    return out.model_dump()


def run_place_extract_runtime(
    params: dict[str, Any],
    input_state: dict[str, Any],
    ctx: AgateEnvContext | None = None,
) -> dict[str, Any]:
    ctx = ctx or default_context()
    return asyncio.run(_place_extract_async(params, input_state, ctx))


async def _geocode_async(
    params: dict[str, Any], input_state: dict[str, Any], ctx: AgateEnvContext
) -> dict[str, Any]:
    node = GeocodeAgent()
    out: GeocodeAgentOutput = await node.run(
        GeocodeAgentInput.model_validate(input_state),
        GeocodeAgentParams.model_validate(params),
        ctx,
    )
    return out.model_dump()


def run_geocode_agent_runtime(
    params: dict[str, Any],
    input_state: dict[str, Any],
    ctx: AgateEnvContext | None = None,
) -> dict[str, Any]:
    ctx = ctx or default_context()
    return asyncio.run(_geocode_async(params, input_state, ctx))


async def _advanced_geocode_async(
    params: dict[str, Any], input_state: dict[str, Any], ctx: AgateEnvContext
) -> dict[str, Any]:
    node = AdvancedGeocodeAgent()
    out: GeocodeAgentOutput = await node.run(
        GeocodeAgentInput.model_validate(input_state),
        AdvancedGeocodeAgentParams.model_validate(params),
        ctx,
    )
    return out.model_dump()


def run_advanced_geocode_agent_runtime(
    params: dict[str, Any],
    input_state: dict[str, Any],
    ctx: AgateEnvContext | None = None,
) -> dict[str, Any]:
    ctx = ctx or default_context()
    return asyncio.run(_advanced_geocode_async(params, input_state, ctx))


def run_output_runtime(merged_state: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    cons = OutputConsolidator()
    body = cons.run(merged_state, params)
    return {"consolidated": body}
