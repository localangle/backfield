"""GeocodeAgent node for intelligent geocoding using LLM reasoning."""

import os
import asyncio
import time
import logging
from typing import List, Dict, Any, Optional, Tuple
from pydantic import BaseModel, Field, ConfigDict

from agate_runtime.context import AgateEnvContext

from .agent import run_geocoding_agent

logger = logging.getLogger(__name__)

# Get Celery timeout limits from environment (defaults match worker/tasks.py)
TASK_SOFT_TIME_LIMIT = int(os.getenv("TASK_SOFT_TIME_LIMIT", "3600"))  # 60 minutes default


def _flatten_executor_upstream_inputs(state: Dict[str, Any]) -> Dict[str, Any]:
    """Hoist per-upstream payloads to top level (parity with PlaceExtract / Backfield executor).

    The graph executor namespaces each direct upstream output by source node id. Without
    flattening, article fields like ``headline`` and ``url`` stay nested and DBOutput's
    shallow merge never sees them for ``substrate_article`` upserts.
    """

    flattened: Dict[str, Any] = {}
    for key, value in state.items():
        is_node_key = key.startswith("node-") and len(key) > 5 and key[5:].isdigit()
        if is_node_key and isinstance(value, dict):
            flattened.update(value)
        elif isinstance(value, dict):
            flattened.update(value)
        else:
            flattened[key] = value
    return flattened


########## AGENT MODELS ##########

class GeocodeAgentInput(BaseModel):
    """Input schema - expects to find locations in namespaced state."""
    model_config = ConfigDict(extra='allow')

class GeocodeAgentParams(BaseModel):
    """Parameters for GeocodeAgent node."""
    maxLocations: int = Field(
        default=100,
        ge=1,
        le=1000,
        description="Maximum number of locations to process per run (prevents timeouts, default: 100)"
    )
    perLocationTimeout: int = Field(
        default=300,
        ge=30,
        le=1800,
        description="Timeout in seconds for each individual location (default: 5 minutes)"
    )
    useCache: bool = Field(
        default=False,
        description="Use Stylebook canonical matching and location cache before external geocoding"
    )
    stylebookApiUrl: Optional[str] = Field(
        default=None,
        description="Stylebook API URL for canonical matching (defaults to STYLEBOOK_API_URL env var)"
    )
    projectSlug: Optional[str] = Field(
        default=None,
        description="Project slug for canonical matching (defaults to PROJECT_SLUG env var)"
    )

# Define Place model locally to avoid cross-node dependencies
# This is a simplified Place model that only includes the fields actually used by the geocode_agent
class Place(BaseModel):
    """Place with optional geocoding data."""
    original_text: str = Field(description="Original text mentioning this place")
    description: str = Field(description="Description of the place in context")
    location: Dict[str, Any] = Field(description="Location information as a dictionary")
    geocoding: Optional[Dict[str, Any]] = Field(default=None, description="Geocoding data if available")

class GeocodeAgentOutput(BaseModel):
    """Output schema - passes through all state with consolidated places structure."""
    model_config = ConfigDict(extra='allow')
    
    places: Dict[str, Any] = Field(description="Consolidated places structure with areas, points, etc.")

########## AGENT NODE ##########

