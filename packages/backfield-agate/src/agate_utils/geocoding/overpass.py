"""Overpass API utilities for intersection geocoding."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import httpx
import overpy
from shapely.geometry import LineString, Point

from agate_utils.llm import call_llm

logger = logging.getLogger(__name__)

# Initialize Overpass API (URL + parse_json only; HTTP uses httpx with a real User-Agent).
api = overpy.Overpass()

# Public Overpass endpoints reject anonymous urllib defaults with 406; identify the client.
_DEFAULT_OVERPASS_USER_AGENT = "Backfield/1.0 (intersection geocode; Overpass API)"
_DEFAULT_OVERPASS_MIRRORS: tuple[str, ...] = (
    "https://lz4.overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)
_RETRYABLE_HTTP_STATUSES: frozenset[int] = frozenset({429, 502, 503, 504})
_DEFAULT_RETRY_DELAY_S = 4.0
_MAX_RETRY_DELAY_S = 60.0
_overpass_semaphore: threading.Semaphore | None = None


def _overpass_user_agent() -> str:
    ua = os.environ.get("OVERPASS_USER_AGENT", _DEFAULT_OVERPASS_USER_AGENT).strip()
    return ua or _DEFAULT_OVERPASS_USER_AGENT


def _overpass_endpoint_urls() -> list[str]:
    """Primary Overpass interpreter URL plus optional mirrors (deduped, ordered)."""
    primary = os.environ.get("OVERPASS_API_URL", "").strip() or api.url
    mirrors_raw = os.environ.get("OVERPASS_MIRROR_URLS", "").strip()
    if mirrors_raw:
        mirrors = [part.strip() for part in mirrors_raw.split(",") if part.strip()]
    else:
        mirrors = list(_DEFAULT_OVERPASS_MIRRORS)
    urls: list[str] = []
    for candidate in (primary, *mirrors):
        if candidate and candidate not in urls:
            urls.append(candidate)
    return urls


def _overpass_max_concurrent() -> int:
    raw = os.environ.get("OVERPASS_MAX_CONCURRENT", "1").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 1


def _overpass_query_stagger_s() -> float:
    raw = os.environ.get("OVERPASS_QUERY_STAGGER_S", "1.0").strip()
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 1.0


def _overpass_semaphore() -> threading.Semaphore:
    global _overpass_semaphore
    if _overpass_semaphore is None:
        _overpass_semaphore = threading.Semaphore(_overpass_max_concurrent())
    return _overpass_semaphore


@contextmanager
def _overpass_request_slot() -> Iterator[None]:
    sem = _overpass_semaphore()
    sem.acquire()
    try:
        yield
    finally:
        sem.release()


def _looks_like_overpass_json(body: bytes) -> bool:
    stripped = body.lstrip()
    return stripped.startswith(b"{") or stripped.startswith(b"[")


def _is_retryable_http_status(status_code: int) -> bool:
    return status_code in _RETRYABLE_HTTP_STATUSES


def _retry_delay_seconds(
    *,
    response: httpx.Response | None,
    attempt: int,
    base_delay_s: float,
    rate_limited: bool,
) -> float:
    """Compute backoff; honor Retry-After when the server sends it."""
    if response is not None:
        retry_after = response.headers.get("Retry-After", "").strip()
        if retry_after:
            if retry_after.isdigit():
                return min(float(retry_after), _MAX_RETRY_DELAY_S)
            try:
                retry_at = parsedate_to_datetime(retry_after)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=UTC)
                delta = (retry_at.timestamp() - time.time())
                if delta > 0:
                    return min(delta, _MAX_RETRY_DELAY_S)
            except (TypeError, ValueError, OverflowError):
                pass
    multiplier = 2 ** max(0, attempt - 1)
    floor = 8.0 if rate_limited else base_delay_s
    return min(floor * multiplier, _MAX_RETRY_DELAY_S)


def _response_error_summary(response: httpx.Response) -> str:
    body_preview = response.text[:300] if response.text else "(empty body)"
    return f"HTTP {response.status_code}: {body_preview!r}"


def _parse_overpass_response(content: bytes) -> overpy.Result:
    if not _looks_like_overpass_json(content):
        preview = content[:200].decode("utf-8", errors="replace")
        raise ValueError(f"Overpass response is not JSON (starts with {preview[:80]!r})")
    return api.parse_json(content)


########## INTERSECTION PARSING ##########

def parse_intersection_description(text: str, openai_api_key: str) -> dict[str, Any] | None:
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
        with open(prompt_path) as f:
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
    alternates: list[str] | None = None
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
        with open(prompt_path) as f:
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

def run_query_with_overpy(query: str, max_retries: int = 4) -> overpy.Result | None:
    """
    Execute an OverpassQL query with retry logic, mirror fallback, and throttling.

    Uses httpx with a descriptive User-Agent (override with OVERPASS_USER_AGENT); overpy's
    default urllib client sends no User-Agent and is often rejected with HTTP 406.

    Env:
        OVERPASS_API_URL: primary interpreter (default: overpy public endpoint)
        OVERPASS_MIRROR_URLS: comma-separated fallback interpreters
        OVERPASS_MAX_CONCURRENT: max in-flight requests per worker process (default 1)
        OVERPASS_USER_AGENT: HTTP User-Agent header

    Args:
        query: OverpassQL query to execute
        max_retries: Maximum retry attempts per endpoint

    Returns:
        Optional[overpy.Result]: Query result or None if failed
    """
    urls = _overpass_endpoint_urls()
    qbytes = query.encode("utf-8") if isinstance(query, str) else query
    timeout = httpx.Timeout(180.0)
    headers = {
        "User-Agent": _overpass_user_agent(),
        "Accept": "application/json",
    }

    with _overpass_request_slot():
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            for url_index, url in enumerate(urls):
                base_delay_s = _DEFAULT_RETRY_DELAY_S
                for attempt in range(max_retries):
                    attempt_no = attempt + 1
                    try:
                        logger.info(
                            "Executing Overpass query (endpoint %s/%s, attempt %s/%s)",
                            url_index + 1,
                            len(urls),
                            attempt_no,
                            max_retries,
                        )
                        response = client.post(url, content=qbytes, headers=headers)

                        if response.status_code == 200:
                            try:
                                return _parse_overpass_response(response.content)
                            except (ValueError, json.JSONDecodeError) as parse_exc:
                                logger.warning(
                                    "Overpass non-JSON body on attempt %s at %s: %s",
                                    attempt_no,
                                    url,
                                    parse_exc,
                                )
                                if attempt >= max_retries - 1:
                                    break
                                delay = _retry_delay_seconds(
                                    response=response,
                                    attempt=attempt_no,
                                    base_delay_s=base_delay_s,
                                    rate_limited=True,
                                )
                                logger.info("Retrying in %.1f seconds...", delay)
                                time.sleep(delay)
                                continue

                        if response.status_code == 400:
                            logger.error(
                                "Overpass bad request (HTTP 400) at %s: %s",
                                url,
                                response.text[:800] if response.text else "(empty body)",
                            )
                            logger.error(
                                "This is a query problem, retrying won't help. Bailing out."
                            )
                            return None

                        err_summary = _response_error_summary(response)
                        rate_limited = response.status_code == 429
                        if _is_retryable_http_status(response.status_code):
                            logger.warning(
                                "Overpass server error on attempt %s at %s: %s",
                                attempt_no,
                                url,
                                err_summary,
                            )
                        else:
                            logger.warning(
                                "Overpass error on attempt %s at %s: %s",
                                attempt_no,
                                url,
                                err_summary,
                            )

                        if attempt >= max_retries - 1:
                            break

                        delay = _retry_delay_seconds(
                            response=response,
                            attempt=attempt_no,
                            base_delay_s=base_delay_s,
                            rate_limited=rate_limited,
                        )
                        logger.info("Retrying in %.1f seconds...", delay)
                        time.sleep(delay)
                        continue

                    except httpx.TimeoutException as exc:
                        logger.warning(
                            "Overpass timeout on attempt %s at %s: %s",
                            attempt_no,
                            url,
                            exc,
                        )
                        if attempt >= max_retries - 1:
                            break
                        delay = _retry_delay_seconds(
                            response=None,
                            attempt=attempt_no,
                            base_delay_s=base_delay_s,
                            rate_limited=False,
                        )
                        logger.info("Retrying in %.1f seconds...", delay)
                        time.sleep(delay)
                    except Exception as exc:
                        error_str = str(exc).lower()
                        if "bad request" in error_str or "syntax" in error_str:
                            logger.error("Overpass bad request - query syntax error: %s", exc)
                            logger.error(
                                "This is a query problem, retrying won't help. Bailing out."
                            )
                            return None
                        if (
                            "gateway timeout" in error_str
                            or "server load" in error_str
                            or "timeout" in error_str
                        ):
                            logger.warning(
                                "Overpass server error on attempt %s at %s: %s",
                                attempt_no,
                                url,
                                exc,
                            )
                        else:
                            logger.warning(
                                "Overpass error on attempt %s at %s: %s",
                                attempt_no,
                                url,
                                exc,
                            )
                        if attempt >= max_retries - 1:
                            break
                        delay = _retry_delay_seconds(
                            response=None,
                            attempt=attempt_no,
                            base_delay_s=base_delay_s,
                            rate_limited=False,
                        )
                        logger.info("Retrying in %.1f seconds...", delay)
                        time.sleep(delay)

                if url_index < len(urls) - 1:
                    logger.warning(
                        "Overpass endpoint exhausted (%s); trying mirror %s",
                        url,
                        urls[url_index + 1],
                    )

            logger.error("Max retries exceeded for Overpass query across all endpoints")
            return None


########## GEOMETRIC OPERATIONS ##########

def linestrings_from_ways(result: overpy.Result) -> list[LineString]:
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


def find_geometric_intersections(result1: overpy.Result, result2: overpy.Result) -> list[Point]:
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

async def estimate_overpass_parameters(
    address_text: str, openai_api_key: str
) -> tuple[float, float, int] | None:
    """
    Estimate plausible latitude, longitude, and search radius for an address.
    This is useful for setting up Overpass queries when we don't have precise coordinates.
    
    Args:
        address_text: Address string like "Hiawatha Ave. Minneapolis MN"
        openai_api_key: OpenAI API key for LLM calls
        
    Returns:
        (latitude, longitude, radius_meters) if successful, None otherwise
    """
    try:
        # Load the prompt template
        prompt_path = Path(__file__).parent / "prompts" / "estimate_overpass_parameters.md"
        with open(prompt_path) as f:
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
                logger.info(
                    "Estimated search parameters for %s: lat=%s, lon=%s, radius=%sm",
                    address_text,
                    lat,
                    lon,
                    radius,
                )
                return (lat, lon, radius)
            else:
                logger.warning(
                    "LLM returned invalid parameters for %s: lat=%s, lon=%s, radius=%s",
                    address_text,
                    lat,
                    lon,
                    radius,
                )
                return None
        else:
            logger.warning(f"LLM response missing required fields for {address_text}")
            return None
    except Exception as e:
        logger.error(f"Error estimating search parameters for {address_text}: {e}")
        return None


def choose_most_plausible_intersection(
    input_string: str,
    candidates: list[Point],
    openai_api_key: str,
    max_candidates: int = 10
) -> Point | None:
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
        with open(prompt_path) as f:
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
    radius: int | None = None,
    alt_map: dict[str, list[str]] | None = None,
    orig_text: str | None = None
) -> tuple[list[dict[str, Any]], list[str]]:
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
    query1 = generate_single_road_query_with_llm(
        road_1, lat, lon, openai_api_key, radius, alternates=alt_map.get(road_1, [])
    )
    query2 = generate_single_road_query_with_llm(
        road_2, lat, lon, openai_api_key, radius, alternates=alt_map.get(road_2, [])
    )

    logger.info(f"Generated query for road 1 ({road_1}):")
    logger.info(query1)
    logger.info(f"Generated query for road 2 ({road_2}):")
    logger.info(query2)
    
    # Collect queries for meta output
    queries = [query1, query2]

    # Execute queries (stagger the second request to reduce 429s on public mirrors)
    logger.info("Executing Overpass queries...")
    result1 = run_query_with_overpy(query1)
    stagger_s = _overpass_query_stagger_s()
    if stagger_s > 0:
        time.sleep(stagger_s)
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
    radius: int | None = None
) -> tuple[list[dict[str, Any]], list[str]]:
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

    logger.info(
        "Parsed intersection: %s and %s near %s, %s",
        road_1,
        road_2,
        parsed["city"],
        parsed["state"],
    )
    logger.info(f"Location: lat={lat}, lon={lon}")
    logger.info(f"Alternate names: {alt_map}")

    results, queries = await find_intersection_coordinates(
        road_1, road_2, lat, lon, openai_api_key, radius, 
        alt_map=alt_map, orig_text=intersection_text
    )
    return results, queries

