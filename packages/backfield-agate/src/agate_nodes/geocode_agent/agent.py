"""LangGraph agent for intelligent geocoding with fallback strategies."""

from typing import Any, Optional
from langgraph.graph import END, StateGraph  # type: ignore

from .nodes import (
    consolidate_node,
    orchestrate_external_geocode,
    orchestrate_geocode,
    output_node,
    resolve_cache_or_miss,
    route_strategy_node,
)
from .nodes.cache_adjudication import adjudicate_stylebook_cache_node
from .types import AgentState, CacheResolveFn, normalized_geocode_hints


def create_geocoding_agent():
    """
    Create the LangGraph geocoding agent using model-based approach.

    Returns:
        Compiled LangGraph workflow
    """
    # Create the graph
    workflow = StateGraph(AgentState)
    
    # Add nodes
    workflow.add_node("orchestrate_geocode", orchestrate_geocode)
    workflow.add_node("consolidate", consolidate_node)
    workflow.add_node("output", output_node)
    
    # Add edges
    workflow.set_entry_point("orchestrate_geocode")
    workflow.add_edge("orchestrate_geocode", "consolidate")
    workflow.add_edge("consolidate", "output")
    workflow.add_edge("output", END)
    
    return workflow.compile()


def create_advanced_geocoding_agent():
    """Advanced graph: cache → Stylebook adjudication → route_strategy → external geocode → …"""
    workflow = StateGraph(AgentState)
    workflow.add_node("resolve_cache_or_miss", resolve_cache_or_miss)
    workflow.add_node("adjudicate_stylebook_cache", adjudicate_stylebook_cache_node)
    workflow.add_node("route_strategy", route_strategy_node)
    workflow.add_node("orchestrate_external_geocode", orchestrate_external_geocode)
    workflow.add_node("consolidate", consolidate_node)
    workflow.add_node("output", output_node)
    workflow.set_entry_point("resolve_cache_or_miss")
    workflow.add_edge("resolve_cache_or_miss", "adjudicate_stylebook_cache")
    workflow.add_edge("adjudicate_stylebook_cache", "route_strategy")
    workflow.add_edge("route_strategy", "orchestrate_external_geocode")
    workflow.add_edge("orchestrate_external_geocode", "consolidate")
    workflow.add_edge("consolidate", "output")
    workflow.add_edge("output", END)
    return workflow.compile()


########## AGENT RUNNER ##########

async def run_geocoding_agent(
    location_text: str,
    location_type: str,
    location_components: dict,
    original_text: str,
    extra_fields: Optional[dict] = None,
    pelias_api_key: Optional[str] = None,
    geocodio_api_key: Optional[str] = None,
    openai_api_key: Optional[str] = None,
    brave_search_api_key: Optional[str] = None,
    use_cache: bool = False,
    stylebook_api_url: Optional[str] = None,
    project_slug: Optional[str] = None,
    service_api_token: Optional[str] = None,
    cache_resolve: Optional[CacheResolveFn] = None,
    geocode_cache_bundle: Optional[dict[str, Any]] = None,
    use_cache_llm_ambiguous_sanity: bool = True,
    use_cache_llm_miss_recall: bool = False,
    evaluation_llm_model: Optional[str] = None,
    router_llm_model: Optional[str] = None,
    geographic_reasoning_llm_model: Optional[str] = None,
    geographic_estimation_llm_model: Optional[str] = None,
    evaluation_ai_model_config_id: Optional[str] = None,
    router_ai_model_config_id: Optional[str] = None,
    geographic_reasoning_ai_model_config_id: Optional[str] = None,
    geographic_estimation_ai_model_config_id: Optional[str] = None,
) -> Optional[dict]:
    """
    Run the geocoding agent workflow for a single location.
    
    This orchestrates the LangGraph workflow that routes to the appropriate
    geography model and consolidates the results.
    
    Args:
        location_text: Full location text to geocode
        location_type: Type of location (state, address, etc.)
        location_components: Structured components of the location
        original_text: Original text from the article mentioning this place
        pelias_api_key: Pelias API key for geocoding
        geocodio_api_key: Geocodio API key for fallback geocoding
        openai_api_key: OpenAI API key for LLM evaluation
        brave_search_api_key: Brave Search API key for place address finding
        evaluation_llm_model: Optional OpenAI model id for area geocoder evaluation.
        router_llm_model: Used only by ``run_advanced_geocoding_agent`` (route_strategy).

    Returns:
        Consolidated output dict if successful, None otherwise
    """
    # Create agent
    agent = create_geocoding_agent()
    
    # Initialize state
    ef = extra_fields or {}
    initial_state: AgentState = {
        "location_text": location_text,
        "location_type": location_type,
        "location_components": location_components,
        "original_text": original_text,
        "extra_fields": ef,
        "geocode_hints": normalized_geocode_hints(ef),
        "geocoding_result": None,
        "geocoding_model": None,
        "pelias_api_key": pelias_api_key,
        "geocodio_api_key": geocodio_api_key,
        "openai_api_key": openai_api_key,
        "brave_search_api_key": brave_search_api_key,
        "use_cache": use_cache,
        "stylebook_api_url": stylebook_api_url,
        "project_slug": project_slug,
        "service_api_token": service_api_token,
        "cache_resolve": cache_resolve,
        "geocode_cache_bundle": geocode_cache_bundle,
        "use_cache_llm_ambiguous_sanity": use_cache_llm_ambiguous_sanity,
        "use_cache_llm_miss_recall": use_cache_llm_miss_recall,
        "final_output": None,
        "evaluation_llm_model": evaluation_llm_model,
        "router_llm_model": router_llm_model,
        "geographic_reasoning_llm_model": geographic_reasoning_llm_model,
        "geographic_estimation_llm_model": geographic_estimation_llm_model,
        "evaluation_ai_model_config_id": evaluation_ai_model_config_id,
        "router_ai_model_config_id": router_ai_model_config_id,
        "geographic_reasoning_ai_model_config_id": geographic_reasoning_ai_model_config_id,
        "geographic_estimation_ai_model_config_id": geographic_estimation_ai_model_config_id,
    }

    # Run the agent
    final_state = await agent.ainvoke(initial_state)

    return final_state["final_output"]


