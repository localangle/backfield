"""Shared types for the geocoding agent."""

from typing import TypedDict, Optional, Any
from backfield_agate_utils.geocoding.geocoding_types import GeocodingResult


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
    final_output: Optional[dict]
