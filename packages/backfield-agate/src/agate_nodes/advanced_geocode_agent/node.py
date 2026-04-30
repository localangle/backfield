"""AdvancedGeocodeAgent — same consolidation semantics as GeocodeAgent with model params."""

from __future__ import annotations

from pydantic import Field

from backfield_agate.context import AgateEnvContext

from agate_nodes.geocode_agent.node import (
    GeocodeAgentInput,
    GeocodeAgentOutput,
    GeocodeAgentParams,
    run_geocode_agent_pipeline,
)


class AdvancedGeocodeAgentParams(GeocodeAgentParams):
    """GeocodeAgent params plus OpenAI model ids for hybrid / evaluation paths."""

    evaluationModel: str = Field(
        default="gpt-5-nano",
        description="OpenAI model for geocoder result evaluation (area flow)",
    )
    routerModel: str = Field(
        default="gpt-5-nano",
        description="Reserved for future routing / decision LLM steps",
    )


class AdvancedGeocodeAgent:
    """Geocoding node with configurable LLM models (evaluation path wired today)."""

    name = "AdvancedGeocodeAgent"
    version = "0.1.0"
    category = "enrichment"

    Input = GeocodeAgentInput
    Output = GeocodeAgentOutput
    Params = AdvancedGeocodeAgentParams

    async def run(
        self,
        inp: GeocodeAgentInput,
        params: AdvancedGeocodeAgentParams,
        ctx: AgateEnvContext,
    ) -> GeocodeAgentOutput:
        return await run_geocode_agent_pipeline(
            inp,
            params,
            ctx,
            evaluation_llm_model=params.evaluationModel,
            router_llm_model=params.routerModel,
            log_label="AdvancedGeocodeAgent",
        )
