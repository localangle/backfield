"""
Nominatim geocoding service wrapper.

This module provides a simplified interface to the Nominatim geocoding service
using the geopy library. Nominatim is a free, open-source geocoding service
that uses OpenStreetMap data.
"""

import logging
import os
import threading
import time
from typing import Any

import requests
from geopy.exc import GeocoderQuotaExceeded, GeocoderServiceError, GeocoderTimedOut
from geopy.geocoders import Nominatim
from geopy.location import Location

from agate_utils.geocoding.nominatim_cache import (
    get_cached_search,
    search_cache_key,
    store_cached_search,
)
from agate_utils.geocoding.lookup_budget import (
    new_deadline,
    remaining_s,
    retry_delay_seconds,
    sleep_before_deadline,
)
from agate_utils.geocoding.provider_health import record_geocoder_http_status
from agate_utils.geocoding.request_gate import (
    GateWaitTimeout,
    acquire_geocode_request_slot,
    provider_cooldown_active,
    start_provider_cooldown,
)

from .geocoding_types import (
    GeocodingResult,
    GeocodingResultData,
    GeometryPoint,
    GeometryPolygon,
    bbox_west_south_east_north_to_polygon_coordinates,
)

_NOMINATIM_MAX_HTTP_RETRIES = 4
_NOMINATIM_RATE_LIMIT_FLOOR_S = 8.0
_NOMINATIM_MAX_RETRY_DELAY_S = 30.0
_DEFAULT_LOOKUP_BUDGET_S = 60.0

# Logging uses the process root JSON formatter; do not call basicConfig here.
logger = logging.getLogger(__name__)


def nominatim_lookup_budget_s() -> float:
    """Hard time budget for one lookup: gate wait, requests, and retry pauses together."""
    raw = os.getenv("NOMINATIM_LOOKUP_BUDGET_S", "").strip()
    try:
        return max(1.0, float(raw)) if raw else _DEFAULT_LOOKUP_BUDGET_S
    except ValueError:
        return _DEFAULT_LOOKUP_BUDGET_S


def _start_cooldown(reason: str) -> None:
    """Make every worker skip Nominatim briefly after a lookup it could not complete."""
    start_provider_cooldown("nominatim", f"Nominatim {reason}")


def _wait_to_retry_rate_limited(
    attempt: int, deadline: float, response: requests.Response | None = None
) -> bool:
    """Back off after a rate-limit answer. False means give up (and start the fleet cool-down)."""
    if attempt >= _NOMINATIM_MAX_HTTP_RETRIES:
        logger.error("Nominatim rate limited; giving up")
        _start_cooldown("rate limited")
        return False
    delay = retry_delay_seconds(
        response,
        attempt=attempt,
        base_delay_s=_NOMINATIM_RATE_LIMIT_FLOOR_S,
        max_delay_s=_NOMINATIM_MAX_RETRY_DELAY_S,
    )
    logger.warning(
        "Nominatim rate limited, retrying in %.1fs (attempt %s/%s)",
        delay,
        attempt,
        _NOMINATIM_MAX_HTTP_RETRIES,
    )
    if not sleep_before_deadline(delay, deadline):
        logger.error("Nominatim rate limited and out of time")
        _start_cooldown("rate limited and out of time")
        return False
    return True


