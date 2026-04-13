"""LangGraph agent for intelligent geocoding with fallback strategies."""

from typing import Optional
from langgraph.graph import StateGraph, END  # type: ignore
from .nodes import orchestrate_geocode, consolidate_node, enrich_node, output_node
from .types import AgentState

def create_geocoding_agent(calculate_parents: bool = False):
    """
    Create the LangGraph geocoding agent using model-based approach.
    
    Args:
        calculate_parents: Whether to run the enrich node for parent calculation
    
    Returns:
        Compiled LangGraph workflow
    """
    # Create the graph
    workflow = StateGraph(AgentState)
    
    # Add nodes
    workflow.add_node("orchestrate_geocode", orchestrate_geocode)
    workflow.add_node("consolidate", consolidate_node)
    
    if calculate_parents:
        workflow.add_node("enrich", enrich_node)
    
    workflow.add_node("output", output_node)
    
    # Add edges
    workflow.set_entry_point("orchestrate_geocode")
    workflow.add_edge("orchestrate_geocode", "consolidate")
    
    if calculate_parents:
        workflow.add_edge("consolidate", "enrich")
        workflow.add_edge("enrich", "output")
    else:
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
    calculate_parents: bool = False,
    use_cache: bool = False,
    stylebook_api_url: Optional[str] = None,
    project_slug: Optional[str] = None,
    service_api_token: Optional[str] = None
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
        calculate_parents: Whether to calculate parent hierarchies
        
    Returns:
        Consolidated output dict if successful, None otherwise
    """
    # Create agent
    agent = create_geocoding_agent(calculate_parents=calculate_parents)
    
    # Initialize state
    initial_state: AgentState = {
        "location_text": location_text,
        "location_type": location_type,
        "location_components": location_components,
        "original_text": original_text,
        "extra_fields": extra_fields or {},
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
        "final_output": None
    }
    
    # Run the agent
    final_state = await agent.ainvoke(initial_state)
    
    return final_state["final_output"]
