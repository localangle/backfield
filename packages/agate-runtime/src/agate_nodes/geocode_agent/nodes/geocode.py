"""LangGraph geocode node for intelligent geocoding with fallback strategies."""

import os
import asyncio
import logging
from ..models import (
    State,
    County,
    City,
    Neighborhood,
    Address,
    Place,
    Intersection,
    StreetRoad,
    Span,
    Region,
    NaturalPlace,
)
from ..types import AgentState
from agate_utils.geocoding.localize import match_canonical_location, get_location_cache
from agate_utils.geocoding.geocoding_types import stylebook_match_to_geocoding_result, cache_match_to_geocoding_result

logger = logging.getLogger(__name__)

########## HELPER FUNCTIONS ##########

def _create_model(location_type: str, location_text: str, components: dict, state: AgentState):
    if location_type == "state":
        state_info = components.get("state", {})
        state_name = state_info.get("name") if isinstance(state_info, dict) else location_text
        return State(name=state_name, country="US")

    if location_type == "county":
        county_name = components.get("county", location_text)
        state_info = components.get("state", {})
        state_name = state_info.get("name") if isinstance(state_info, dict) else "Unknown"
        return County(name=county_name, state=state_name, country="US")

    if location_type == "city":
        city_name = components.get("city", location_text)
        state_info = components.get("state", {})
        state_name = state_info.get("name") if isinstance(state_info, dict) else "Unknown"
        county_name = components.get("county", "")
        return City(name=city_name, state=state_name, county=county_name, country="US")

    if location_type == "neighborhood":
        neighborhood_name = components.get("neighborhood", location_text)
        city_name = components.get("city", "")
        state_info = components.get("state", {})
        state_name = state_info.get("name") if isinstance(state_info, dict) else "Unknown"
        county_name = components.get("county", "")
        return Neighborhood(
            name=neighborhood_name,
            city=city_name,
            state=state_name,
            county=county_name,
            country="US",
        )

    if location_type == "address":
        address = components.get("address", location_text)
        city_name = components.get("city", "")
        state_info = components.get("state", {})
        state_abbr = state_info.get("abbr") if isinstance(state_info, dict) else None
        return Address(name=address, city=city_name, state_abbr=state_abbr, country="US")

    if location_type == "place":
        place_info = components.get("place", {})
        if isinstance(place_info, dict):
            place_name = place_info.get("name", location_text)
            is_addressable = place_info.get("addressable", None)
        else:
            place_name = str(place_info) if place_info else location_text
            is_addressable = None

        city_name = components.get("city", "")
        state_info = components.get("state", {})
        state_abbr = state_info.get("abbr") if isinstance(state_info, dict) else None
        model = Place(name=place_name, city=city_name, state_abbr=state_abbr, country="US")
        model._input_addressability = is_addressable
        model._original_text = state.get("original_text", "")
        return model

    if location_type in {"intersection_road", "intersection_highway"}:
        model = Intersection(name=location_text, country="US")
        model._original_text = state.get("original_text", "")
        return model

    if location_type == "street_road":
        street_road_info = components.get("street_road", {})
        if isinstance(street_road_info, dict) and street_road_info.get("name"):
            street_name = street_road_info.get("name")
        else:
            street_name = location_text

        city_name = components.get("city", "")
        state_info = components.get("state", {})
        state_abbr = state_info.get("abbr") if isinstance(state_info, dict) else ""
        return StreetRoad(name=street_name, city=city_name, state=state_abbr, country="US")

    if location_type.startswith("region"):
        extra_context_parts = []
        if state.get("original_text"):
            extra_context_parts.append(f"Original text: {state['original_text']}")
        extra_fields = state.get("extra_fields") or {}
        description = extra_fields.get("description")
        if description:
            extra_context_parts.append(f"Description: {description}")
        additional_context = "\n".join(extra_context_parts) if extra_context_parts else None
        return Region(name=location_text, country="US", additional_context=additional_context)

    if location_type == "natural":
        city_name = components.get("city", "")
        state_info = components.get("state", {})
        if isinstance(state_info, dict):
            state_name = state_info.get("name")
            state_abbr = state_info.get("abbr")
        else:
            state_name = state_info if isinstance(state_info, str) else None
            state_abbr = None

        place_info = components.get("place", {}) if isinstance(components, dict) else {}
        if isinstance(place_info, dict):
            place_name = place_info.get("name")
            place_is_natural = bool(place_info.get("natural"))
        else:
            place_name = None
            place_is_natural = False

        extra_context_parts = []
        if state.get("original_text"):
            extra_context_parts.append(f"Original text: {state['original_text']}")
        extra_fields = state.get("extra_fields") or {}
        description = extra_fields.get("description")
        if description:
            extra_context_parts.append(f"Description: {description}")
        additional_context = "\n".join(extra_context_parts) if extra_context_parts else None

        return NaturalPlace(
            name=location_text,
            city=city_name or None,
            state=state_name,
            state_abbr=state_abbr,
            country="US",
            place_name=place_name,
            place_is_natural=place_is_natural,
            additional_context=additional_context,
        )

    if location_type == "span":
        span_info = components.get("span", {}) if isinstance(components, dict) else {}
        return Span(name=location_text, span=span_info, country="US")

    return None

########## GEOCODE NODE ##########

