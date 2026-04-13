"""Intersection geocoding model for road intersections."""

import logging
from typing import Optional
from backfield_agate_utils.geocoding.geocodio import geocode_search as geocodio_search, is_valid_intersection_result
from backfield_agate_utils.geocoding.geocoding_types import GeocodingResult, GeocodingResultData, GeometryPoint
from backfield_agate_utils.geocoding.overpass import find_intersection_coordinates_from_text
from backfield_agate_utils.geocoding.wof import get_parents_by_coords, get_id_by_coords

from .point import Point

logger = logging.getLogger(__name__)

########## INTERSECTION MODEL ##########

class Intersection(Point):
    """Model for street or highway intersections."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._original_text: Optional[str] = None

    ########## PRIVATE/HELPER METHODS ##########

    def _try_geocodio(self, geocodio_api_key: Optional[str]) -> Optional[GeocodingResult]:
        if not geocodio_api_key:
            return None

        try:
            result = geocodio_search(self.name, geocodio_api_key)
            if result and result.result and is_valid_intersection_result(result.result.confidence):
                logger.info("Geocodio returned valid intersection for %s", self.name)
                return result
        except Exception as exc:
            logger.warning("Geocodio failed for intersection %s: %s", self.name, exc)
        return None

    async def _try_overpass(
        self,
        openai_api_key: Optional[str],
    ) -> Optional[GeocodingResult]:
        if not openai_api_key:
            return None

        try:
            search_text = self._original_text or self.name
            intersections, queries = await find_intersection_coordinates_from_text(search_text, openai_api_key)
            for idx, query in enumerate(queries):
                logger.info("Overpass query %d for %s: %s", idx + 1, self.name, query[:200])

            if not intersections:
                return None

            point = intersections[0].get("point")
            if not point:
                return None

            lat, lon = point.y, point.x
            try:
                parent_hierarchy = get_parents_by_coords(lat, lon, placetype="address")
            except Exception as exc:
                logger.warning("Failed to get parents for intersection %s: %s", self.name, exc)
                parent_hierarchy = {}

            result_data = GeocodingResultData(
                id=get_id_by_coords(lat, lon, "address"),
                processed_str=self.name,
                geometry=GeometryPoint(type="Point", coordinates=[lon, lat]),
                confidence={},
                parent_hierarchy=parent_hierarchy,
            )
            return GeocodingResult(geocoder="overpass", input_str=self.name, result=result_data)
        except Exception as exc:
            logger.error("Overpass geocoding failed for %s: %s", self.name, exc)
            return None

    ########## PUBLIC METHODS ##########

    async def geocode(
        self,
        pelias_api_key: Optional[str] = None,
        geocodio_api_key: Optional[str] = None,
        openai_api_key: Optional[str] = None,
    ) -> Optional[GeocodingResult]:
        logger.info("Geocoding intersection: %s", self.name)

        geocodio_result = self._try_geocodio(geocodio_api_key)
        if geocodio_result:
            self.geocoding_result = geocodio_result
            return geocodio_result

        overpass_result = await self._try_overpass(openai_api_key)
        if overpass_result:
            self.geocoding_result = overpass_result
            return overpass_result

        logger.warning("All intersection geocoding methods failed for %s", self.name)
        return None
