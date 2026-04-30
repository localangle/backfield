"""Shared types for the geocoding agent."""

from collections.abc import Callable
from typing import Any, Optional, TypedDict

from agate_utils.geocoding.geocoding_types import GeocodingResult

# Sync (run in ``asyncio.to_thread``): returns match dict for stylebook/cache converters, or None.
CacheResolveFn = Callable[[str, str, dict[str, Any]], dict[str, Any] | None]


class AgentState(TypedDict, total=False):
    """State for the geocoding agent."""
    location_text: str
    location_type: str
    location_components: dict
    original_text: str
    extra_fields: dict  # Additional fields from PlaceExtract (like 'mural', 'description', etc.)
    geocoding_result: Optional[GeocodingResult]
    geocoding_model: Optional[Any]  # The model instance used for geocoding
    geocoding_failure_reason: Optional[str]  # Reason for geocoding failure (e.g., "not addressable", "non-point geometry")
    pelias_api_key: Optional[str]
    geocodio_api_key: Optional[str]
    openai_api_key: Optional[str]
    brave_search_api_key: Optional[str]
    use_cache: bool  # Whether to use Stylebook canonical matching and cache
    stylebook_api_url: Optional[str]  # Stylebook API URL for canonical matching
    project_slug: Optional[str]  # Project slug for canonical matching
    service_api_token: Optional[str]  # Service API token for Stylebook API
    # When set with ``use_cache``, DB-backed canonical + substrate_location_cache (Backfield worker).
    cache_resolve: Optional[CacheResolveFn]
    final_output: Optional[dict]
    # Optional per-run OpenAI model overrides (AdvancedGeocodeAgent / future hybrid graphs).
    evaluation_llm_model: Optional[str]
    router_llm_model: Optional[str]
