"""Geocodio geocoding service wrapper using geopy."""

import logging
from typing import Dict, Any, Optional, Union
from geopy.geocoders import Geocodio
from geopy.exc import GeocoderServiceError, GeocoderTimedOut
from agate_utils.geocoding.geocoding_types import GeocodingResult, GeocodingResultData, GeometryPoint, Confidence
from agate_utils.geocoding.wof import get_parents_by_coords, get_id_by_coords

logger = logging.getLogger(__name__)


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


def geocode_search(
    query: str,
    api_key: str,
    timeout: int = 10,
    placetype: Optional[str] = None
) -> Optional[GeocodingResult]:
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
        
        logger.info(f"Geocodio search geocoding: {query}")
        
        location = geolocator.geocode(query)
        
        if not location:
            logger.warning(f"No results found for: {query}")
            return None
        
        # Get parent hierarchy using WOF
        parent_hierarchy = {}
        if placetype:
            try:
                parent_hierarchy = get_parents_by_coords(
                    location.latitude,
                    location.longitude,
                    placetype
                )
            except Exception as e:
                logger.warning(f"Failed to get parent hierarchy from WOF: {e}")
                parent_hierarchy = {}
        
        # Store raw data for validation purposes
        raw_data = location.raw if hasattr(location, 'raw') else {}
        
        # Build result
        result_data = GeocodingResultData(
            id=get_id_by_coords(location.latitude, location.longitude, placetype),
            processed_str=raw_data.get("formatted_address", location.address),
            geometry=GeometryPoint(
                type="Point",
                coordinates=[location.longitude, location.latitude]
            ),
            confidence=raw_data,  # Store raw data in confidence for later validation
            parent_hierarchy=parent_hierarchy
        )
        
        return GeocodingResult(
            geocoder="geocodio_search",
            input_str=query,
            result=result_data
        )
        
    except GeocoderTimedOut:
        logger.error(f"Geocodio geocoding timed out for: {query}")
        return None
    except GeocoderServiceError as e:
        logger.error(f"Geocodio service error: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Error in Geocodio search geocoding: {str(e)}")
        return None


def geocode_structured(
    street: Optional[str] = None,
    city: Optional[str] = None,
    state: Optional[str] = None,
    postal_code: Optional[str] = None,
    country: Optional[str] = None,
    api_key: str = None,
    timeout: int = 10,
    placetype: Optional[str] = None
) -> Optional[GeocodingResult]:
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
        
        logger.info(f"Geocodio structured geocoding: {query_dict}")
        
        location = geolocator.geocode(query_dict)
        
        if not location:
            logger.warning(f"No results found for structured query: {query_dict}")
            return None
        
        # Get parent hierarchy using WOF
        parent_hierarchy = {}
        if placetype:
            try:
                parent_hierarchy = get_parents_by_coords(
                    location.latitude,
                    location.longitude,
                    placetype
                )
            except Exception as e:
                logger.warning(f"Failed to get parent hierarchy from WOF: {e}")
                parent_hierarchy = {}
        
        # Build input string from components for display
        input_parts = [p for p in [street, city, state, postal_code, country] if p]
        input_str = ", ".join(input_parts)
        
        # Build result
        result_data = GeocodingResultData(
            id=get_id_by_coords(location.latitude, location.longitude, placetype),
            processed_str=location.raw.get("formatted_address", location.address),
            geometry=GeometryPoint(
                type="Point",
                coordinates=[location.longitude, location.latitude]
            ),
            confidence={},  # geopy doesn't expose Geocodio's accuracy score
            parent_hierarchy=parent_hierarchy
        )
        
        return GeocodingResult(
            geocoder="geocodio_structured",
            input_str=input_str,
            result=result_data
        )
        
    except GeocoderTimedOut:
        logger.error(f"Geocodio geocoding timed out for: {query_dict}")
        return None
    except GeocoderServiceError as e:
        logger.error(f"Geocodio service error: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Error in Geocodio structured geocoding: {str(e)}")
        return None


def reverse_geocode(
    lat: float,
    lon: float,
    api_key: str,
    timeout: int = 10
) -> Optional[GeocodingResult]:
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
        
        logger.info(f"Geocodio reverse geocoding: ({lat}, {lon})")
        
        location = geolocator.reverse((lat, lon))
        
        if not location:
            logger.warning(f"No results found for coordinates: ({lat}, {lon})")
            return None
        
        # Build result
        result_data = GeocodingResultData(
            id=None,
            processed_str=location.address,
            geometry=GeometryPoint(
                type="Point",
                coordinates=[location.longitude, location.latitude]
            ),
            confidence={},
            parent_hierarchy=None  # Geocodio doesn't provide parent hierarchy via geopy
        )
        
        return GeocodingResult(
            geocoder="geocodio_reverse",
            input_str=f"{lat}, {lon}",
            result=result_data
        )
        
    except GeocoderTimedOut:
        logger.error(f"Geocodio reverse geocoding timed out for: ({lat}, {lon})")
        return None
    except GeocoderServiceError as e:
        logger.error(f"Geocodio service error: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Error in Geocodio reverse geocoding: {str(e)}")
        return None