async def run_advanced_geocoding_agent(
    location_text: str,
    location_type: str,
    location_components: dict,
    original_text: str,
    extra_fields: Optional[dict] = None,
    pelias_api_key: Optional[str] = None,
    geocodio_api_key: Optional[str] = None,
    openai_api_key: Optional[str] = None,
    brave_search_api_key: Optional[str] = None,
    use_cache: bool = False,
    stylebook_api_url: Optional[str] = None,
    project_slug: Optional[str] = None,
    service_api_token: Optional[str] = None,
    cache_resolve: Optional[CacheResolveFn] = None,
    geocode_cache_bundle: Optional[dict[str, Any]] = None,
    use_cache_llm_ambiguous_sanity: bool = True,
    use_cache_llm_miss_recall: bool = False,
    evaluation_llm_model: Optional[str] = None,
    router_llm_model: Optional[str] = None,
    geographic_reasoning_llm_model: Optional[str] = None,
    geographic_estimation_llm_model: Optional[str] = None,
    evaluation_ai_model_config_id: Optional[str] = None,
    router_ai_model_config_id: Optional[str] = None,
    geographic_reasoning_ai_model_config_id: Optional[str] = None,
    geographic_estimation_ai_model_config_id: Optional[str] = None,
) -> Optional[dict]:
    """Same IO as ``run_geocoding_agent`` but uses the Advanced graph (router + quieter INFO)."""
    agent = create_advanced_geocoding_agent()
    ef = extra_fields or {}
    initial_state: AgentState = {
        "location_text": location_text,
        "location_type": location_type,
        "location_components": location_components,
        "original_text": original_text,
        "extra_fields": ef,
        "geocode_hints": normalized_geocode_hints(ef),
        "geocoding_result": None,
        "geocoding_model": None,
        "pelias_api_key": pelias_api_key,
        "geocodio_api_key": geocodio_api_key,
        "openai_api_key": openai_api_key,
        "brave_search_api_key": brave_search_api_key,
        "use_cache": use_cache,
        "stylebook_api_url": stylebook_api_url,
        "project_slug": project_slug,
        "service_api_token": service_api_token,
        "cache_resolve": cache_resolve,
        "geocode_cache_bundle": geocode_cache_bundle,
        "use_cache_llm_ambiguous_sanity": use_cache_llm_ambiguous_sanity,
        "use_cache_llm_miss_recall": use_cache_llm_miss_recall,
        "final_output": None,
        "evaluation_llm_model": evaluation_llm_model,
        "router_llm_model": router_llm_model,
        "geographic_reasoning_llm_model": geographic_reasoning_llm_model,
        "geographic_estimation_llm_model": geographic_estimation_llm_model,
        "evaluation_ai_model_config_id": evaluation_ai_model_config_id,
        "router_ai_model_config_id": router_ai_model_config_id,
        "geographic_reasoning_ai_model_config_id": geographic_reasoning_ai_model_config_id,
        "geographic_estimation_ai_model_config_id": geographic_estimation_ai_model_config_id,
        "advanced_quiet_logs": True,
    }
    final_state = await agent.ainvoke(initial_state)
    return final_state["final_output"]
