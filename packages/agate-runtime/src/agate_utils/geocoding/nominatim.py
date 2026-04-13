"""
Nominatim geocoding service wrapper.

This module provides a simplified interface to the Nominatim geocoding service
using the geopy library. Nominatim is a free, open-source geocoding service
that uses OpenStreetMap data.
"""

import time
import logging
import threading
from typing import Dict, List, Optional, Tuple, Union, Any

import requests
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError, GeocoderQuotaExceeded
from geopy.location import Location

from .geocoding_types import GeocodingResult, GeocodingResultData, GeometryPoint, GeometryPolygon, GeocodingError, GeocodingErrorTypes
from .wof import get_parents_by_coords, get_id_by_coords

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class NominatimGeocoder:
    """
    A wrapper class for Nominatim geocoding service.
    
    Provides methods for forward geocoding (address to coordinates) and
    reverse geocoding (coordinates to address) with error handling,
    rate limiting, and result standardization.
    """
    
    def __init__(
        self,
        user_agent: str = "agate-ai-platform/1.0",
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
        self._geocoder: Optional[Nominatim] = None
        self.rate_limit = rate_limit
        self.last_request_time = 0.0
        
    def _enforce_rate_limit(self) -> None:
        """Enforce rate limiting between requests."""
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
    
    def _extract_address_components(self, location: Location) -> Dict[str, Optional[str]]:
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
    
    def _location_to_result(self, location: Location, input_str: str, placetype: Optional[str] = None) -> GeocodingResult:
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
            # Create Polygon geometry from bounding box [west, south, east, north]
            try:
                west, south, east, north = map(float, boundingbox)
                geometry = GeometryPolygon(coordinates=[west, south, east, north])
            except (ValueError, TypeError):
                # Fallback to Point if bounding box is invalid
                geometry = GeometryPoint(coordinates=[location.longitude or 0.0, location.latitude or 0.0])
        else:
            # Create Point geometry from lat/lon
            geometry = GeometryPoint(coordinates=[location.longitude or 0.0, location.latitude or 0.0])
        
        # Get parent hierarchy using WOF
        parent_hierarchy = {}
        if placetype and location.latitude and location.longitude:
            try:
                parent_hierarchy = get_parents_by_coords(
                    location.latitude,
                    location.longitude,
                    placetype
                )
            except Exception as e:
                logger.warning(f"Failed to get parent hierarchy from WOF: {e}")
                parent_hierarchy = {}
        
        # Get ID from WOF if placetype is recognized, otherwise use Nominatim place_id
        wof_id = None
        if placetype:
            try:
                wof_id = get_id_by_coords(location.latitude, location.longitude, placetype)
            except Exception as e:
                logger.warning(f"Failed to get WOF ID for coordinates: {e}")
        
        # Use WOF ID if available, otherwise fall back to Nominatim place_id
        result_id = wof_id if wof_id else (f"nominatim:{place_id}" if place_id else None)
        
        # Create result data
        result_data = GeocodingResultData(
            id=result_id,
            processed_str=location.raw.get("formatted_address", location.address),
            geometry=geometry,
            confidence={},  # Empty dict since Nominatim doesn't provide confidence scores
            parent_hierarchy=parent_hierarchy
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
        country_codes: Optional[List[str]] = None,
        viewbox: Optional[Tuple[float, float, float, float]] = None,
        bounded: bool = False,
        placetype: Optional[str] = None
    ) -> Union[GeocodingResult, List[GeocodingResult], None]:
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
        
        try:
            logger.info(f"Geocoding query: {query}")
            
            # Prepare geocoding parameters
            geocode_params = {
                'exactly_one': exactly_one,
                'language': 'en'
            }
            
            if country_codes:
                geocode_params['country_codes'] = ','.join(country_codes)
            
            if viewbox:
                geocode_params['viewbox'] = viewbox
                geocode_params['bounded'] = bounded
            
            # Perform geocoding
            geocoder = self._get_geocoder()
            results = geocoder.geocode(query, **geocode_params)
            print(f"Nominatim results: {results}")
            
            if not results:
                logger.warning(f"No results found for query: {query}")
                return None
            
            # Convert results to standardized format
            if exactly_one:
                return self._location_to_result(results, query, placetype)
            else:
                return [self._location_to_result(location, query, placetype) for location in results]
                
        except GeocoderTimedOut:
            logger.error(f"Geocoding timeout for query: {query}")
            return None
        except GeocoderServiceError as e:
            logger.error(f"Geocoding service error for query '{query}': {e}")
            return None
        except GeocoderQuotaExceeded:
            logger.error(f"Geocoding quota exceeded for query: {query}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error geocoding query '{query}': {e}")
            return None
    
    def search_raw(
        self,
        query: str,
        limit: int = 10,
        addressdetails: bool = True,
        extratags: bool = True,
        namedetails: bool = True,
        language: str = "en",
        layer: Optional[str] = None,
        dedupe: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
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
        try:
            logger.info(f"Searching Nominatim for: {query}")
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

            response = requests.get(
                "https://nominatim.openstreetmap.org/search",
                params=params,
                headers={"User-Agent": self.user_agent},
                timeout=self.timeout,
            )
            response.raise_for_status()
            results = response.json()
            if not isinstance(results, list):
                logger.warning("Unexpected Nominatim response format for query: %s", query)
                return []
            logger.info("Nominatim search returned %d raw result(s) for %s", len(results), query)
            return results
        except requests.Timeout:
            logger.error(f"Nominatim search timeout for query: {query}")
            return []
        except requests.HTTPError as e:
            logger.error(f"Nominatim HTTP error for query '{query}': {e}")
            return []
        except requests.RequestException as e:
            logger.error(f"Nominatim request error for query '{query}': {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error during Nominatim search for '{query}': {e}")
            return []
    

########## CONVENIENCE FUNCTIONS ##########

def geocode_address(
    address: str,
    user_agent: str = "agate-ai-platform/1.0",
    country_codes: Optional[List[str]] = None,
    placetype: Optional[str] = None
) -> Optional[GeocodingResult]:
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
    user_agent: str = "agate-ai-platform/1.0",
    limit: int = 10,
    addressdetails: bool = True,
    extratags: bool = True,
    namedetails: bool = True,
) -> List[Dict[str, Any]]:
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
    user_agent: str = "agate-ai-platform/1.0",
    limit: int = 20
) -> Optional[str]:
    """
    Convenience function to geocode an address and return raw JSON data as string.
    
    Args:
        address: Address to geocode
        user_agent: User agent string for API requests
        limit: Maximum number of results to return (up to 10)
        
    Returns:
        JSON string containing raw Nominatim results or None if no results
    """
    try:
        from geopy.geocoders import Nominatim
        
        # Initialize Nominatim geocoder
        geolocator = Nominatim(user_agent=user_agent, timeout=10)
        
        # Perform geocoding request
        locations = geolocator.geocode(address, limit=limit, exactly_one=False)
        
        if not locations:
            logger.warning(f"No results found for: {address}")
            return None
        
        # Combine raw data from all results
        raw_results = []
        for location in locations:
            if hasattr(location, 'raw'):
                raw_results.append(location.raw)
        
        if not raw_results:
            logger.warning(f"No raw data found in results for: {address}")
            return None
        
        # Convert to JSON string
        import json
        json_string = json.dumps(raw_results, indent=2)
        
        logger.info(f"Found {len(raw_results)} raw results for: {address}")
        return json_string
        
    except Exception as e:
        logger.error(f"Error geocoding address '{address}': {e}")
        return None