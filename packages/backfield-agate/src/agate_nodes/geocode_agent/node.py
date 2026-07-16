"""GeocodeAgent node for intelligent geocoding using LLM reasoning."""

import os
import asyncio
import time
import logging
from typing import List, Dict, Any, Optional, Tuple
from pydantic import AliasChoices, BaseModel, Field, ConfigDict, model_validator

from agate_runtime.context import AgateEnvContext
from agate_runtime.upstream_input import flatten_upstream_inputs

from .agent import run_advanced_geocoding_agent
from .location_limits import location_needs_review_entry, split_locations_for_geocoding
from .place_dedupe import deduplicate_consolidated_places

logger = logging.getLogger(__name__)

# Get Celery timeout limits from environment (defaults match worker/tasks.py)
TASK_SOFT_TIME_LIMIT = int(os.getenv("TASK_SOFT_TIME_LIMIT", "3600"))  # 60 minutes default


def _flatten_executor_upstream_inputs(state: Dict[str, Any]) -> Dict[str, Any]:
    """Hoist per-upstream payloads to top level (parity with PlaceExtract / Backfield executor)."""
    return flatten_upstream_inputs(state)


########## AGENT MODELS ##########

class GeocodeAgentInput(BaseModel):
    """Input schema - expects to find locations in namespaced state."""
    model_config = ConfigDict(extra='allow')

