"""Geocodio geocoding service wrapper using geopy."""

import logging
from typing import Any

from agate_utils.geocoding.geocoding_types import (
    GeocodingResult,
    GeocodingResultData,
    GeometryPoint,
)
from backfield_observability.external import sanitize_error_message
from geopy.exc import GeocoderServiceError, GeocoderTimedOut
from geopy.geocoders import Geocodio

logger = logging.getLogger(__name__)


def _geocodio_result_id(raw_data: dict[str, Any]) -> str | None:
    """Stable id from Geocodio when the API returns stable_address_key."""
    key = raw_data.get("stable_address_key")
    if key is None:
        return None
    key_str = str(key).strip()
    if not key_str:
        return None
    return f"geocodio:{key_str}"


_ACCEPTABLE_ACCURACY_TYPES: frozenset[str] = frozenset(
    {
        "rooftop",
        "point",
        "range_interpolation",
        "intersection",
    }
)


def is_valid_intersection_result(raw_data: dict) -> bool:
    """
    Check if a Geocodio result is a valid intersection.
    
    Args:
        raw_data: Raw data from Geocodio response
        
    Returns:
        bool: True if it's a valid intersection result
    """
    accuracy_type = raw_data.get("accuracy_type", "")
    accuracy_score = raw_data.get("accuracy", 0)
    
    # Valid ONLY if it's an intersection (not street_center)
    return accuracy_type == "intersection" and accuracy_score >= 0.8


def is_acceptable_geocodio_accuracy(
    raw_data: dict | None,
    *,
    min_accuracy: float = 0.8,
) -> bool:
    """True when Geocodio accuracy_type/score are precise enough to auto-accept.

    Rejects coarse types such as ``place`` (city centroid), ``street_center``,
    ``nearest_rooftop_match``, and ``postal_code``.
    """
    if not isinstance(raw_data, dict):
        return False
    accuracy_type = str(raw_data.get("accuracy_type") or "").strip().lower()
    if accuracy_type not in _ACCEPTABLE_ACCURACY_TYPES:
        return False
    try:
        accuracy_score = float(raw_data.get("accuracy") or 0)
    except (TypeError, ValueError):
        return False
    return accuracy_score >= min_accuracy


def geocode_search(
    query: str,
    api_key: str,
    timeout: int = 10,
    placetype: str | None = None
) -> GeocodingResult | None:
    """
    Geocode a location using Geocodio with a free-text query.
    
    Args:
        query: Location text to geocode
        api_key: Geocodio API key
        timeout: Request timeout in seconds
        pelias_api_key: Pelias API key
        geo_type: Type of geography being geocoded
        
    Returns:
        GeocodingResult if successful, None otherwise
    """
    try:
        geolocator = Geocodio(api_key=api_key, timeout=timeout)
        
        logger.info("Geocodio search geocoding request")
        logger.debug("Geocodio search placetype hint present=%s", bool(placetype))

        location = geolocator.geocode(query)
        
        if not location:
            logger.warning("No Geocodio search results")
            return None
        
        # Store raw data for validation purposes
        raw_data = location.raw if hasattr(location, 'raw') else {}
        
        # Build result
        result_data = GeocodingResultData(
            id=_geocodio_result_id(raw_data),
            processed_str=raw_data.get("formatted_address", location.address),
            geometry=GeometryPoint(
                type="Point",
                coordinates=[location.longitude, location.latitude]
            ),
            confidence=raw_data,  # Store raw data in confidence for later validation
        )
        
        return GeocodingResult(
            geocoder="geocodio_search",
            input_str=query,
            result=result_data
        )
        
    except GeocoderTimedOut:
        logger.error("Geocodio geocoding timed out")
        return None
    except GeocoderServiceError as e:
        from backfield_observability.external import sanitize_error_message

        logger.error("Geocodio service error: %s", sanitize_error_message(str(e)))
        return None
    except Exception as e:
        from backfield_observability.external import sanitize_error_message

        logger.error("Error in Geocodio search geocoding: %s", sanitize_error_message(str(e)))
        return None