async def orchestrate_geocode(state: AgentState) -> AgentState:
    """
    Orchestrate geocoding by routing to the appropriate geography model.
    
    This LangGraph node determines which model (State, County, Address) to use
    and calls its geocode() method, which contains the actual geocoding logic.
    """
    location_type = state["location_type"].lower()
    location_text = state["location_text"]
    components = state.get("location_components", {})
    
    logger.info(f"Geocoding {location_type}: {location_text}")
    
    try:
        pelias_api_key = state.get("pelias_api_key")
        geocodio_api_key = state.get("geocodio_api_key")
        openai_api_key = state.get("openai_api_key")
        brave_search_api_key = state.get("brave_search_api_key")
        use_cache = state.get("use_cache", False)
        stylebook_api_url = state.get("stylebook_api_url") or os.environ.get("STYLEBOOK_API_URL")
        project_slug = state.get("project_slug") or os.environ.get("PROJECT_SLUG")
        service_api_token = state.get("service_api_token") or os.environ.get("SERVICE_API_TOKEN")

        # Try canonical matching and cache lookup if enabled
        geocoding_result = None
        if use_cache and stylebook_api_url and project_slug:
            logger.info(f"[CACHE ENABLED] Attempting cache lookup for '{location_text}' (project: {project_slug})")
            # 1. Try canonical matching (run in thread pool to avoid blocking)
            logger.info(f"Stylebook canonical match: name={location_text}, project_slug={project_slug}")
            try:
                canonical_match = await asyncio.to_thread(
                    match_canonical_location,
                    name=location_text,
                    base_url=stylebook_api_url,
                    project_slug=project_slug,
                    service_token=service_api_token
                )
                if canonical_match:
                    geocoding_result = stylebook_match_to_geocoding_result(
                        canonical_match, location_text
                    )
                    logger.info(f"[CACHE HIT] Found canonical match for '{location_text}': {canonical_match.get('id', 'unknown')}")
                else:
                    logger.info(f"No canonical match found for '{location_text}', trying cache")
            except Exception as e:
                logger.warning(f"Error during canonical match for '{location_text}': {e}")

            # 2. If no canonical match, try cache lookup
            if not geocoding_result:
                logger.info(f"Checking LocationCache for '{location_text}' before external geocoding")
                try:
                    cache_match = await asyncio.to_thread(
                        get_location_cache,
                        name=location_text,
                        base_url=stylebook_api_url,
                        project_slug=project_slug,
                        service_token=service_api_token
                    )
                    if cache_match:
                        try:
                            geocoding_result = cache_match_to_geocoding_result(cache_match, location_text)
                            if not geocoding_result.result.geometry:
                                logger.warning(f"Cache match for '{location_text}' has no geometry, falling back to external geocoding")
                                geocoding_result = None
                            else:
                                logger.info(f"[CACHE HIT] Found cache match for '{location_text}': {cache_match.get('id', 'unknown')}")
                        except Exception as e:
                            logger.warning(f"Error converting cache match for '{location_text}': {e}")
                            geocoding_result = None
                    else:
                        logger.info(f"No cache match found for '{location_text}', proceeding to external geocoding")
                except Exception as e:
                    logger.warning(f"Error looking up cache for '{location_text}': {e}")

        # If we have a result from cache/canonical, use it; otherwise proceed with model geocoding
        if geocoding_result:
            state["geocoding_result"] = geocoding_result
            state["geocoding_model"] = None  # No model used for cache/canonical matches
            state["geocoding_failure_reason"] = None
            logger.info(f"[CACHE SUCCESS] Geocoding success (cache/canonical): {geocoding_result.result.processed_str}")
            return state
        
        # Cache not enabled or no cache hit - log why
        if not use_cache:
            logger.info(f"[CACHE SKIP] Cache lookup disabled for '{location_text}'")
        elif not stylebook_api_url:
            logger.info(f"[CACHE SKIP] Stylebook API URL not configured for '{location_text}'")
        elif not project_slug:
            logger.info(f"[CACHE SKIP] Project slug not provided for '{location_text}'")
        else:
            logger.info(f"[CACHE MISS] No cache/canonical match found for '{location_text}', using external geocoding")

        model = _create_model(location_type, location_text, components, state)
        if model is None:
            logger.warning(f"Unsupported location type: {location_type}")
            state["geocoding_result"] = None
            state["geocoding_model"] = None
            return state
        
        # Geocode using the model
        geocode_kwargs = {
            "pelias_api_key": pelias_api_key,
            "geocodio_api_key": geocodio_api_key,
            "openai_api_key": openai_api_key,
        }

        if isinstance(model, Region):
            geocode_kwargs = {"openai_api_key": openai_api_key}
        else:
            if isinstance(model, Place):
                geocode_kwargs["brave_search_api_key"] = brave_search_api_key
            if isinstance(model, StreetRoad):
                geocode_kwargs["original_text"] = state.get("original_text", "")

        result = await model.geocode(**geocode_kwargs)
        
        # Store both the result and the model instance
        state["geocoding_result"] = result
        state["geocoding_model"] = model
        
        # Store failure reason if available
        if isinstance(model, Place) and hasattr(model, '_failure_reason') and model._failure_reason:
            state["geocoding_failure_reason"] = model._failure_reason
        elif isinstance(model, Intersection) and not result:
            # Intersection-specific failure reason
            state["geocoding_failure_reason"] = "Intersection geocoding failed"
        elif not result:
            state["geocoding_failure_reason"] = (
                state.get("geocoding_failure_reason")
                or f"Geocoding produced no result for {location_type}"
            )
        else:
            state["geocoding_failure_reason"] = None
            
        if result:
            try:
                logger.info(f"Geocoding success: {result.result.processed_str}")
            except Exception as e:
                logger.error(f"Error logging geocoding success: {str(e)}")
        else:
            logger.warning(f"Geocoding failed for {location_text}")
            
    except Exception as e:
        logger.error(f"Error geocoding {location_text}: {str(e)}")
        state["geocoding_result"] = None
        state["geocoding_model"] = None
    
    return state
