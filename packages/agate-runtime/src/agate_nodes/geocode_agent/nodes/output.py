"""LangGraph output node for formatting the final geocoding results."""

from typing import Dict, Any
from ..types import AgentState

AREA_KEY_ORDER = ["id", "location", "type", "original_text", "description", "parent_ids", "geocode"]
POINT_KEY_ORDER = ["id", "location", "type", "original_text", "description", "parent_ids", "geocode"]

########## HELPER FUNCTIONS ##########

def _reorder_keys(obj: Dict[str, Any], key_order):
    ordered = {}
    processed = set()

    for key in key_order:
        if key in obj:
            ordered[key] = obj[key]
            processed.add(key)

    for key, value in obj.items():
        if key not in processed:
            ordered[key] = value

    return ordered

def _format_areas(areas):
    if not isinstance(areas, dict):
        return areas
    formatted = {}
    for area_type, area_list in areas.items():
        if isinstance(area_list, list):
            formatted[area_type] = [_reorder_keys(area_obj, AREA_KEY_ORDER) for area_obj in area_list]
        else:
            formatted[area_type] = area_list
    return formatted

def _format_points(points):
    if not isinstance(points, list):
        return points
    return [_reorder_keys(point_obj, POINT_KEY_ORDER) for point_obj in points]

########## OUTPUT NODE ##########

async def output_node(state: AgentState) -> AgentState:
    """
    Format the final output from the geocoding agent.
    
    This node takes the final_output from previous nodes and ensures it's
    properly formatted for consumption by downstream nodes or APIs.
    
    Formatting includes:
    - Reordering keys in area objects to: id, location, type, original_text, geocode (followed by extra fields like 'mural')
    - Reordering keys in point objects to: id, location, type, original_text, geocode (followed by extra fields like 'mural')
    - Preserving any extra fields (like 'mural', 'description', 'parent_ids') after the core fields
    
    Args:
        state: Current agent state with final_output
        
    Returns:
        Updated agent state with formatted final_output
    """
    final_output = state.get("final_output")
    
    if not final_output:
        state["final_output"] = {
            "places": {
                "areas": {
                    "states": [],
                    "counties": [],
                    "cities": [],
                    "neighborhoods": [],
                    "regions": [],
                    "other": []
                },
                "points": [],
                "needs_review": []
            }
        }
        return state
    
    # Format the areas and points with consistent key order
    places = final_output.get("places", {})
    areas = places.get("areas", {})
    points = places.get("points", [])
    
    formatted_areas = _format_areas(areas)
    formatted_points = _format_points(points)
    
    # Update the final output with formatted areas and points
    places["areas"] = formatted_areas
    places["points"] = formatted_points
    final_output["places"] = places
    state["final_output"] = final_output
    return state