def geocode_structured(
    street: str | None = None,
    city: str | None = None,
    state: str | None = None,
    postal_code: str | None = None,
    country: str | None = None,
    api_key: str = None,
    timeout: int = 10,
    placetype: str | None = None
) -> GeocodingResult | None:
    """
    Geocode using Geocodio with structured address components.
    
    Args:
        street: Street address (e.g., "100 Main St")
        city: City/town name
        state: State/province name or abbreviation
        postal_code: ZIP/postal code
        country: Country name or code (optional, defaults to US)
        api_key: Geocodio API key
        timeout: Request timeout in seconds
        
    Returns:
        GeocodingResult if successful, None otherwise
    """
    if not api_key:
        logger.error("Geocodio API key is required")
        return None
    
    try:
        geolocator = Geocodio(api_key=api_key, timeout=timeout)
        
        # Build structured query dictionary
        query_dict = {}
        if street:
            query_dict["street"] = street
        if city:
            query_dict["city"] = city
        if state:
            query_dict["state"] = state
        if postal_code:
            query_dict["postal_code"] = postal_code
        if country:
            query_dict["country"] = country
        
        if not query_dict:
            logger.error("At least one address component must be provided")
            return None
        
        logger.info("Geocodio structured geocoding request")
        logger.debug("Geocodio structured placetype hint: %r", placetype)

        location = geolocator.geocode(query_dict)
        
        if not location:
            logger.warning("No Geocodio structured results")
            return None
        
        # Build input string from components for display
        input_parts = [p for p in [street, city, state, postal_code, country] if p]
        input_str = ", ".join(input_parts)

        raw_data = location.raw if hasattr(location, "raw") and location.raw else {}

        # Build result
        result_data = GeocodingResultData(
            id=_geocodio_result_id(raw_data),
            processed_str=raw_data.get("formatted_address", location.address),
            geometry=GeometryPoint(
                type="Point",
                coordinates=[location.longitude, location.latitude]
            ),
            confidence=raw_data,
        )
        
        return GeocodingResult(
            geocoder="geocodio_structured",
            input_str=input_str,
            result=result_data
        )
        
    except GeocoderTimedOut:
        logger.error("Geocodio structured geocoding timed out")
        return None
    except GeocoderServiceError as e:
        logger.error("Geocodio service error: %s", sanitize_error_message(str(e)))
        return None
    except Exception as e:
        logger.error("Error in Geocodio structured geocoding: %s", sanitize_error_message(str(e)))
        return None


def reverse_geocode(
    lat: float,
    lon: float,
    api_key: str,
    timeout: int = 10
) -> GeocodingResult | None:
    """
    Reverse geocode coordinates using Geocodio.
    
    Args:
        lat: Latitude
        lon: Longitude
        api_key: Geocodio API key
        timeout: Request timeout in seconds
        
    Returns:
        GeocodingResult if successful, None otherwise
    """
    if not api_key:
        logger.error("Geocodio API key is required")
        return None
    
    try:
        geolocator = Geocodio(api_key=api_key, timeout=timeout)
        
        logger.info("Geocodio reverse geocoding request")
        
        location = geolocator.reverse((lat, lon))
        
        if not location:
            logger.warning("No Geocodio reverse results")
            return None

        raw_data = location.raw if hasattr(location, "raw") and location.raw else {}

        # Build result
        result_data = GeocodingResultData(
            id=_geocodio_result_id(raw_data),
            processed_str=location.address,
            geometry=GeometryPoint(
                type="Point",
                coordinates=[location.longitude, location.latitude]
            ),
            confidence=raw_data,
        )
        
        return GeocodingResult(
            geocoder="geocodio_reverse",
            input_str=f"{lat}, {lon}",
            result=result_data
        )
        
    except GeocoderTimedOut:
        logger.error("Geocodio reverse geocoding timed out")
        return None
    except GeocoderServiceError as e:
        logger.error("Geocodio service error: %s", sanitize_error_message(str(e)))
        return None
    except Exception as e:
        logger.error("Error in Geocodio reverse geocoding: %s", sanitize_error_message(str(e)))
        return None

