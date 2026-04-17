"""Pelias geocoding service wrapper."""

import logging
import httpx
from typing import Dict, Any, Optional, List
from agate_utils.geocoding.geocoding_types import (
    Confidence,
    GeocodingResult,
    GeocodingResultData,
    GeometryPoint,
    GeometryPolygon,
    bbox_west_south_east_north_to_polygon_coordinates,
)

logger = logging.getLogger(__name__)


async def geocode_search(
    text: str,
    api_key: Optional[str] = None,
    size: int = 5,
    **kwargs
) -> Optional[GeocodingResult]:
    """
    Geocode a location using Pelias search endpoint.
    
    Args:
        text: Location text to geocode
        api_key: Pelias/Geocode.Earth API key (optional)
        size: Maximum number of results to return
        **kwargs: Additional parameters to pass to Pelias (e.g., boundary.country, focus.point.lat)
        
    Returns:
        GeocodingResult if successful, None otherwise
    """
    try:
        url = "https://api.geocode.earth/v1/search"
        params = {
            "text": text,
            "size": size,
            **kwargs
        }
        
        if api_key:
            params["api_key"] = api_key
        
        logger.info(f"Pelias search geocoding: {text}")
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
        
        features = data.get("features", [])
        if not features:
            logger.warning(f"No results found for: {text}")
            return None
        
        # Use the first (best) result
        feature = features[0]
        properties = feature.get("properties", {})
        geometry = feature.get("geometry", {})
        bbox = feature.get("bbox")  # Bounding box [west, south, east, north]
        
        # Determine if this is an area (has bbox) or a point
        # For areas like city, county, state, use the bbox as Polygon
        # For addresses/POIs, use the Point
        layer = properties.get("layer", "")
        is_area = layer in ["city", "county", "region", "country", "localadmin",
            "neighbourhood", "locality"]
        
        if bbox and is_area and len(bbox) == 4:
            # Use bounding box for area-type results
            logger.info(f"Using bbox for {layer}: {bbox}")
            result_geometry = GeometryPolygon(
                type="Polygon",
                coordinates=bbox_west_south_east_north_to_polygon_coordinates(bbox),
            )
        else:
            # Use point geometry
            if geometry.get("type") != "Point":
                logger.warning(f"Unexpected geometry type: {geometry.get('type')}")
                return None
            
            coords = geometry.get("coordinates", [])
            if len(coords) < 2:
                logger.warning("Invalid coordinates in result")
                return None
            
            lon, lat = coords[0], coords[1]
            result_geometry = GeometryPoint(
                type="Point",
                coordinates=[lon, lat]
            )
        
        # Use specific GID based on layer type
        layer = properties.get("layer", "")
        if layer == "neighbourhood":
            result_id = properties.get("neighbourhood_gid")
        elif layer == "locality":
            result_id = properties.get("locality_gid")
        elif layer == "county":
            result_id = properties.get("county_gid")
        elif layer == "region":
            result_id = properties.get("region_gid")
        else:
            result_id = properties.get("gid")  # Fallback to generic gid
        
        # Build result
        result_data = GeocodingResultData(
            id=result_id,
            processed_str=properties.get("label", text),
            geometry=result_geometry,
            confidence={},  # Pelias doesn't provide structured confidence
        )
        
        return GeocodingResult(
            geocoder="pelias_search",
            input_str=text,
            result=result_data
        )
        
    except Exception as e:
        logger.error(f"Error in Pelias search geocoding: {str(e)}")
        return None


