import hashlib, logging, math
from typing import Dict, Optional, Tuple
from pydantic import Field
from agate_utils.geocoding.geocoding_types import (
    GeocodingResult,
    GeocodingResultData,
    GeometryPoint,
    GeometryPolygon,
    bbox_west_south_east_north_to_polygon_coordinates,
)
from .area import Area
from .city import City
from ..point.intersection import Intersection

logger = logging.getLogger(__name__)

MILES_TO_METERS = 1609.34
EARTH_RADIUS_DEG_LAT = 111_320  # Approximate meters per degree latitude

########## SPAN MODEL ##########

class Span(Area):
    """Area model representing a roadway span between two endpoints."""

    span: Dict[str, Dict[str, str]] = Field(default_factory=dict)
    buffer_miles: float = Field(default=0.25)

    def __init__(self, **data):
        super().__init__(**data)
        self._start_model: Optional[Area] = None
        self._end_model: Optional[Area] = None
        self._start_point: Optional[GeometryPoint] = None
        self._end_point: Optional[GeometryPoint] = None

    ########## PRIVATE/HELPER METHODS ##########

    async def _geocode_endpoint(
        self,
        endpoint: Dict[str, str],
        pelias_api_key: Optional[str],
        geocodio_api_key: Optional[str],
        openai_api_key: Optional[str],
    ) -> Tuple[Optional[Area], Optional[GeometryPoint]]:
        endpoint_type = (endpoint.get("type") or "").lower()
        location_text = (endpoint.get("location") or "").strip()

        if not endpoint_type or not location_text:
            logger.warning("Invalid span endpoint: %s", endpoint)
            return None, None

        if endpoint_type == "city":
            return await self._geocode_city_endpoint(
                location_text, pelias_api_key, geocodio_api_key, openai_api_key
            )
        if endpoint_type in {"intersection", "intersection_road", "intersection_highway"}:
            return await self._geocode_intersection_endpoint(
                location_text, geocodio_api_key, openai_api_key
            )

        logger.warning("Unsupported span endpoint type '%s'", endpoint_type)
        return None, None

    async def _geocode_city_endpoint(
        self,
        location_text: str,
        pelias_api_key: Optional[str],
        geocodio_api_key: Optional[str],
        openai_api_key: Optional[str],
    ) -> Tuple[Optional[City], Optional[GeometryPoint]]:
        city_name, state_name, country = self._parse_city(location_text)
        city_model = City(name=city_name, state=state_name, county="", country=country)

        result = await city_model.geocode(
            pelias_api_key=pelias_api_key,
            geocodio_api_key=geocodio_api_key,
            openai_api_key=openai_api_key,
        )

        if not result or not result.result:
            return city_model, None

        point = self._geometry_to_point(result.result.geometry)
        if not point:
            return city_model, None

        city_model.geocoding_result = result
        return city_model, point

    async def _geocode_intersection_endpoint(
        self,
        location_text: str,
        geocodio_api_key: Optional[str],
        openai_api_key: Optional[str],
    ) -> Tuple[Optional[Intersection], Optional[GeometryPoint]]:
        intersection_model = Intersection(name=location_text, country=self.country)
        intersection_model._original_text = location_text

        result = await intersection_model.geocode(
            pelias_api_key=None,
            geocodio_api_key=geocodio_api_key,
            openai_api_key=openai_api_key,
        )

        if not result or not result.result:
            return intersection_model, None

        geometry = result.result.geometry
        if geometry.type != "Point":
            logger.warning(
                "Intersection geocoder returned non-point geometry for %s",
                location_text,
            )
            return intersection_model, None

        intersection_model.geocoding_result = result
        return intersection_model, GeometryPoint(coordinates=geometry.coordinates)

    @staticmethod
    def _geometry_to_point(geometry) -> Optional[GeometryPoint]:
        if geometry.type == "Point":
            return GeometryPoint(coordinates=list(geometry.coordinates))
        if geometry.type == "Polygon":
            west, south, east, north = geometry.coordinates
            lon = (west + east) / 2
            lat = (south + north) / 2
            return GeometryPoint(coordinates=[lon, lat])
        logger.warning("Unsupported geometry type for span endpoint: %s", geometry.type)
        return None

    @staticmethod
    def _parse_city(location_text: str) -> Tuple[str, str, str]:
        parts = [part.strip() for part in location_text.split(",") if part.strip()]
        city = parts[0] if parts else location_text
        state = parts[1] if len(parts) > 1 else ""
        country = parts[2] if len(parts) > 2 else "US"
        return city, state, country or "US"

    def _build_buffered_bbox(
        self,
        start_point: GeometryPoint,
        end_point: GeometryPoint,
    ) -> Optional[GeometryPolygon]:
        lon1, lat1 = start_point.coordinates
        lon2, lat2 = end_point.coordinates

        buffer_meters = self.buffer_miles * MILES_TO_METERS
        lat_buffer = buffer_meters / EARTH_RADIUS_DEG_LAT

        avg_lat_rad = math.radians((lat1 + lat2) / 2)
        cos_lat = math.cos(avg_lat_rad)
        if abs(cos_lat) < 1e-6:
            cos_lat = 1e-6
        lon_buffer = buffer_meters / (EARTH_RADIUS_DEG_LAT * cos_lat)

        west = max(-180.0, min(lon1, lon2) - lon_buffer)
        east = min(180.0, max(lon1, lon2) + lon_buffer)
        south = max(-90.0, min(lat1, lat2) - lat_buffer)
        north = min(90.0, max(lat1, lat2) + lat_buffer)

        if west >= east or south >= north:
            logger.warning(
                "Invalid buffered bbox computed: west=%s east=%s south=%s north=%s",
                west,
                east,
                south,
                north,
            )
            return None

        return GeometryPolygon(
            coordinates=bbox_west_south_east_north_to_polygon_coordinates([west, south, east, north]),
        )

    def _build_result_id(self) -> str:
        digest = hashlib.md5(self.name.encode("utf-8")).hexdigest()
        return f"span:{digest[:20]}"


    ########## PUBLIC METHODS ##########

    async def geocode(
        self,
        pelias_api_key: Optional[str] = None,
        geocodio_api_key: Optional[str] = None,
        openai_api_key: Optional[str] = None,
        **_: Dict,
    ) -> Optional[GeocodingResult]:
        if not self.span or not self.span.get("start") or not self.span.get("end"):
            logger.warning("Span data missing start or end definitions")
            return None

        start_model, start_point = await self._geocode_endpoint(
            self.span["start"], pelias_api_key, geocodio_api_key, openai_api_key
        )
        end_model, end_point = await self._geocode_endpoint(
            self.span["end"], pelias_api_key, geocodio_api_key, openai_api_key
        )

        if not start_point or not end_point:
            logger.warning("Failed to geocode both endpoints for span '%s'", self.name)
            return None

        self._start_model = start_model
        self._end_model = end_model
        self._start_point = start_point
        self._end_point = end_point

        bbox = self._build_buffered_bbox(start_point, end_point)
        if not bbox:
            logger.warning("Failed to build bounding box for span '%s'", self.name)
            return None

        confidence = {
            "method": "span_buffer",
            "buffer_miles": self.buffer_miles,
            "start": {
                "type": self.span["start"].get("type"),
                "coordinates": start_point.coordinates,
            },
            "end": {
                "type": self.span["end"].get("type"),
                "coordinates": end_point.coordinates,
            },
        }

        result_data = GeocodingResultData(
            id=self._build_result_id(),
            processed_str=f"{self.name} (span)",
            geometry=bbox,
            confidence=confidence,
        )

        self.geocoding_result = GeocodingResult(
            geocoder="span",
            input_str=self.name,
            result=result_data,
        )

        return self.geocoding_result