"""Overpass API utilities for intersection geocoding."""

import time
import json
import logging
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
import overpy
from shapely.geometry import LineString, Point
from agate_utils.llm import call_llm

logger = logging.getLogger(__name__)

# Initialize Overpass API
api = overpy.Overpass()


########## INTERSECTION PARSING ##########

def parse_intersection_description(text: str, openai_api_key: str) -> Optional[Dict[str, Any]]:
    """
    Parse a natural language intersection description into structured fields.
    
    Args:
        text: Natural language intersection description
        openai_api_key: OpenAI API key for LLM calls
        
    Returns:
        Optional[Dict[str, Any]]: Parsed intersection data or None if parsing fails
        Example: {
            "road_1": "42nd St",
            "road_2": "Cedar Ave", 
            "city": "Minneapolis",
            "state": "MN",
            "latitude": 44.9778,
            "longitude": -93.2650,
            "alternates": {"Cedar Ave": ["MN 77"]}
        }
    """
    try:
        # Correct path from overpass.py location to prompts
        prompt_path = Path(__file__).parent / "prompts" / "parse_intersection_description.md"
        print("prompt_path")
        print(prompt_path)
        with open(prompt_path, 'r') as f:
            prompt_template = f.read()
    except FileNotFoundError:
        logger.error("Parse intersection description prompt not found")
        return None
    
    try:
        prompt = prompt_template.format(text=text)
        
        response = call_llm(
            prompt=prompt,
            model="gpt-5-mini",
            openai_api_key=openai_api_key,
            force_json=True
        )
        
        return json.loads(response.strip())
    except (json.JSONDecodeError, Exception) as e:
        logger.error(f"Failed to parse intersection description '{text}': {str(e)}")
        return None


########## OVERPASS QUERY GENERATION ##########

def generate_single_road_query_with_llm(
    road: str, 
    lat: float, 
    lon: float, 
    api_key: str,
    radius: int = 50000, 
    alternates: Optional[List[str]] = None
) -> str:
    """
    Generate an OverpassQL query for a single road using LLM.
    
    Args:
        road: Road name to search for
        lat: Latitude of search center
        lon: Longitude of search center
        api_key: OpenAI API key for LLM calls
        radius: Search radius in meters
        alternates: Alternate names for the road
        
    Returns:
        str: Valid OverpassQL query
    """
    try:
        alternates_str = alternates or []
        
        prompt_path = Path(__file__).parent / "prompts" / "generate_overpass_query.md"
        with open(prompt_path, 'r') as f:
            prompt_template = f.read()
        
        prompt = prompt_template.format(
            road=road,
            alternates=alternates_str,
            radius=radius,
            lat=lat,
            lon=lon
        )
        
        response = call_llm(
            prompt=prompt,
            model="gpt-5-mini",
            openai_api_key=api_key,
            force_json=False
        )
        
        return clean_overpass_query(response.strip())
        
    except Exception as e:
        logger.error(f"Failed to generate Overpass query for road '{road}': {str(e)}")
        # Return a basic fallback query
        return f"""
        [out:json][timeout:25];
        (
          way["name"~"{road}"](around:{radius},{lat},{lon});
        );
        out geom;
        """


def clean_overpass_query(raw_response: str) -> str:
    """
    Clean up LLM-generated OverpassQL query.
    
    Args:
        raw_response: Raw LLM response
        
    Returns:
        str: Cleaned OverpassQL query
    """
    lines = raw_response.strip().splitlines()
    return "\n".join(line for line in lines if not line.strip().startswith("```")).strip()


########## QUERY EXECUTION ##########

