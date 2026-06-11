"""Sync entrypoints for async ported nodes (asyncio.run per node)."""

from __future__ import annotations

import asyncio
import os
from typing import Any

from agate_runtime.context import AgateEnvContext
from agate_runtime.output_node import OutputConsolidator
from agate_nodes.geocode_agent.node import (
    GeocodeAgent,
    GeocodeAgentInput,
    GeocodeAgentOutput,
    GeocodeAgentParams,
)
from agate_nodes.organization_extract.node_port import (
    OrganizationExtractInput,
    OrganizationExtractNode,
    OrganizationExtractParams,
)
from agate_nodes.person_extract.node_port import (
    PersonExtractInput,
    PersonExtractNode,
    PersonExtractParams,
)
from agate_nodes.place_extract.node_port import (
    PlaceExtractInput,
    PlaceExtractNode,
    PlaceExtractParams,
)


def default_context() -> AgateEnvContext:
    """Build run context from worker env overlays when present."""
    prompt = os.getenv("BACKFIELD_PROJECT_SYSTEM_PROMPT", "").strip() or None
    run_id = os.getenv("BACKFIELD_RUN_ID", "backfield")
    raw_pid = os.getenv("BACKFIELD_PROJECT_ID")
    project_id: int | None = None
    if raw_pid and str(raw_pid).strip().isdigit():
        project_id = int(str(raw_pid).strip())
    return AgateEnvContext(
        run_id=str(run_id),
        project_id=project_id,
        project_system_prompt=prompt,
    )


async def run_place_extract_async(
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
    return asyncio.run(run_place_extract_async(params, input_state, ctx))


async def run_person_extract_async(
    params: dict[str, Any], input_state: dict[str, Any], ctx: AgateEnvContext
) -> dict[str, Any]:
    node = PersonExtractNode()
    out = await node.run(
        PersonExtractInput.model_validate(input_state),
        PersonExtractParams.model_validate(params),
        ctx,
    )
    return out.model_dump()


def run_person_extract_runtime(
    params: dict[str, Any],
    input_state: dict[str, Any],
    ctx: AgateEnvContext | None = None,
) -> dict[str, Any]:
    ctx = ctx or default_context()
    return asyncio.run(run_person_extract_async(params, input_state, ctx))


async def run_organization_extract_async(
    params: dict[str, Any], input_state: dict[str, Any], ctx: AgateEnvContext
) -> dict[str, Any]:
    node = OrganizationExtractNode()
    out = await node.run(
        OrganizationExtractInput.model_validate(input_state),
        OrganizationExtractParams.model_validate(params),
        ctx,
    )
    return out.model_dump()


def run_organization_extract_runtime(
    params: dict[str, Any],
    input_state: dict[str, Any],
    ctx: AgateEnvContext | None = None,
) -> dict[str, Any]:
    ctx = ctx or default_context()
    return asyncio.run(run_organization_extract_async(params, input_state, ctx))


async def run_article_metadata_async(
    params: dict[str, Any], input_state: dict[str, Any], ctx: AgateEnvContext
) -> dict[str, Any]:
    from agate_nodes.article_metadata.node_port import (
        ArticleMetadataInput,
        ArticleMetadataNode,
        ArticleMetadataParams,
    )

    node = ArticleMetadataNode()
    out = await node.run(
        ArticleMetadataInput.model_validate(input_state),
        ArticleMetadataParams.model_validate(params),
        ctx,
    )
    return out.model_dump()


def run_article_metadata_runtime(
    params: dict[str, Any],
    input_state: dict[str, Any],
    ctx: AgateEnvContext | None = None,
) -> dict[str, Any]:
    ctx = ctx or default_context()
    return asyncio.run(run_article_metadata_async(params, input_state, ctx))


async def run_custom_extract_async(
    params: dict[str, Any], input_state: dict[str, Any], ctx: AgateEnvContext
) -> dict[str, Any]:
    from agate_nodes.custom_extract.node_port import (
        CustomExtractInput,
        CustomExtractNode,
        CustomExtractParams,
    )

    node = CustomExtractNode()
    out = await node.run(
        CustomExtractInput.model_validate(input_state),
        CustomExtractParams.model_validate(params),
        ctx,
    )
    return out.model_dump()


def run_custom_extract_runtime(
    params: dict[str, Any],
    input_state: dict[str, Any],
    ctx: AgateEnvContext | None = None,
) -> dict[str, Any]:
    ctx = ctx or default_context()
    return asyncio.run(run_custom_extract_async(params, input_state, ctx))


async def run_geocode_agent_async(
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
    return asyncio.run(run_geocode_agent_async(params, input_state, ctx))


# Node types the parallel executor awaits directly (no nested asyncio.run).
ASYNC_NODE_RUNNERS: dict[str, Any] = {
    "PlaceExtract": run_place_extract_async,
    "PersonExtract": run_person_extract_async,
    "OrganizationExtract": run_organization_extract_async,
    "ArticleMetadata": run_article_metadata_async,
    "CustomExtract": run_custom_extract_async,
    "GeocodeAgent": run_geocode_agent_async,
}


def run_output_runtime(merged_state: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    cons = OutputConsolidator()
    body = cons.run(merged_state, params)
    return {"consolidated": body}