class NominatimGeocoder:
    """
    A wrapper class for Nominatim geocoding service.
    
    Provides methods for forward geocoding (address to coordinates) and
    reverse geocoding (coordinates to address) with error handling,
    rate limiting, and result standardization.
    """
    
    def __init__(
        self,
        user_agent: str = "agate/1.0",
        timeout: int = 10,
        rate_limit: float = 1.0
    ):
        """
        Initialize the Nominatim geocoder.
        
        Args:
            user_agent: User agent string for API requests (required by Nominatim)
            timeout: Request timeout in seconds
            rate_limit: Minimum delay between requests in seconds
        """
        self.user_agent = user_agent
        self.timeout = timeout
        self._lock = threading.Lock()
        self._rate_limit_lock = threading.Lock()
        self._geocoder: Nominatim | None = None
        self.rate_limit = rate_limit
        self.last_request_time = 0.0
        
    def _enforce_rate_limit(self) -> None:
        """Enforce rate limiting between requests."""
        # Geocode calls run in worker threads, so serialize the check-and-sleep.
        with self._rate_limit_lock:
            current_time = time.time()
            elapsed = current_time - self.last_request_time
            if elapsed < self.rate_limit:
                sleep_time = self.rate_limit - elapsed
                logger.debug("Nominatim rate limit: sleeping %.2f seconds", sleep_time)
                time.sleep(sleep_time)
            self.last_request_time = time.time()

    def _get_geocoder(self) -> Nominatim:
        with self._lock:
            if self._geocoder is None:
                self._geocoder = Nominatim(user_agent=self.user_agent, timeout=self.timeout)
            return self._geocoder
    
    def _extract_address_components(self, location: Location) -> dict[str, str | None]:
        """
        Extract standardized address components from a geopy Location object.
        
        Args:
            location: geopy Location object
            
        Returns:
            Dictionary with standardized address components
        """
        raw_data = location.raw if hasattr(location, 'raw') else {}
        address_components = raw_data.get('address', {})
        
        return {
            'country': address_components.get('country'),
            'state': address_components.get('state') or address_components.get('province'),
            'city': address_components.get('city') or address_components.get('town') or address_components.get('village'),
            'postal_code': address_components.get('postcode'),
            'place_type': address_components.get('type'),
            'raw_data': raw_data
        }
    
    def _location_to_result(self, location: Location, input_str: str, _placetype: str | None = None) -> GeocodingResult:
        """
        Convert a geopy Location object to a standardized GeocodingResult.
        
        Args:
            location: geopy Location object
            input_str: Original input string that was geocoded
            
        Returns:
            Standardized GeocodingResult object with nested structure
        """
        raw_data = location.raw if hasattr(location, 'raw') else {}
        
        # Extract place_id for the id field
        place_id = raw_data.get('place_id')
        
        # Determine geometry type based on available data
        boundingbox = raw_data.get('boundingbox')
        if boundingbox and len(boundingbox) == 4:
            # Nominatim returns [south, north, west, east]; convert to [west, south, east, north].
            try:
                south, north, west, east = map(float, boundingbox)
                geometry = GeometryPolygon(
                    coordinates=bbox_west_south_east_north_to_polygon_coordinates(
                        [west, south, east, north]
                    ),
                )
            except (ValueError, TypeError):
                # Fallback to Point if bounding box is invalid
                geometry = GeometryPoint(coordinates=[location.longitude or 0.0, location.latitude or 0.0])
        else:
            # Create Point geometry from lat/lon
            geometry = GeometryPoint(coordinates=[location.longitude or 0.0, location.latitude or 0.0])
        
        result_id = f"nominatim:{place_id}" if place_id else None
        
        # Create result data
        result_data = GeocodingResultData(
            id=result_id,
            processed_str=location.raw.get("formatted_address", location.address),
            geometry=geometry,
            confidence={
                "nominatim_class": raw_data.get("class"),
                "nominatim_type": raw_data.get("type"),
            },
        )
        
        return GeocodingResult(
            geocoder="nominatim",
            input_str=input_str,
            result=result_data
        )
    
    def geocode(
        self,
        query: str,
        exactly_one: bool = True,
        country_codes: list[str] | None = None,
        viewbox: tuple[float, float, float, float] | None = None,
        bounded: bool = False,
        placetype: str | None = None
    ) -> GeocodingResult | list[GeocodingResult] | None:
        """
        Geocode an address or place name to coordinates.
        
        Args:
            query: Address or place name to geocode
            exactly_one: If True, return single result; if False, return list
            country_codes: List of country codes to limit search (e.g., ['US', 'CA'])
            viewbox: Bounding box as (west, south, east, north) in decimal degrees
            bounded: If True, restrict results to the viewbox
            
        Returns:
            GeocodingResult, list of GeocodingResult, or None if no results
        """
        self._enforce_rate_limit()
        
        geocode_params = {
            "exactly_one": exactly_one,
            "language": "en",
        }
        if country_codes:
            geocode_params["country_codes"] = ",".join(country_codes)
        if viewbox:
            geocode_params["viewbox"] = viewbox
            geocode_params["bounded"] = bounded
            
        if provider_cooldown_active("nominatim"):
            logger.debug("Nominatim cooling down; skipping geocode")
            return None
        deadline = new_deadline(nominatim_lookup_budget_s())
        geocoder = self._get_geocoder()
        for attempt in range(1, _NOMINATIM_MAX_HTTP_RETRIES + 1):
            try:
                with acquire_geocode_request_slot(
                    "nominatim", max_wait_s=remaining_s(deadline)
                ):
                    results = geocoder.geocode(query, **geocode_params)
            
                if not results:
                    logger.warning("No Nominatim results")
                    return None
            
                if exactly_one:
                    return self._location_to_result(results, query, placetype)
                return [
                    self._location_to_result(location, query, placetype)
                    for location in results
                ]
            
            except GateWaitTimeout:
                logger.warning("Nominatim geocode gave up waiting for a request slot")
                return None
            except GeocoderTimedOut:
                logger.error("Nominatim geocode timeout")
                return None
            except GeocoderQuotaExceeded:
                record_geocoder_http_status("nominatim", 429)
                if not _wait_to_retry_rate_limited(attempt, deadline):
                    return None
            except GeocoderServiceError as e:
                message = str(e).lower()
                if "429" in message or "rate" in message:
                    record_geocoder_http_status("nominatim", 429)
                    if not _wait_to_retry_rate_limited(attempt, deadline):
                        return None
                    continue
                record_geocoder_http_status("nominatim", 502)
                logger.error("Nominatim geocode service error: %s", type(e).__name__)
                return None
            except Exception:
                logger.error("Unexpected Nominatim geocode error", exc_info=True)
                return None
        return None
    
    def search_raw(
        self,
        query: str,
        limit: int = 10,
        addressdetails: bool = True,
        extratags: bool = True,
        namedetails: bool = True,
        language: str = "en",
        layer: str | None = None,
        dedupe: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Retrieve raw Nominatim search results for a query.
        
        Args:
            query: Search text
            limit: Maximum number of results to return
            addressdetails: Whether to include address breakdown
            extratags: Whether to include additional tags
            namedetails: Whether to include name translations/details
            language: Preferred language for results
        
        Returns:
            List of raw result dictionaries (possibly empty)
        """
        self._enforce_rate_limit()
        params = {
            "q": query,
            "format": "jsonv2",
            "limit": str(limit),
            "addressdetails": "1" if addressdetails else "0",
            "extratags": "1" if extratags else "0",
            "namedetails": "1" if namedetails else "0",
            "accept-language": language,
        }
        if layer is not None:
            params["layer"] = layer
        if dedupe is not None:
            params["dedupe"] = str(dedupe)

        cache_key = search_cache_key(params)
        cached = get_cached_search(cache_key)
        if cached is not None:
            logger.debug("Nominatim search answered from the shared cache")
            return cached
        if provider_cooldown_active("nominatim"):
            logger.debug("Nominatim cooling down; skipping search")
            return []
        deadline = new_deadline(nominatim_lookup_budget_s())

        for attempt in range(1, _NOMINATIM_MAX_HTTP_RETRIES + 1):
            try:
                with acquire_geocode_request_slot(
                    "nominatim", max_wait_s=remaining_s(deadline)
                ):
                    # Another worker may have fetched this query while we waited for the slot.
                    cached = get_cached_search(cache_key)
                    if cached is not None:
                        logger.debug("Nominatim search answered from the shared cache")
                        return cached
                    response = requests.get(
                        "https://nominatim.openstreetmap.org/search",
                        params=params,
                        headers={"User-Agent": self.user_agent},
                        timeout=min(self.timeout, max(1.0, remaining_s(deadline))),
                    )
                if response.status_code >= 400:
                    record_geocoder_http_status("nominatim", response.status_code)
                if response.status_code == 429:
                    if not _wait_to_retry_rate_limited(attempt, deadline, response):
                        return []
                    continue
                response.raise_for_status()
                results = response.json()
                if not isinstance(results, list):
                    logger.warning("Unexpected Nominatim response format")
                    return []
                store_cached_search(cache_key, results)
                return results
            except GateWaitTimeout:
                logger.warning("Nominatim search gave up waiting for a request slot")
                return []
            except requests.Timeout:
                logger.error("Nominatim search timeout")
                return []
            except requests.HTTPError:
                logger.error("Nominatim HTTP error")
                return []
            except requests.RequestException:
                logger.error("Nominatim request error")
                return []
            except Exception:
                logger.error("Unexpected Nominatim search error", exc_info=True)
                return []
        return []
    

########## CONVENIENCE FUNCTIONS ##########

def geocode_address(
    address: str,
    user_agent: str = "agate/1.0",
    country_codes: list[str] | None = None,
    placetype: str | None = None
) -> GeocodingResult | None:
    """
    Convenience function to geocode a single address.
    
    Args:
        address: Address to geocode
        user_agent: User agent string for API requests
        country_codes: List of country codes to limit search
        
    Returns:
        GeocodingResult or None if no results
    """
    geocoder = NominatimGeocoder(user_agent=user_agent)
    return geocoder.geocode(address, country_codes=country_codes, placetype=placetype)


def search_places(
    query: str,
    user_agent: str = "agate/1.0",
    limit: int = 10,
    addressdetails: bool = True,
    extratags: bool = True,
    namedetails: bool = True,
) -> list[dict[str, Any]]:
    """
    Convenience function to perform a raw Nominatim search and return result dictionaries.
    """
    geocoder = NominatimGeocoder(user_agent=user_agent)
    return geocoder.search_raw(
        query=query,
        limit=limit,
        addressdetails=addressdetails,
        extratags=extratags,
        namedetails=namedetails,
    )


def geocode_address_raw(
    address: str,
    user_agent: str = "agate/1.0",
    limit: int = 20
) -> str | None:
    """
    Convenience function to geocode an address and return raw JSON data as string.
    
    Args:
        address: Address to geocode
        user_agent: User agent string for API requests
        limit: Maximum number of results to return (up to 10)
        
    Returns:
        JSON string containing raw Nominatim results or None if no results
    """
    import json

    try:
        raw_results = search_places(query=address, user_agent=user_agent, limit=limit)
        if not raw_results:
            logger.warning("No Nominatim results for address lookup")
            return None
        return json.dumps(raw_results, indent=2)
    except Exception:
        logger.error("Error geocoding address", exc_info=True)
        return None