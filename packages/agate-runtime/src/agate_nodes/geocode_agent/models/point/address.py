import logging
from typing import Dict, Any, Optional
from agate_utils.geocoding.geocoding_types import GeocodingResult
from agate_utils.geocoding.pelias import geocode_search as pelias_search, geocode_structured as pelias_structured
from agate_utils.geocoding.geocodio import geocode_search as geocodio_search
from agate_utils.geocoding.nominatim import geocode_address

from .point import Point

logger = logging.getLogger(__name__)

########## ADDRESS MODEL ##########

class Address(Point):
    """Model for address-level locations."""

    ########## PRIVATE/HELPER METHODS ##########

    def _prep(self) -> Dict[str, Any]:
        """Prepare address data for geocoding."""
        parts = [self.name]
        if self.city:
            parts.append(self.city)
        if self.state_abbr:
            parts.append(self.state_abbr)
        if self.country:
            parts.append(self.country)
        full_address = ", ".join(parts)

        return {
            "full_address": full_address,
            "pelias_structured": {
                "address": self.name,
                "locality": self.city or None,
                "region": self.state_abbr or None,
                "country": self.country or "USA",
            },
        }

    ########## PUBLIC METHODS ##########

    async def geocode(
        self,
        pelias_api_key: Optional[str] = None,
        geocodio_api_key: Optional[str] = None,
        openai_api_key: Optional[str] = None,
    ) -> Optional[GeocodingResult]:
        """Geocode an address using Pelias → Geocodio → Nominatim."""
        logger.info("Geocoding address: %s", self.name)

        try:
            prep_data = self._prep()
        except Exception as exc:
            logger.error("Address prep failed for %s: %s", self.name, exc)
            return None

        full_address = prep_data["full_address"]

        # Pelias structured (best accuracy when address components present)
        if pelias_api_key:
            try:
                structured_params = {k: v for k, v in prep_data["pelias_structured"].items() if v}
                result = await pelias_structured(**structured_params, api_key=pelias_api_key)
                if result and self._is_good_point_result(result):
                    logger.info("Pelias structured success for %s", self.name)
                    self.geocoding_result = result
                    return result
            except Exception as exc:
                logger.warning("Pelias structured failed for %s: %s", self.name, exc)

        # Pelias search fallback
        if pelias_api_key:
            try:
                result = await pelias_search(text=full_address, api_key=pelias_api_key)
                if result and self._is_good_point_result(result):
                    logger.info("Pelias search success for %s", self.name)
                    self.geocoding_result = result
                    return result
            except Exception as exc:
                logger.warning("Pelias search failed for %s: %s", self.name, exc)

        # Geocodio
        if geocodio_api_key:
            try:
                result = geocodio_search(query=full_address, api_key=geocodio_api_key)
                if result and self._is_good_point_result(result):
                    logger.info("Geocodio success for %s", self.name)
                    self.geocoding_result = result
                    return result
            except Exception as exc:
                logger.warning("Geocodio failed for %s: %s", self.name, exc)

        # Nominatim fallback
        try:
            result = geocode_address(address=full_address, user_agent="agate-ai-platform/1.0")
            if result and self._is_good_point_result(result):
                logger.info("Nominatim success for %s", self.name)
                self.geocoding_result = result
                return result
        except Exception as exc:
            logger.warning("Nominatim failed for %s: %s", self.name, exc)

        logger.warning("All geocoding services failed for %s", self.name)
        return None
