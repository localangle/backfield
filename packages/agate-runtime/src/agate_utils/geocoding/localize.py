import logging
import requests
from typing import Optional, List, Dict, Any
from .geocoding_types import (
    GeocodingResult,
    GeocodingResultData,
    GeometryPoint,
    GeometryPolygon,
    bbox_west_south_east_north_to_polygon_coordinates,
)

########## STYLEBOOK API FUNCTIONS ##########

def match_canonical_location(
    name: str,
    base_url: str,
    project_slug: str,
    city: Optional[str] = None,
    state: Optional[str] = None,
    min_similarity: float = 0.7,
    service_token: Optional[str] = None,
    timeout: float = 5.0
) -> Optional[Dict[str, Any]]:
    """
    Match a location name to a canonical StylebookLocation.
    
    Args:
        name: Location name to match
        base_url: Base URL for Stylebook API
        project_slug: Project slug (required)
        city: Optional city filter
        state: Optional state filter
        min_similarity: Minimum similarity threshold (default 0.7)
        service_token: Service API token for authentication
        timeout: Request timeout in seconds
        
    Returns:
        Dict with canonical location data, or None if no match or multiple matches
    """
    try:
        url = f"{base_url.rstrip('/')}/geo/match"
        params = {
            "project_slug": project_slug,
            "name": name,
            "min_similarity": min_similarity
        }
        
        if city:
            params["city"] = city
        if state:
            params["state"] = state
        
        headers = {}
        if service_token:
            headers["Authorization"] = f"Bearer {service_token}"
        
        logging.info(f"Stylebook canonical match: name={name}, project_slug={project_slug}")
        response = requests.get(url, params=params, headers=headers, timeout=timeout)
        response.raise_for_status()
        result = response.json()
        
        # Check if there are multiple matches - if so, return None to fall back to normal geocoding
        if result.get("multiple_matches"):
            logging.info(f"Multiple canonical matches found for '{name}', falling back to normal geocoding")
            return None
        
        if result.get("match"):
            logging.info(f"Found canonical match for '{name}': similarity={result.get('similarity', 0)}")
            return result.get("match")
        else:
            logging.debug(f"No canonical match found for '{name}'")
            return None
            
    except requests.Timeout:
        logging.warning(f"Canonical match request timed out for '{name}'")
        return None
    except requests.RequestException as e:
        logging.warning(f"Canonical match request failed for '{name}': {e}")
        return None
    except Exception as e:
        logging.error(f"Error matching canonical location '{name}': {e}")
        return None


def get_location_cache(
    name: str,
    base_url: str,
    project_slug: str,
    service_token: Optional[str] = None,
    timeout: float = 5.0
) -> Optional[Dict[str, Any]]:
    """
    Get location from LocationCache by exact name match.
    
    Args:
        name: Location name to match
        base_url: Base URL for Stylebook API
        project_slug: Project slug (required)
        service_token: Service API token for authentication
        timeout: Request timeout in seconds
        
    Returns:
        Dict with cached location data, or None if no match
    """
    try:
        url = f"{base_url.rstrip('/')}/geo/cache"
        params = {
            "project_slug": project_slug,
            "name": name
        }
        
        headers = {}
        if service_token:
            headers["Authorization"] = f"Bearer {service_token}"
        
        logging.info(f"Stylebook cache lookup: name={name}, project_slug={project_slug}")
        response = requests.get(url, params=params, headers=headers, timeout=timeout)
        response.raise_for_status()
        result = response.json()
        
        if result.get("match"):
            logging.info(f"Found cache match for '{name}'")
            return result.get("match")
        else:
            logging.debug(f"No cache match found for '{name}'")
            return None
            
    except requests.Timeout:
        logging.warning(f"Cache lookup request timed out for '{name}'")
        return None
    except requests.RequestException as e:
        logging.warning(f"Cache lookup request failed for '{name}': {e}")
        return None
    except Exception as e:
        logging.error(f"Error looking up cache for '{name}': {e}")
        return None


def localize_search(query: str, city: str, state: str, type: str, base_url: str, project_slug: str = "", endpoint: str = "/geo/search", args: str = "") -> Optional[List[Dict[str, Any]]]:
    """
    Search for a location using the Stylebook API.
    
    Args:
        query (str): The search query (e.g., "West Ash")
        city (str): City name (e.g., "Columbia")
        state (str): State abbreviation (e.g., "MO")
        type (str): Geography type (e.g., "neighborhood")
        base_url (str): Base URL for the Stylebook API (default: "https://stylebook-api.agate.localangle.co")
        project_slug (str): Project slug for project-scoped endpoints (required)
        endpoint (str): API endpoint path (default: "/geo/search")
        args (str): Additional URL arguments as a string (e.g., "limit=10&radius=5km")
        
    Returns:
        Optional[List[Dict]]: List of search results or None if search fails
    """
    try:
        url = f"{base_url}{endpoint}"
        params = {
            "city": city,
            "state": state,
            "type": type,
            "q": query
        }
        
        if project_slug:
            params["project_slug"] = project_slug
        
        # Add additional args if provided
        if args:
            # Parse args string and add to params
            for arg in args.split('&'):
                if '=' in arg:
                    key, value = arg.split('=', 1)
                    params[key.strip()] = value.strip()
        
        logging.info(f"Stylebook search: city={city}, state={state}, type={type}, query={query}, project_slug={project_slug}, url={url}")
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        results = data.get("results", [])
        
        if results:
            logging.info(f"Stylebook returned {len(results)} results")
            return results
        else:
            logging.info("Stylebook returned no results")
            return None
            
    except Exception as e:
        logging.error(f"Error in Stylebook search: {str(e)}")
        return None

