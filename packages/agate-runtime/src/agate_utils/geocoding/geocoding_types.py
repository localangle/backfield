"""
Shared types and data structures for geocoding services.

This module defines common data structures that are used across
all geocoding service implementations to ensure consistency.
"""

from typing import Dict, Optional, Union, List, Any, Sequence
from dataclasses import dataclass


def bbox_west_south_east_north_to_polygon_coordinates(
    bbox: Sequence[float] | Sequence[int],
) -> List[List[List[float]]]:
    """Convert a Pelias/GeoJSON bbox [west, south, east, north] to GeoJSON Polygon coordinates.

    Many providers expose extent as four numbers; GeoJSON ``Polygon`` requires a closed linear
    ring of ``[lon, lat]`` pairs. Callers should pass this return value as ``GeometryPolygon.coordinates``.
    """

    if len(bbox) != 4:
        raise ValueError("bbox must have length 4 [west, south, east, north]")
    west, south, east, north = (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
    ring: List[List[float]] = [
        [west, south],
        [east, south],
        [east, north],
        [west, north],
        [west, south],
    ]
    return [ring]


@dataclass
class GeometryPoint:
    """Represents a Point geometry with longitude, latitude coordinates."""
    type: str = "Point"
    coordinates: List[float] = None  # [longitude, latitude]
    
    def __post_init__(self):
        """Validate the point geometry."""
        if self.coordinates is None:
            raise ValueError("Point coordinates must be provided")
        if len(self.coordinates) != 2:
            raise ValueError("Point coordinates must have exactly 2 values [longitude, latitude]")
        
        lon, lat = self.coordinates
        if not isinstance(lon, (int, float)) or not isinstance(lat, (int, float)):
            raise ValueError("Coordinates must be numeric values")
        
        if not (-90 <= lat <= 90):
            raise ValueError(f"Latitude must be between -90 and 90, got {lat}")
        
        if not (-180 <= lon <= 180):
            raise ValueError(f"Longitude must be between -180 and 180, got {lon}")


@dataclass
class GeometryPolygon:
    """Represents a Polygon geometry with bounding box coordinates or full GeoJSON coordinates."""
    type: str = "Polygon"
    coordinates: Union[List[float], List[List[float]], List[List[List[float]]], List[List[List[List[float]]]]] = None  # Can be bbox [west, south, east, north] or full GeoJSON coordinates
    
    def __post_init__(self):
        """Validate the polygon geometry."""
        if self.coordinates is None:
            raise ValueError("Polygon coordinates must be provided")
        
        # If coordinates is a 4-element list of numbers, validate as bbox
        if isinstance(self.coordinates, list) and len(self.coordinates) == 4:
            if all(isinstance(coord, (int, float)) for coord in self.coordinates):
                west, south, east, north = self.coordinates
                if not (-90 <= south <= 90) or not (-90 <= north <= 90):
                    raise ValueError(f"South and north must be between -90 and 90, got south={south}, north={north}")
                if not (-180 <= west <= 180) or not (-180 <= east <= 180):
                    raise ValueError(f"West and east must be between -180 and 180, got west={west}, east={east}")
                if west >= east:
                    raise ValueError(f"West must be less than east, got west={west}, east={east}")
                if south >= north:
                    raise ValueError(f"South must be less than north, got south={south}, north={north}")
                return  # Valid bbox format
        
        # Otherwise, assume it's full GeoJSON coordinates (nested arrays)
        # No validation needed for full GeoJSON - it will be validated by the visualization/rendering code


@dataclass
class Confidence:
    """Represents confidence information for a geocoding result."""
    score: Optional[float] = None
    match_type: Optional[str] = None
    accuracy: Optional[str] = None


@dataclass
class GeocodingResultData:
    """Represents the core data of a geocoding result."""
    id: Optional[str]
    processed_str: str
    geometry: Union[GeometryPoint, GeometryPolygon]
    confidence: Dict  # Empty dict {} if no confidence available


@dataclass
class GeocodingResult:
    """
    Represents a standardized geocoding result with nested structure.
    
    This class provides a consistent interface for geocoding results
    across all geocoding service providers (Nominatim, Google, etc.).
    """
    geocoder: str
    input_str: str
    result: GeocodingResultData
    
    def to_dict(self) -> Dict:
        """Convert the result to a dictionary."""
        return {
            'geocoder': self.geocoder,
            'input_str': self.input_str,
            'result': {
                'id': self.result.id,
                'processed_str': self.result.processed_str,
                'geometry': {
                    'type': self.result.geometry.type,
                    'coordinates': self.result.geometry.coordinates
                },
                'confidence': self.result.confidence,
            }
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'GeocodingResult':
        """Create a GeocodingResult from a dictionary."""
        geometry_data = data['result']['geometry']
        if geometry_data['type'] == 'Point':
            geometry = GeometryPoint(coordinates=geometry_data['coordinates'])
        elif geometry_data['type'] == 'Polygon':
            geometry = GeometryPolygon(coordinates=geometry_data['coordinates'])
        else:
            raise ValueError(f"Unsupported geometry type: {geometry_data['type']}")
        
        result_data = GeocodingResultData(
            id=data['result']['id'],
            processed_str=data['result']['processed_str'],
            geometry=geometry,
            confidence=data['result']['confidence'],
        )
        
        return cls(
            geocoder=data['geocoder'],
            input_str=data['input_str'],
            result=result_data
        )
    
    def __str__(self) -> str:
        """String representation of the geocoding result."""
        if self.result.geometry.type == "Point":
            lon, lat = self.result.geometry.coordinates
            return f"GeocodingResult(geocoder='{self.geocoder}', input='{self.input_str}', coordinates=({lat:.6f}, {lon:.6f}))"
        else:
            return f"GeocodingResult(geocoder='{self.geocoder}', input='{self.input_str}', geometry=Polygon)"
    
    def __repr__(self) -> str:
        """Detailed string representation of the geocoding result."""
        return (f"GeocodingResult(geocoder='{self.geocoder}', "
                f"input_str='{self.input_str}', "
                f"id='{self.result.id}', "
                f"geometry_type='{self.result.geometry.type}')")


@dataclass
class GeocodingError:
    """
    Represents an error that occurred during geocoding.
    
    This class provides a standardized way to handle and report
    geocoding errors across different service providers.
    """
    error_type: str
    message: str
    query: Optional[str] = None
    service: Optional[str] = None
    details: Optional[Dict] = None
    
    def __str__(self) -> str:
        """String representation of the geocoding error."""
        service_info = f" ({self.service})" if self.service else ""
        query_info = f" for query '{self.query}'" if self.query else ""
        return f"{self.error_type}{service_info}{query_info}: {self.message}"
    
    def __repr__(self) -> str:
        """Detailed string representation of the geocoding error."""
        return (f"GeocodingError(error_type='{self.error_type}', "
                f"message='{self.message}', query='{self.query}', "
                f"service='{self.service}')")


# Common error types
class GeocodingErrorTypes:
    """Constants for common geocoding error types."""
    TIMEOUT = "timeout"
    SERVICE_ERROR = "service_error"
    QUOTA_EXCEEDED = "quota_exceeded"
    INVALID_QUERY = "invalid_query"
    NO_RESULTS = "no_results"
    NETWORK_ERROR = "network_error"
    AUTHENTICATION_ERROR = "authentication_error"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"


# Type aliases for better code readability
GeocodingResults = list[GeocodingResult]
GeocodingErrors = list[GeocodingError]


def cache_match_to_geocoding_result(
    cache_match: Dict[str, Any],
    original_query: str
) -> GeocodingResult:
    """
    Convert LocationCache match to GeocodingResult format.
    
    Args:
        cache_match: Result from /geo/cache endpoint
        original_query: Original location query string
        
    Returns:
        GeocodingResult object
    """
    import json
    
    # Extract geometry from boundaries - use full geometry coordinates directly
    boundaries = cache_match.get("boundaries", [])
    geometry_type = cache_match.get("type", "Polygon")
    
    geometry = None
    if boundaries and len(boundaries) > 0:
        geom_dict = boundaries[0] if isinstance(boundaries, list) else boundaries
        geom_type = geom_dict.get("type", geometry_type)
        coords = geom_dict.get("coordinates", [])
        
        if geom_type == "Point" and isinstance(coords, list) and len(coords) >= 2:
            geometry = GeometryPoint(coordinates=[float(coords[0]), float(coords[1])])
        elif geom_type in ["Polygon", "MultiPolygon"]:
            # Store full GeoJSON coordinates directly (not just bbox)
            if isinstance(coords, list) and len(coords) > 0:
                geometry = GeometryPolygon(coordinates=coords)  # Store full coordinates directly
                geometry.type = geom_type  # Set type (Polygon or MultiPolygon)
    
    # If we still don't have geometry, try bbox fallback
    if geometry is None:
        bbox = cache_match.get("bbox")
        if bbox and isinstance(bbox, list) and len(bbox) == 4:
            geometry = GeometryPolygon(
                coordinates=bbox_west_south_east_north_to_polygon_coordinates(bbox),
            )
        else:
            # If no geometry at all, raise an error or return None
            raise ValueError(f"No geometry data available in cache match for query: {original_query}")
    
    # Build processed string (use label or name)
    processed_str = cache_match.get("label") or cache_match.get("name", original_query)
    
    # Build confidence dict
    confidence = cache_match.get("confidence", {})
    confidence.update({
        "source": "location_cache",
        "cache_id": cache_match.get("confidence", {}).get("cache_id")
    })
    
    result_data = GeocodingResultData(
        id=cache_match.get("id"),  # Use location_source_id as identifier
        processed_str=processed_str,
        geometry=geometry,
        confidence=confidence,
    )
    
    return GeocodingResult(
        geocoder="cache",
        input_str=original_query,
        result=result_data
    )


def stylebook_match_to_geocoding_result(
    stylebook_match: Dict[str, Any],
    original_query: str
) -> GeocodingResult:
    """
    Convert StylebookLocation match to GeocodingResult format.
    
    Args:
        stylebook_match: Result from /geo/match endpoint
        original_query: Original location query string
        
    Returns:
        GeocodingResult object
    """
    import json
    
    # Extract geometry from boundaries - use full geometry coordinates directly
    boundaries = stylebook_match.get("boundaries", [])
    geometry_type = stylebook_match.get("type", "Polygon")
    
    geometry = None
    if boundaries and len(boundaries) > 0:
        geom_dict = boundaries[0] if isinstance(boundaries, list) else boundaries
        geom_type = geom_dict.get("type", geometry_type)
        coords = geom_dict.get("coordinates", [])
        
        # Debug logging
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Converting stylebook match: geom_type={geom_type}, coords_type={type(coords).__name__}, coords_length={len(str(coords)) if coords else 0}")
        
        if geom_type == "Point" and len(coords) == 2:
            geometry = GeometryPoint(coordinates=[float(coords[0]), float(coords[1])])
        elif geom_type in ["Polygon", "MultiPolygon"]:
            # Store full GeoJSON coordinates directly (not just bbox)
            if isinstance(coords, list) and len(coords) > 0:
                # Create geometry with full GeoJSON coordinates
                # GeometryPolygon now accepts both bbox and full GeoJSON coordinates
                geometry = GeometryPolygon(coordinates=coords)  # Store full coordinates directly
                geometry.type = geom_type  # Set type (Polygon or MultiPolygon)
                logger.info(f"Created geometry: type={geometry.type}, coords_length={len(str(geometry.coordinates))}")
    
    # If we still don't have geometry, try bbox fallback
    if geometry is None:
        bbox = stylebook_match.get("bbox")
        if bbox and len(bbox) == 4:
            geometry = GeometryPolygon(
                coordinates=bbox_west_south_east_north_to_polygon_coordinates(bbox),
            )
    
    # Build processed string (use label or name)
    processed_str = stylebook_match.get("label") or stylebook_match.get("name", original_query)
    
    # Build confidence dict (without geometry_json - geometry goes in result.geometry)
    confidence = stylebook_match.get("confidence", {})
    confidence.update({
        "source": "canonical",
        "canonical_id": stylebook_match.get("id")
    })
    
    result_data = GeocodingResultData(
        id=f"stylebook:{stylebook_match.get('id')}",
        processed_str=processed_str,
        geometry=geometry,
        confidence=confidence,
    )
    
    return GeocodingResult(
        geocoder="stylebook",
        input_str=original_query,
        result=result_data
    )