class GeocodeAgent:
    """
    An intelligent geocoding node that uses LLM reasoning to improve geocoding results.
    """

    name = "GeocodeAgent"
    version = "0.1.0"
    category = "enrichment"

    Input = GeocodeAgentInput
    Output = GeocodeAgentOutput
    Params = GeocodeAgentParams

    async def run(
        self,
        inp: GeocodeAgentInput,
        params: GeocodeAgentParams,
        ctx: AgateEnvContext,
    ) -> GeocodeAgentOutput:
        """
        Geocode locations using LLM-enhanced geocoding with intelligent fallback.
        
        Currently supports city, state, and county location types.
        Uses sequential fallback: Nominatim → (LLM evaluation) → Pelias if needed.
        """
        # Get all state (namespaced by upstream node id from the Backfield executor)
        state_dict = inp.model_dump()
        flat_state = _flatten_executor_upstream_inputs(state_dict)

        # Prefer flattened text / locations (single upstream is typical)
        text = flat_state.get("text") if isinstance(flat_state.get("text"), str) else None
        if not text:
            for _key, value in state_dict.items():
                if isinstance(value, dict) and "text" in value:
                    candidate_text = value["text"]
                    if isinstance(candidate_text, str):
                        text = candidate_text
                        break

        locations_data = flat_state.get("locations")
        if locations_data is None:
            for _key, value in state_dict.items():
                if isinstance(value, dict) and "locations" in value:
                    locations_data = value["locations"]
                    break

        # If no locations found, return empty places structure
        if not locations_data:
            logger.info("No locations found in input state. Returning empty places structure.")
            output_data = {
                **flat_state,
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
            # Include text at root level if found
            if text:
                output_data["text"] = text
            return GeocodeAgentOutput(**output_data)
        
        # Handle empty locations list
        if not isinstance(locations_data, list) or len(locations_data) == 0:
            logger.info("Empty locations list found. Returning empty places structure.")
            output_data = {
                **flat_state,
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
            # Include text at root level if found
            if text:
                output_data["text"] = text
            return GeocodeAgentOutput(**output_data)
        
        # Filter for supported types
        supported_types = [
            "state",
            "county",
            "city",
            "neighborhood",
            "address",
            "place",
            "intersection_road",
            "intersection_highway",
            "street_road",
            "span",
            "region",
            "region_city",
            "region_state",
            "region_national",
            "natural",
        ]
        filtered_locations = [
            loc for loc in locations_data 
            if loc.get('location', {}).get('type', '').lower() in supported_types
        ]
        
        skipped_count = len(locations_data) - len(filtered_locations)
        if skipped_count > 0:
            logger.info(f"Skipping {skipped_count} location(s) with unsupported types")
        
        # Show what types we're processing
        types_being_processed = set(loc.get('location', {}).get('type', '').lower() for loc in filtered_locations)
        logger.info(f"Processing {len(filtered_locations)} location(s) of type: {', '.join(types_being_processed)}")
        
        # Get API keys from context
        pelias_api_key = ctx.get_api_key("PELIAS_API_KEY")
        geocodio_api_key = ctx.get_api_key("GEOCODIO_API_KEY")
        openai_api_key = ctx.get_api_key("OPENAI_API_KEY")
        brave_search_api_key = ctx.get_api_key("BRAVE_SEARCH_API_KEY")
        service_api_token = ctx.get_api_key("SERVICE_API_TOKEN")
        
        # Get cache parameters
        stylebook_api_url = params.stylebookApiUrl or os.environ.get("STYLEBOOK_API_URL")
        project_slug = params.projectSlug or os.environ.get("PROJECT_SLUG")
        
        # Configuration for timeout handling
        PER_LOCATION_TIMEOUT = params.perLocationTimeout
        MAX_LOCATIONS = params.maxLocations
        CELERY_TIMEOUT_BUFFER = 300  # Stop 5 minutes before Celery timeout to allow cleanup
        
        # Process each location through the agent and collect consolidated results
        all_consolidated_places = {
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
        
        # Track processing stats
        start_time = time.time()
        processed_count = 0
        skipped_count = 0
        timeout_count = 0
        
        # Limit number of locations to process
        locations_to_process = filtered_locations[:MAX_LOCATIONS]
        if len(filtered_locations) > MAX_LOCATIONS:
            logger.warning(f"Limiting processing to first {MAX_LOCATIONS} of {len(filtered_locations)} locations")
            skipped_count = len(filtered_locations) - MAX_LOCATIONS
        
        # Concurrency limit for parallel processing (default: 5 concurrent geocoding requests)
        MAX_CONCURRENT = int(os.getenv("GEOCODE_MAX_CONCURRENT", "5"))
        
        async def process_single_location(loc: dict, idx: int) -> Tuple[dict, Optional[dict], Optional[str]]:
            """
            Process a single location and return (location_dict, result, error).
            
            Returns:
                (loc, consolidated_result, error_message)
            """
            location_info = loc.get('location', {})
            location_name = location_info.get('full', '')
            
            try:
                logger.info(
                    f"Processing [{idx+1}/{len(locations_to_process)}]: "
                    f"{location_name} (type: {location_info.get('type', '')})"
                )
                
                # Extract extra fields (everything except nested location + verbatim quote).
                extra_fields = {
                    key: value
                    for key, value in loc.items()
                    if key not in ("location", "original_text")
                }
                # ``components`` live under ``location`` in PlaceExtract output; copy for DBOutput persistence.
                if isinstance(location_info, dict):
                    comps = location_info.get("components")
                    if isinstance(comps, dict):
                        extra_fields = {**extra_fields, "components": comps}
                
                # Run the agent for this location with per-location timeout
                consolidated_result = await asyncio.wait_for(
                    run_geocoding_agent(
                        location_text=location_name,
                        location_type=location_info.get('type', ''),
                        location_components=location_info.get('components', {}),
                        original_text=loc.get('original_text', ''),
                        extra_fields=extra_fields,
                        pelias_api_key=pelias_api_key,
                        brave_search_api_key=brave_search_api_key,
                        geocodio_api_key=geocodio_api_key,
                        openai_api_key=openai_api_key,
                        use_cache=params.useCache,
                        stylebook_api_url=stylebook_api_url,
                        project_slug=project_slug,
                        service_api_token=service_api_token
                    ),
                    timeout=PER_LOCATION_TIMEOUT
                )
                
                return (loc, consolidated_result, None)
                
            except asyncio.TimeoutError:
                logger.warning(
                    f"Location {location_name} exceeded {PER_LOCATION_TIMEOUT}s timeout. "
                    f"Skipping and adding to needs_review."
                )
                return (loc, None, f"Geocoding timeout after {PER_LOCATION_TIMEOUT}s")
                
            except Exception as e:
                logger.error(f"Error geocoding {location_name}: {str(e)}")
                return (loc, None, str(e))
        
        # Check timeout before starting parallel processing
        elapsed_time = time.time() - start_time
        remaining_time = TASK_SOFT_TIME_LIMIT - elapsed_time
        
        if remaining_time < CELERY_TIMEOUT_BUFFER:
            logger.warning(
                f"Approaching Celery timeout before starting (elapsed: {elapsed_time:.1f}s, remaining: {remaining_time:.1f}s). "
                f"Skipping all {len(locations_to_process)} locations."
            )
            skipped_count += len(locations_to_process)
            # Add skipped locations to needs_review
            for skipped_loc in locations_to_process:
                location_info = skipped_loc.get('location', {})
                all_consolidated_places["needs_review"].append({
                    "original_text": skipped_loc.get('original_text', ''),
                    "location": location_info,
                    "error": f"Skipped due to approaching Celery timeout (elapsed {elapsed_time:.1f}s)"
                })
        else:
            # Process locations in parallel with concurrency limit
            semaphore = asyncio.Semaphore(MAX_CONCURRENT)
            
            async def process_with_semaphore(loc: dict, idx: int):
                """Process a location with semaphore to limit concurrency."""
                async with semaphore:
                    return await process_single_location(loc, idx)
            
            # Create tasks for all locations (semaphore will limit concurrent execution)
            tasks = [
                process_with_semaphore(loc, idx)
                for idx, loc in enumerate(locations_to_process)
            ]
            
            # Process all tasks in parallel (semaphore ensures max concurrency)
            # Use return_exceptions=True so one failure doesn't stop others
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"Unexpected error in parallel processing: {result}")
                    processed_count += 1
                    continue
                
                loc, consolidated_result, error_msg = result
                location_info = loc.get('location', {})
                location_name = location_info.get('full', '')
                
                if error_msg:
                    # Handle timeout or error
                    if "timeout" in error_msg.lower():
                        timeout_count += 1
                    all_consolidated_places["needs_review"].append({
                        "original_text": loc.get('original_text', ''),
                        "location": location_info,
                        "error": error_msg
                    })
                    processed_count += 1
                elif consolidated_result and consolidated_result.get("places"):
                    places = consolidated_result["places"]
                    
                    # Merge the consolidated results with deduplication
                    for area_type in ["states", "counties", "cities", "neighborhoods", "regions", "other"]:
                        if places.get("areas", {}).get(area_type):
                            # Get existing IDs to avoid duplicates
                            existing_ids = {item.get("id") for item in all_consolidated_places["areas"][area_type] if item.get("id")}
                            
                            # Only add items that don't already exist
                            for item in places["areas"][area_type]:
                                if item.get("id") not in existing_ids:
                                    all_consolidated_places["areas"][area_type].append(item)
                                    existing_ids.add(item.get("id"))
                    
                    if places.get("points"):
                        all_consolidated_places["points"].extend(places["points"])
                    
                    if places.get("needs_review"):
                        all_consolidated_places["needs_review"].extend(places["needs_review"])
                    
                    logger.info(f"Success: {location_name}")
                    processed_count += 1
                else:
                    logger.warning(f"No result for: {location_name}")
                    processed_count += 1  # Still count as processed even if no result
        
        total_time = time.time() - start_time
        logger.info(
            f"GeocodeAgent completed: {processed_count} processed, {timeout_count} timed out, "
            f"{skipped_count} skipped, total time: {total_time:.1f}s"
        )
        
        # Return flattened carry-through fields + ``places`` so DBOutput sees article metadata.
        output_data = {
            **flat_state,
            "places": all_consolidated_places,
        }
        if text:
            output_data["text"] = text

        return GeocodeAgentOutput(**output_data)
