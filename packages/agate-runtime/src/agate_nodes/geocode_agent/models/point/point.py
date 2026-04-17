import logging
from typing import Optional, Dict, Any
from agate_utils.geocoding.geocoding_types import GeocodingResult
from agate_utils.geocoding.pelias import geocode_search as pelias_search
from agate_utils.geocoding.geocodio import geocode_search as geocodio_search
from agate_utils.geocoding.nominatim import geocode_address

from ..base import Location

logger = logging.getLogger(__name__)

########## BASE POINT MODEL ##########

class Point(Location):
    """Base class for point-type locations (addresses, POIs, etc.)."""

    ########## PRIVATE/HELPER METHODS ##########

    def _is_good_point_result(self, result: GeocodingResult) -> bool:
        """Return True when the geocoder produced a point geometry."""
        if not result or not result.result:
            return False
        return getattr(result.result.geometry, "type", None) == "Point"

    ########## PUBLIC METHODS ##########

    async def geocode(
        self,
        pelias_api_key: Optional[str] = None,
        geocodio_api_key: Optional[str] = None,
    ) -> Optional[GeocodingResult]:
        """Geocode a point using the Pelias → Geocodio → Nominatim fallback chain."""
        logger.info("Geocoding point: %s", self.name)

        try:
            prep_data = self._prep()
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Point prep failed for %s: %s", self.name, exc)
            return None

        # Try Pelias first
        if pelias_api_key:
            try:
                result = await pelias_search(text=prep_data["text"], api_key=pelias_api_key)
                if result and self._is_good_point_result(result):
                    logger.info("Pelias success for %s", self.name)
                    return result
            except Exception as exc:
                logger.warning("Pelias failed for %s: %s", self.name, exc)

        # Try Geocodio
        if geocodio_api_key:
            try:
                result = geocodio_search(query=prep_data["text"], api_key=geocodio_api_key)
                if result and self._is_good_point_result(result):
                    logger.info("Geocodio success for %s", self.name)
                    return result
            except Exception as exc:
                logger.warning("Geocodio failed for %s: %s", self.name, exc)

        # Fall back to Nominatim
        try:
            result = geocode_address(address=prep_data["text"], user_agent="agate-ai-platform/1.0")
            if result and self._is_good_point_result(result):
                logger.info("Nominatim success for %s", self.name)
                return result
        except Exception as exc:
            logger.warning("Nominatim failed for %s: %s", self.name, exc)

        logger.warning("All geocoding services failed for %s", self.name)
        return None