async def geocode_structured(
    address: Optional[str] = None,
    locality: Optional[str] = None,
    county: Optional[str] = None,
    region: Optional[str] = None,
    neighbourhood: Optional[str] = None,
    postalcode: Optional[str] = None,
    country: str = "US",
    api_key: Optional[str] = None,
    **kwargs
) -> Optional[GeocodingResult]:
    """
    Geocode using Pelias structured endpoint with address components.
    
    Args:
        address: Street address (e.g., "100 Main St")
        locality: City/town name
        county: County name
        region: State/province name
        neighbourhood: Neighborhood name
        postalcode: ZIP/postal code
        country: Country code (default: "US")
        api_key: Pelias/Geocode.Earth API key (optional)
        **kwargs: Additional parameters to pass to Pelias
        
    Returns:
        GeocodingResult if successful, None otherwise
    """
    try:
        url = "https://api.geocode.earth/v1/search/structured"
        
        params = {"country": country}
        
        # Add provided components
        if address:
            params["address"] = address
        if locality:
            params["locality"] = locality
        if county:
            params["county"] = county
        if neighbourhood:
            params["neighbourhood"] = neighbourhood
        if region:
            params["region"] = region
        if postalcode:
            params["postalcode"] = postalcode
        
        # Add any additional params
        params.update(kwargs)
        
        if api_key:
            params["api_key"] = api_key
        
        logger.info(f"Pelias structured geocoding: {params}")
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
        
        features = data.get("features", [])
        if not features:
            logger.warning(f"No results found for structured query")
            return None
        
        # Use the first (best) result
        feature = features[0]
        properties = feature.get("properties", {})
        geometry = feature.get("geometry", {})
        bbox = feature.get("bbox")  # Bounding box [west, south, east, north]
        
        # Determine if this is an area (has bbox) or a point
        layer = properties.get("layer", "")
        is_area = layer in ["city", "county", "region",
        "country", "localadmin", "neighbourhood", "locality"]
        
        if bbox and is_area and len(bbox) == 4:
            # Use bounding box for area-type results
            logger.info(f"Using bbox for {layer}: {bbox}")
            result_geometry = GeometryPolygon(
                type="Polygon",
                coordinates=bbox_west_south_east_north_to_polygon_coordinates(bbox),
            )
        else:
            # Use point geometry
            if geometry.get("type") != "Point":
                logger.warning(f"Unexpected geometry type: {geometry.get('type')}")
                return None
            
            coords = geometry.get("coordinates", [])
            if len(coords) < 2:
                logger.warning("Invalid coordinates in result")
                return None
            
            lon, lat = coords[0], coords[1]
            result_geometry = GeometryPoint(
                type="Point",
                coordinates=[lon, lat]
            )
        
        # Build input string from components
        input_parts = [p for p in [address, locality, county, region, postalcode, country] if p]
        input_str = ", ".join(input_parts)
        
        # Use specific GID based on layer type
        layer = properties.get("layer", "")
        if layer == "neighbourhood":
            result_id = properties.get("neighbourhood_gid")
        elif layer == "locality":
            result_id = properties.get("locality_gid")
        elif layer == "county":
            result_id = properties.get("county_gid")
        elif layer == "region":
            result_id = properties.get("region_gid")
        else:
            result_id = properties.get("gid")  # Fallback to generic gid
        
        # Build result
        result_data = GeocodingResultData(
            id=result_id,
            processed_str=properties.get("label", input_str),
            geometry=result_geometry,
            confidence={},  # Pelias doesn't provide structured confidence
        )
        
        return GeocodingResult(
            geocoder="pelias_structured",
            input_str=input_str,
            result=result_data
        )
        
    except Exception as e:
        logger.error(f"Error in Pelias structured geocoding: {str(e)}")
        return None


async def reverse_geocode(
    lat: float,
    lon: float,
    api_key: Optional[str] = None,
    **kwargs
) -> Optional[GeocodingResult]:
    """
    Reverse geocode coordinates using Pelias.
    
    Args:
        lat: Latitude
        lon: Longitude
        api_key: Pelias/Geocode.Earth API key (optional)
        **kwargs: Additional parameters to pass to Pelias
        
    Returns:
        GeocodingResult if successful, None otherwise
    """
    try:
        url = "https://api.geocode.earth/v1/reverse"
        params = {
            "point.lat": lat,
            "point.lon": lon,
            "size": 1,
            **kwargs
        }
        
        if api_key:
            params["api_key"] = api_key
        
        logger.info(f"Pelias reverse geocoding: ({lat}, {lon})")
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
        
        features = data.get("features", [])
        if not features:
            logger.warning(f"No results found for coordinates: ({lat}, {lon})")
            return None
        
        feature = features[0]
        properties = feature.get("properties", {})
        geometry = feature.get("geometry", {})
        
        coords = geometry.get("coordinates", [])
        if len(coords) < 2:
            logger.warning("Invalid coordinates in result")
            return None
        
        result_lon, result_lat = coords[0], coords[1]
        
        # Build result
        input_str = f"{lat}, {lon}"
        result_data = GeocodingResultData(
            id=properties.get("gid"),  # Use gid (Who's On First ID) instead of id
            processed_str=properties.get("label", input_str),
            geometry=GeometryPoint(
                type="Point",
                coordinates=[result_lon, result_lat]
            ),
            confidence={},
        )
        
        return GeocodingResult(
            geocoder="pelias_reverse",
            input_str=input_str,
            result=result_data
        )
        
    except Exception as e:
        logger.error(f"Error in Pelias reverse geocoding: {str(e)}")
        return None