def localize_reverse(lat: float, lon: float, type: str, base_url: str, project_slug: str = "", endpoint: str = "/geo/reverse", args: str = "") -> Optional[Dict[str, Any]]:
    """
    Reverse geocode coordinates using the Stylebook API.
    
    Args:
        lat (float): Latitude
        lon (float): Longitude
        type (str): Geography type (e.g., "neighborhood")
        base_url (str): Base URL for the Stylebook API (default: "https://stylebook-api.agate.localangle.co")
        project_slug (str): Project slug for project-scoped endpoints (required)
        endpoint (str): API endpoint path (default: "/geo/reverse")
        args (str): Additional URL arguments as a string (e.g., "limit=10&radius=5km")
        
    Returns:
        Optional[Dict]: Result object or None if reverse geocoding fails
    """
    try:
        url = f"{base_url}{endpoint}"
        params = {
            "lat": lat,
            "lon": lon,
            "type": type
        }
        
        if project_slug:
            params["project_slug"] = project_slug
        
        # Add additional args if provided
        if args:
            # Parse args string and add to params
            for arg in args.split('&'):
                if '=' in arg:
                    key, value = arg.split('=', 1)
                    params[key.strip()] = value.strip()
        
        logging.info(f"Stylebook reverse geocoding: lat={lat}, lon={lon}, type={type}, project_slug={project_slug}, url={url}")
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        results = data.get("results", [])
        
        if results and len(results) > 0:
            logging.info(f"Stylebook reverse geocoding found result")
            return results[0]
        else:
            logging.info("Stylebook reverse geocoding returned no results")
            return None
            
    except Exception as e:
        logging.error(f"Error in Stylebook reverse geocoding: {str(e)}")
        return None

def format_geocoding_result_from_localize(input_str: str, localize_result: Dict[str, Any]) -> Optional[GeocodingResult]:
    """
    Convert a Stylebook API result to a GeocodingResult object matching Pelias/Geocodio format.
    
    Args:
        input_str (str): The original input string
        localize_result (Dict): Result from Stylebook API
        
    Returns:
        Optional[GeocodingResult]: The created geocoding result or None if conversion fails
    """
    try:
        # Extract bbox and calculate center point
        # Stylebook can return either "bbox" or "bounding_box", or geometry_json
        geometry_json = localize_result.get("geometry_json") or localize_result.get("geometry")
        bbox = localize_result.get("bbox") or localize_result.get("bounding_box", [])
        
        if geometry_json and isinstance(geometry_json, dict):
            # Use geometry_json if available (preferred)
            geom_type = geometry_json.get("type")
            coords = geometry_json.get("coordinates")
            if geom_type == "Polygon" and coords:
                # Extract bbox from polygon coordinates
                def extract_coords(coords_list):
                    coords_flat = []
                    for item in coords_list:
                        if isinstance(item, (int, float)):
                            continue
                        elif isinstance(item[0], (int, float)) and len(item) >= 2:
                            coords_flat.append((float(item[0]), float(item[1])))
                        else:
                            coords_flat.extend(extract_coords(item))
                    return coords_flat
                
                all_coords = extract_coords(coords)
                if all_coords:
                    lons = [c[0] for c in all_coords]
                    lats = [c[1] for c in all_coords]
                    bbox = [min(lons), min(lats), max(lons), max(lats)]
            elif geom_type == "Point" and coords and len(coords) >= 2:
                geometry = GeometryPoint(coordinates=[float(coords[0]), float(coords[1])])
            else:
                geometry = None
        
        if not geometry:
            if len(bbox) >= 4:
                # bbox format: [min_lon, min_lat, max_lon, max_lat] == [west, south, east, north]
                geometry = GeometryPolygon(
                    coordinates=bbox_west_south_east_north_to_polygon_coordinates(
                        [float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])]
                    ),
                )
            else:
                # If no bbox, try to get a point from lat/lon
                lat = localize_result.get("lat") or localize_result.get("latitude")
                lon = localize_result.get("lon") or localize_result.get("longitude")
                
                if lat is not None and lon is not None:
                    geometry = GeometryPoint(coordinates=[float(lon), float(lat)])
                else:
                    logging.warning(f"Stylebook result missing geometry data: {localize_result}")
                    return None
        
        # Get formatted address or label
        formatted_address = localize_result.get("label") or localize_result.get("name") or input_str
        
        # Get ID from stylebook result
        result_id = localize_result.get("id")
        if result_id:
            result_id = f"stylebook:{result_id}"
        
        # Create the result data
        result_data = GeocodingResultData(
            id=result_id,
            processed_str=formatted_address,
            geometry=geometry,
            confidence={},  # Empty dict for now, can be populated if stylebook provides confidence
        )
        
        # Create and return the geocoding result
        return GeocodingResult(
            geocoder="stylebook",
            input_str=input_str,
            result=result_data
        )
        
    except Exception as e:
        logging.error(f"Error formatting stylebook result: {str(e)}")
        return None