class GeocodeAgentParams(BaseModel):
    """Parameters for GeocodeAgent node."""

    maxLocations: int = Field(
        default=200,
        ge=1,
        le=1000,
        description="Maximum number of locations to process per run (prevents timeouts, default: 200)"
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
    stylebookId: Optional[int] = Field(
        default=None,
        validation_alias=AliasChoices("stylebookId", "stylebook_id"),
        description="Stylebook id for DB-backed cache (worker: BACKFIELD_PROJECT_ID + useCache)",
    )
    evaluationModel: str = Field(
        default="gpt-5-nano",
        description="OpenAI model for judging ambiguous geocoder results and refining location display lines",
    )
    geographicReasoningModel: str = Field(
        default="gpt-5-nano",
        description=(
            "OpenAI model for geographic research and decision-making during external geocode "
            "(place addressability, search queries, candidate selection)"
        ),
    )
    geographicEstimationModel: str = Field(
        default="gpt-5-nano",
        description=(
            "OpenAI model for LLM geometry estimation when geocoders cannot resolve a location "
            "(intersection points, region/street/natural bounding boxes)"
        ),
    )
    routerModel: str = Field(
        default="gpt-5-nano",
        description="OpenAI model for post-cache route_strategy JSON",
    )
    evaluationAiModelConfigId: Optional[str] = Field(
        default=None,
        description="Optional Backfield AI model config id (overrides evaluationModel when set)",
    )
    geographicReasoningAiModelConfigId: Optional[str] = Field(
        default=None,
        description="Optional Backfield AI model config id (overrides geographicReasoningModel when set)",
    )
    geographicEstimationAiModelConfigId: Optional[str] = Field(
        default=None,
        description="Optional Backfield AI model config id (overrides geographicEstimationModel when set)",
    )
    routerAiModelConfigId: Optional[str] = Field(
        default=None,
        description="Optional Backfield AI model config id (overrides routerModel when set)",
    )
    useCacheLlmAdjudication: bool = Field(
        default=True,
        description=(
            "When useCache and DB bundle are active: run evaluation LLM on ambiguous tier-1 "
            "or tier-2 sanity failures before external geocoding"
        ),
    )
    useCacheLlmAdjudicationOnMissRecall: bool = Field(
        default=False,
        description=(
            "When useCache and DB bundle: also run adjudication on strict cache miss "
            "if trigram recall returns canonical candidates (extra LLM cost)"
        ),
    )

    @model_validator(mode="after")
    def _coerce_empty_model_strings(self) -> "GeocodeAgentParams":
        """Saved graphs may persist empty strings, which override Field defaults and break routing."""
        defaults = (
            ("evaluationModel", "gpt-5-nano"),
            ("routerModel", "gpt-5-nano"),
            ("geographicReasoningModel", "gpt-5-nano"),
            ("geographicEstimationModel", "gpt-5-nano"),
        )
        updates: dict[str, str] = {}
        for key, default in defaults:
            raw = getattr(self, key)
            if not (str(raw) if raw is not None else "").strip():
                updates[key] = default
        if updates:
            return self.model_copy(update=updates)
        return self


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


async def run_geocode_agent_pipeline(
    inp: GeocodeAgentInput,
    params: GeocodeAgentParams,
    ctx: AgateEnvContext,
    *,
    log_label: str = "GeocodeAgent",
) -> GeocodeAgentOutput:
    """Geocode locations using the LangGraph pipeline (cache → route_strategy → external geocode → consolidate)."""

    def _pipe_log(msg: str, *args: object) -> None:
        logger.debug(msg, *args)

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
        _pipe_log("No locations found in input state. Returning empty places structure.")
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
        _pipe_log("Empty locations list found. Returning empty places structure.")
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
        # PlaceExtract ``political_district`` (wards, legislative districts, etc.):
        # must pass through so Stylebook cache + Region geocode path can run.
        "political_district",
    ]
    filtered_locations = [
        loc for loc in locations_data 
        if loc.get('location', {}).get('type', '').lower() in supported_types
    ]

    skipped_count = len(locations_data) - len(filtered_locations)
    if skipped_count > 0:
        _pipe_log("Skipping %s location(s) with unsupported types", skipped_count)

    # Show what types we're processing
    types_being_processed = set(loc.get('location', {}).get('type', '').lower() for loc in filtered_locations)
    _pipe_log(
        "Processing %s location(s) of type: %s",
        len(filtered_locations),
        ", ".join(types_being_processed),
    )
        
    # Get API keys from context
    pelias_api_key = ctx.get_api_key("PELIAS_API_KEY")
    geocodio_api_key = ctx.get_api_key("GEOCODIO_API_KEY")
    openai_api_key = ctx.get_api_key("OPENAI_API_KEY")
    brave_search_api_key = ctx.get_api_key("BRAVE_SEARCH_API_KEY")
    service_api_token = ctx.get_api_key("SERVICE_API_TOKEN")

    eval_lm_model = params.evaluationModel
    router_lm_model = params.routerModel
    geo_lm_model = params.geographicReasoningModel
    geo_est_lm_model = params.geographicEstimationModel
    raw_pid = os.getenv("BACKFIELD_PROJECT_ID")
    if raw_pid:
        try:
            from backfield_ai.model_resolve import resolve_geocode_litellm_models
            from backfield_db.session import get_engine
            from sqlmodel import Session

            with Session(get_engine()) as res_sess:
                eval_lm_model, router_lm_model, geo_lm_model, geo_est_lm_model = (
                    resolve_geocode_litellm_models(
                        res_sess,
                        int(raw_pid),
                        params,
                    )
                )
        except Exception as exc:
            logger.warning(
                "Could not resolve catalog AI models for GeocodeAgent; using legacy ids: %s",
                exc,
            )

    # Get cache parameters
    stylebook_api_url = params.stylebookApiUrl or os.environ.get("STYLEBOOK_API_URL")
    project_slug = params.projectSlug or os.environ.get("PROJECT_SLUG")
    meta = ctx.metadata if isinstance(ctx.metadata, dict) else {}
    raw_resolve = meta.get("cache_resolve")
    cache_resolve = raw_resolve if callable(raw_resolve) else None
    geocode_cache_bundle = meta.get("geocode_cache_bundle")
    cache_bundle = geocode_cache_bundle if isinstance(geocode_cache_bundle, dict) else None
        
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
        
    # Limit number of locations to process; overflow goes to needs_review.
    locations_to_process, overflow_locations = split_locations_for_geocoding(
        filtered_locations,
        MAX_LOCATIONS,
    )
    if overflow_locations:
        logger.warning(
            "Limiting processing to first %s of %s locations; %s overflow row(s) moved to needs_review",
            MAX_LOCATIONS,
            len(filtered_locations),
            len(overflow_locations),
        )
        skipped_count = len(overflow_locations)
        for overflow_loc in overflow_locations:
            all_consolidated_places["needs_review"].append(
                location_needs_review_entry(
                    overflow_loc,
                    f"Skipped: exceeded maxLocations limit ({MAX_LOCATIONS})",
                )
            )

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
            _pipe_log(
                "Processing [%s/%s]: %s (type: %s)",
                idx + 1,
                len(locations_to_process),
                location_name,
                location_info.get("type", ""),
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
                
            consolidated_result = await asyncio.wait_for(
                run_advanced_geocoding_agent(
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
                    service_api_token=service_api_token,
                    cache_resolve=cache_resolve,
                    geocode_cache_bundle=cache_bundle,
                    use_cache_llm_ambiguous_sanity=params.useCacheLlmAdjudication,
                    use_cache_llm_miss_recall=params.useCacheLlmAdjudicationOnMissRecall,
                    evaluation_llm_model=eval_lm_model,
                    router_llm_model=router_lm_model,
                    geographic_reasoning_llm_model=geo_lm_model,
                    geographic_estimation_llm_model=geo_est_lm_model,
                    evaluation_ai_model_config_id=params.evaluationAiModelConfigId,
                    router_ai_model_config_id=params.routerAiModelConfigId,
                    geographic_reasoning_ai_model_config_id=params.geographicReasoningAiModelConfigId,
                    geographic_estimation_ai_model_config_id=params.geographicEstimationAiModelConfigId,
                ),
                timeout=PER_LOCATION_TIMEOUT,
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
            all_consolidated_places["needs_review"].append(
                location_needs_review_entry(
                    skipped_loc,
                    f"Skipped due to approaching Celery timeout (elapsed {elapsed_time:.1f}s)",
                )
            )
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
                all_consolidated_places["needs_review"].append(
                    location_needs_review_entry(loc, error_msg)
                )
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
                    
                _pipe_log("Success: %s", location_name)
                processed_count += 1
            else:
                logger.warning(f"No result for: {location_name}")
                processed_count += 1  # Still count as processed even if no result
        
    total_time = time.time() - start_time
    logger.info(
        f"{log_label} completed: {processed_count} processed, {timeout_count} timed out, "
        f"{skipped_count} skipped, total time: {total_time:.1f}s"
    )

    all_consolidated_places = deduplicate_consolidated_places(all_consolidated_places)

    # Return flattened carry-through fields + ``places`` so DBOutput sees article metadata.
    output_data = {
        **flat_state,
        "places": all_consolidated_places,
    }
    if text:
        output_data["text"] = text

    return GeocodeAgentOutput(**output_data)


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
        from .runner import attach_geocode_cache_bundle

        attach_geocode_cache_bundle(
            ctx,
            use_cache=params.useCache,
            stylebook_id=params.stylebookId,
        )
        return await run_geocode_agent_pipeline(inp, params, ctx)
