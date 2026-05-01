"""LangGraph geocode node for intelligent geocoding with fallback strategies."""

import os
import asyncio
import logging
from ..models import (
    Area,
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
from ..types import AgentState, normalized_geocode_hints
from agate_utils.geocoding.localize import match_canonical_location, get_location_cache
from agate_utils.geocoding.geocoding_types import stylebook_match_to_geocoding_result, cache_match_to_geocoding_result

logger = logging.getLogger(__name__)


def _advanced_quiet(state: AgentState) -> bool:
    return bool(state.get("advanced_quiet_logs"))


def _adv_info(state: AgentState, msg: str, *args: object) -> None:
    if _advanced_quiet(state):
        logger.debug(msg, *args)
    else:
        logger.info(msg, *args)


########## HELPER FUNCTIONS ##########


def _geocode_hints_for_context(state: AgentState) -> str | None:
    """Stripped PlaceExtract hints for LLM context strings (Region, NaturalPlace, etc.)."""
    raw = state.get("geocode_hints") or normalized_geocode_hints(state.get("extra_fields"))
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


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
        addr = Address(name=address, city=city_name, state_abbr=state_abbr, country="US")
        addr._original_text = state.get("original_text", "")
        addr._geocode_hints = _geocode_hints_for_context(state)
        return addr

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
        hints = state.get("geocode_hints") or normalized_geocode_hints(state.get("extra_fields"))
        model._geocode_hints = hints or None
        return model

    if location_type in {"intersection_road", "intersection_highway"}:
        model = Intersection(name=location_text, country="US")
        model._original_text = state.get("original_text", "")
        model._geocode_hints = _geocode_hints_for_context(state)
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
        sr = StreetRoad(name=street_name, city=city_name, state=state_abbr, country="US")
        sr._geocode_hints = _geocode_hints_for_context(state)
        return sr

    if location_type.startswith("region"):
        extra_context_parts = []
        if state.get("original_text"):
            extra_context_parts.append(f"Original text: {state['original_text']}")
        extra_fields = state.get("extra_fields") or {}
        description = extra_fields.get("description")
        if description:
            extra_context_parts.append(f"Description: {description}")
        hints_line = _geocode_hints_for_context(state)
        if hints_line:
            extra_context_parts.append(f"Geocode hints: {hints_line}")
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
        hints_line = _geocode_hints_for_context(state)
        if hints_line:
            extra_context_parts.append(f"Geocode hints: {hints_line}")
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
        sp = Span(name=location_text, span=span_info, country="US")
        sp._geocode_hints = _geocode_hints_for_context(state)
        return sp

    return None

########## GEOCODE NODES ##########

async def resolve_cache_or_miss(state: AgentState) -> AgentState:
    """Populate ``geocoding_result`` from Stylebook / DB cache when configured; else leave unset."""
    location_type = state["location_type"].lower()
    location_text = state["location_text"]
    components = state.get("location_components", {})

    _adv_info(state, "Geocoding %s: %s", location_type, location_text)

    use_cache = state.get("use_cache", False)
    stylebook_api_url = state.get("stylebook_api_url") or os.environ.get("STYLEBOOK_API_URL")
    project_slug = state.get("project_slug") or os.environ.get("PROJECT_SLUG")
    service_api_token = state.get("service_api_token") or os.environ.get("SERVICE_API_TOKEN")

    geocoding_result = None
    cache_resolve_fn = state.get("cache_resolve")
    if use_cache and cache_resolve_fn is not None:
        _adv_info(state, "[CACHE ENABLED] DB cache resolve for '%s'", location_text)
        try:
            match_dict = await asyncio.to_thread(
                cache_resolve_fn,
                location_text,
                location_type,
                components,
            )
            if match_dict:
                src = (match_dict.get("confidence") or {}).get("source")
                try:
                    if src == "canonical_db":
                        geocoding_result = stylebook_match_to_geocoding_result(match_dict, location_text)
                    elif src == "location_cache":
                        geocoding_result = cache_match_to_geocoding_result(match_dict, location_text)
                    else:
                        geocoding_result = None
                    if geocoding_result and not geocoding_result.result.geometry:
                        logger.warning(
                            "DB cache match for '%s' has no geometry, falling back to external geocoding",
                            location_text,
                        )
                        geocoding_result = None
                    elif geocoding_result:
                        _adv_info(
                            state,
                            "[CACHE HIT] DB cache for '%s' (source=%s, id=%s)",
                            location_text,
                            src,
                            match_dict.get("id"),
                        )
                except Exception as e:
                    logger.warning("Error converting DB cache match for '%s': %s", location_text, e)
                    geocoding_result = None
        except Exception as e:
            logger.warning("Error during DB cache resolve for '%s': %s", location_text, e)

    elif use_cache and stylebook_api_url and project_slug:
        _adv_info(
            state,
            "[CACHE ENABLED] HTTP Stylebook cache for '%s' (project: %s)",
            location_text,
            project_slug,
        )
        _adv_info(
            state,
            "Stylebook canonical match: name=%s, project_slug=%s",
            location_text,
            project_slug,
        )
        try:
            canonical_match = await asyncio.to_thread(
                match_canonical_location,
                name=location_text,
                base_url=stylebook_api_url,
                project_slug=project_slug,
                service_token=service_api_token,
            )
            if canonical_match:
                geocoding_result = stylebook_match_to_geocoding_result(canonical_match, location_text)
                _adv_info(
                    state,
                    "[CACHE HIT] Found canonical match for '%s': %s",
                    location_text,
                    canonical_match.get("id", "unknown"),
                )
            else:
                _adv_info(state, "No canonical match found for '%s', trying cache", location_text)
        except Exception as e:
            logger.warning("Error during canonical match for '%s': %s", location_text, e)

        if not geocoding_result:
            _adv_info(state, "Checking LocationCache for '%s' before external geocoding", location_text)
            try:
                cache_match = await asyncio.to_thread(
                    get_location_cache,
                    name=location_text,
                    base_url=stylebook_api_url,
                    project_slug=project_slug,
                    service_token=service_api_token,
                )
                if cache_match:
                    try:
                        geocoding_result = cache_match_to_geocoding_result(cache_match, location_text)
                        if not geocoding_result.result.geometry:
                            logger.warning(
                                "Cache match for '%s' has no geometry, falling back to external geocoding",
                                location_text,
                            )
                            geocoding_result = None
                        else:
                            _adv_info(
                                state,
                                "[CACHE HIT] Found cache match for '%s': %s",
                                location_text,
                                cache_match.get("id", "unknown"),
                            )
                    except Exception as e:
                        logger.warning("Error converting cache match for '%s': %s", location_text, e)
                        geocoding_result = None
                else:
                    _adv_info(
                        state,
                        "No cache match found for '%s', proceeding to external geocoding",
                        location_text,
                    )
            except Exception as e:
                logger.warning("Error looking up cache for '%s': %s", location_text, e)

    if geocoding_result:
        state["geocoding_result"] = geocoding_result
        state["geocoding_model"] = None
        state["geocoding_failure_reason"] = None
        _adv_info(
            state,
            "[CACHE SUCCESS] Geocoding success (cache/canonical): %s",
            geocoding_result.result.processed_str,
        )
        return state

    if not use_cache:
        _adv_info(state, "[CACHE SKIP] Cache lookup disabled for '%s'", location_text)
    elif cache_resolve_fn is None and not stylebook_api_url:
        _adv_info(
            state,
            "[CACHE SKIP] No DB cache_resolve and no Stylebook API URL for '%s'",
            location_text,
        )
    elif cache_resolve_fn is None and not project_slug:
        _adv_info(state, "[CACHE SKIP] No DB cache_resolve and no project slug for '%s'", location_text)
    else:
        _adv_info(
            state,
            "[CACHE MISS] No cache/canonical match found for '%s', using external geocoding",
            location_text,
        )

    return state


async def orchestrate_external_geocode(state: AgentState) -> AgentState:
    """External geocoding path after cache miss (and optional routing)."""
    if state.get("geocoding_result") is not None:
        return state

    location_type = state["location_type"].lower()
    location_text = state["location_text"]
    components = state.get("location_components", {})

    try:
        pelias_api_key = state.get("pelias_api_key")
        geocodio_api_key = state.get("geocodio_api_key")
        openai_api_key = state.get("openai_api_key")
        brave_search_api_key = state.get("brave_search_api_key")

        model = _create_model(location_type, location_text, components, state)
        if model is None:
            logger.warning("Unsupported location type: %s", location_type)
            state["geocoding_result"] = None
            state["geocoding_model"] = None
            return state

        eval_model = state.get("evaluation_llm_model")
        if isinstance(model, Area) and eval_model:
            model._evaluation_llm_model = eval_model  # type: ignore[attr-defined]

        geocode_kwargs: dict = {
            "pelias_api_key": pelias_api_key,
            "geocodio_api_key": geocodio_api_key,
            "openai_api_key": openai_api_key,
        }

        if isinstance(model, Region):
            geocode_kwargs = {"openai_api_key": openai_api_key}
        else:
            if isinstance(model, Place):
                # Advanced graph sets ``allow_web_search`` from route_strategy; baseline graph omits it (default True).
                raw_allow = state.get("allow_web_search")
                allow_web = True if raw_allow is None else bool(raw_allow)
                geocode_kwargs["brave_search_api_key"] = (
                    brave_search_api_key if allow_web else None
                )
                geocode_kwargs["allow_web_search"] = allow_web
            if isinstance(model, StreetRoad):
                geocode_kwargs["original_text"] = state.get("original_text", "")

        result = await model.geocode(**geocode_kwargs)

        state["geocoding_result"] = result
        state["geocoding_model"] = model

        if isinstance(model, Place) and hasattr(model, "_failure_reason") and model._failure_reason:
            state["geocoding_failure_reason"] = model._failure_reason
        elif isinstance(model, Intersection) and not result:
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
                _adv_info(state, "Geocoding success: %s", result.result.processed_str)
            except Exception as e:
                logger.error("Error logging geocoding success: %s", e)
        else:
            logger.warning("Geocoding failed for %s", location_text)

    except Exception as e:
        logger.error("Error geocoding %s: %s", location_text, e)
        state["geocoding_result"] = None
        state["geocoding_model"] = None

    return state


async def orchestrate_geocode(state: AgentState) -> AgentState:
    """
    Baseline graph entry: cache resolution then external geocoding when needed.
    """
    await resolve_cache_or_miss(state)
    if state.get("geocoding_result") is not None:
        return state
    return await orchestrate_external_geocode(state)