def run_query_with_overpy(query: str, max_retries: int = 4) -> Optional[overpy.Result]:
    """
    Execute an OverpassQL query with retry logic.
    
    Args:
        query: OverpassQL query to execute
        max_retries: Maximum number of retry attempts
        
    Returns:
        Optional[overpy.Result]: Query result or None if failed
    """
    retry_delay = 2  # Start with 2 seconds for gateway timeouts
    for attempt in range(max_retries):
        try:
            logger.info(f"Executing Overpass query (attempt {attempt + 1})")
            return api.query(query)
        except Exception as e:
            # Check if it's a specific overpy error type
            error_str = str(e).lower()
            if "bad request" in error_str or "syntax" in error_str:
                logger.error(f"Overpass bad request - query syntax error: {e}")
                logger.error("This is a query problem, retrying won't help. Bailing out.")
                return None
            elif "gateway timeout" in error_str or "server load" in error_str or "timeout" in error_str:
                logger.warning(f"Overpass server error on attempt {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    retry_delay = min(retry_delay * 2, 15)  # Cap at 15 seconds
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    logger.error("Max retries exceeded for Overpass query")
                    return None
            else:
                # For any other error, log and retry
                logger.warning(f"Overpass error on attempt {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    retry_delay = min(retry_delay * 2, 15)  # Cap at 15 seconds
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    logger.error("Max retries exceeded for Overpass query")
                    return None


########## GEOMETRIC OPERATIONS ##########

def linestrings_from_ways(result: overpy.Result) -> List[LineString]:
    """
    Convert Overpass ways to Shapely LineString objects.
    
    Args:
        result: Overpass query result
        
    Returns:
        List[LineString]: List of LineString geometries
    """
    ways = []
    for way in result.ways:
        coords = [(node.lon, node.lat) for node in way.nodes]
        if len(coords) >= 2:
            ways.append(LineString(coords))
    return ways


def find_geometric_intersections(result1: overpy.Result, result2: overpy.Result) -> List[Point]:
    """
    Find geometric intersections between two sets of road ways.
    
    Args:
        result1: First road's Overpass result
        result2: Second road's Overpass result
        
    Returns:
        List[Point]: List of intersection points
    """
    lines1 = linestrings_from_ways(result1)
    lines2 = linestrings_from_ways(result2)

    intersections = []
    for l1 in lines1:
        for l2 in lines2:
            if l1.intersects(l2):
                intersection = l1.intersection(l2)
                if isinstance(intersection, Point):
                    intersections.append(intersection)
                elif hasattr(intersection, 'geoms'):
                    for geom in intersection.geoms:
                        if isinstance(geom, Point):
                            intersections.append(geom)
    return intersections


########## LLM FUNCTIONS ##########

async def estimate_overpass_parameters(address_text: str, openai_api_key: str) -> Optional[Tuple[float, float, int]]:
    """
    Estimate plausible latitude, longitude, and search radius for an address.
    This is useful for setting up Overpass queries when we don't have precise coordinates.
    
    Args:
        address_text: Address string like "Hiawatha Ave. Minneapolis MN"
        openai_api_key: OpenAI API key for LLM calls
        
    Returns:
        Optional[Tuple[float, float, int]]: (latitude, longitude, radius_meters) if successful, None otherwise
    """
    try:
        # Load the prompt template
        prompt_path = Path(__file__).parent / "prompts" / "estimate_overpass_parameters.md"
        with open(prompt_path, 'r') as f:
            prompt_template = f.read()
        
        prompt = prompt_template.format(address_text=address_text)
        
        response = call_llm(
            prompt=prompt,
            model="gpt-5-mini",
            openai_api_key=openai_api_key,
            force_json=True
        )
        
        result = json.loads(response)
        
        if "latitude" in result and "longitude" in result and "radius" in result:
            lat = float(result["latitude"])
            lon = float(result["longitude"])
            radius = int(result["radius"])
            
            # Basic validation - ensure coordinates are reasonable
            if -90 <= lat <= 90 and -180 <= lon <= 180 and 1000 <= radius <= 500000:
                logger.info(f"Estimated search parameters for {address_text}: lat={lat}, lon={lon}, radius={radius}m")
                return (lat, lon, radius)
            else:
                logger.warning(f"LLM returned invalid parameters for {address_text}: lat={lat}, lon={lon}, radius={radius}")
                return None
        else:
            logger.warning(f"LLM response missing required fields for {address_text}")
            return None
    except Exception as e:
        logger.error(f"Error estimating search parameters for {address_text}: {e}")
        return None


def choose_most_plausible_intersection(
    input_string: str,
    candidates: List[Point],
    openai_api_key: str,
    max_candidates: int = 10
) -> Optional[Point]:
    """
    Use LLM to select the most plausible intersection from candidates.
    
    Args:
        input_string: Original user input
        candidates: List of candidate intersection points
        openai_api_key: OpenAI API key for LLM calls
        max_candidates: Maximum number of candidates to consider
        
    Returns:
        Optional[Point]: Most plausible intersection point or None
    """
    if not candidates:
        return None

    # Sort by distance to center lat/lon (as a basic filter)
    # Optionally: keep top N to reduce LLM token use
    trimmed = candidates[:max_candidates]

    # Format choices for the LLM
    choices = "\n".join(
        f"{i+1}. lat: {pt.y:.6f}, lon: {pt.x:.6f}"
        for i, pt in enumerate(trimmed)
    )

    try:
        prompt_path = Path(__file__).parent / "prompts" / "choose_intersection.md"
        with open(prompt_path, 'r') as f:
            prompt_template = f.read()
        
        prompt = prompt_template.format(
            input_string=input_string,
            choices=choices
        )
        
        response = call_llm(
            prompt=prompt,
            model="gpt-5-mini",
            openai_api_key=openai_api_key,
            force_json=False
        )
        
        # Clean up the response to handle decimal points
        cleaned_response = response.strip().rstrip('.')
        choice = int(cleaned_response)
        if 1 <= choice <= len(trimmed):
            return trimmed[choice - 1]
    except Exception as e:
        logger.error(f"LLM ranking failed: {e}")

    return None


########## MAIN INTERSECTION FUNCTIONS ##########

async def find_intersection_coordinates(
    road_1: str,
    road_2: str,
    lat: float,
    lon: float,
    openai_api_key: str,
    radius: Optional[int] = None,
    alt_map: Optional[Dict[str, List[str]]] = None,
    orig_text: Optional[str] = None
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Find intersection coordinates for two roads.
    
    Args:
        road_1: First road name
        road_2: Second road name
        lat: Latitude of search center
        lon: Longitude of search center
        openai_api_key: OpenAI API key for LLM calls
        radius: Search radius in meters (if None, will be estimated)
        alt_map: Map of road names to alternate names
        orig_text: Original user input for context
        
    Returns:
        List[Dict[str, Any]]: List of intersection results with coordinates
        List[str]: List of Overpass queries used
    """
    alt_map = alt_map or {}
    
    # Estimate radius if not provided
    if radius is None and orig_text:
        estimated_params = await estimate_overpass_parameters(orig_text, openai_api_key)
        if estimated_params:
            _, _, radius = estimated_params
            logger.info(f"Estimated radius for intersection search: {radius}m")
        else:
            radius = 50000  # Fallback to default
            logger.warning(f"Could not estimate radius, using default: {radius}m")
    elif radius is None:
        radius = 50000  # Fallback to default
        logger.warning(f"No radius provided and no original text, using default: {radius}m")
    
    # Generate queries for both roads
    query1 = generate_single_road_query_with_llm(road_1, lat, lon, openai_api_key, radius, alternates=alt_map.get(road_1, []))
    query2 = generate_single_road_query_with_llm(road_2, lat, lon, openai_api_key, radius, alternates=alt_map.get(road_2, []))

    logger.info(f"Generated query for road 1 ({road_1}):")
    logger.info(query1)
    logger.info(f"Generated query for road 2 ({road_2}):")
    logger.info(query2)
    
    # Collect queries for meta output
    queries = [query1, query2]

    # Execute queries
    logger.info("Executing Overpass queries...")
    result1 = run_query_with_overpy(query1)
    result2 = run_query_with_overpy(query2)
    
    if not result1 or not result2:
        logger.error("Failed to retrieve road data from Overpass")
        logger.error(f"Result1: {result1}")
        logger.error(f"Result2: {result2}")
        return [], []

    # Find geometric intersections
    intersections = find_geometric_intersections(result1, result2)

    if not intersections:
        logger.warning("No geometric intersections found")
        return [], []

    logger.info(f"Found {len(intersections)} intersection point(s)")

    # Prepare results with boundary information
    results = []
    
    # Select most plausible intersection if original text provided
    if orig_text:
        best = choose_most_plausible_intersection(orig_text, intersections, openai_api_key)
        if best:
            logger.info(f"Most plausible intersection: lat={best.y}, lon={best.x}")
            results.append({
                'point': best
            })
        else:
            logger.warning("Could not identify a most plausible intersection")
    else:
        # Return all intersections
        for intersection in intersections:
            results.append({
                'point': intersection
            })

    return results, queries


async def find_intersection_coordinates_from_text(
    intersection_text: str, 
    openai_api_key: str,
    radius: Optional[int] = None
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Find intersection coordinates from natural language description.
    
    Args:
        intersection_text: Natural language intersection description
        openai_api_key: OpenAI API key for LLM calls
        radius: Search radius in meters (if None, will be estimated)
        
    Returns:
        List[Dict[str, Any]]: List of intersection results with coordinates
        List[str]: List of Overpass queries used
    """
    logger.info(f"Starting intersection finder for: {intersection_text}")
    
    # Parse the intersection description
    parsed = parse_intersection_description(intersection_text, openai_api_key)
    if not parsed:
        logger.error("Failed to parse intersection description")
        return [], []
    
    road_1 = parsed["road_1"]
    road_2 = parsed["road_2"]
    lat = parsed["latitude"]
    lon = parsed["longitude"]
    alt_map = parsed.get("alternates", {})

    logger.info(f"Parsed intersection: {road_1} and {road_2} near {parsed['city']}, {parsed['state']}")
    logger.info(f"Location: lat={lat}, lon={lon}")
    logger.info(f"Alternate names: {alt_map}")

    results, queries = await find_intersection_coordinates(
        road_1, road_2, lat, lon, openai_api_key, radius, 
        alt_map=alt_map, orig_text=intersection_text
    )
    return results, queries

