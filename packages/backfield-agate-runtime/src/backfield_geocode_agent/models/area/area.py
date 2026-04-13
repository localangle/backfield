import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from backfield_agate_utils.geocoding.geocoding_types import GeocodingResult
from backfield_agate_utils.geocoding.pelias import geocode_search as pelias_search, geocode_structured as pelias_structured
from backfield_agate_utils.geocoding.geocodio import geocode_search as geocodio_search
from backfield_agate_utils.geocoding.nominatim import geocode_address
from backfield_agate_utils.llm import call_llm
from ..base import Location

logger = logging.getLogger(__name__)

LLM_EVALUATION_MODEL = "gpt-5-nano"

########## BASE AREA MODEL ##########

class Area(Location):
    """Base class for area-type locations."""

    ########## PRIVATE/HELPER METHODS ##########

    def _get_placetype(self) -> str:
        """Get the placetype for this area model."""
        class_name = self.__class__.__name__.lower()
        if class_name == "city":
            return "city"
        elif class_name == "state":
            return "state"
        elif class_name == "county":
            return "county"
        elif class_name == "neighborhood":
            return "neighborhood"
        else:
            return "unknown"

    def _is_clear_match(self, result: GeocodingResult) -> bool:
        """Determine if a geocoding result is conclusively correct without LLM evaluation."""
        if not result or not result.result:
            return False

        processed_str = result.result.processed_str.lower()
        name_lower = self.name.lower()

        if name_lower in processed_str or processed_str in name_lower:
            return True

        if hasattr(result.result.geometry, "type") and result.result.geometry.type == "Point":
            return False

        return False

    def _evaluate_result(self, result: GeocodingResult, geocoder_name: str, openai_api_key: str) -> Optional[Dict[str, Any]]:
        """Use LLM to evaluate ambiguous geocoding results."""
        if not result or not result.result:
            return {"quality": "failed", "reason": "No result returned"}

        try:
            prompt_path = Path(__file__).parent.parent.parent / "prompts" / "evaluate_result.md"
            with open(prompt_path, "r") as f:
                prompt_template = f.read()

            coordinates = (
                result.result.geometry.coordinates
                if hasattr(result.result.geometry, "coordinates")
                else []
            )
            prompt = prompt_template.format(
                location_text=self.name,
                location_type="area",
                geocoder=geocoder_name,
                processed_str=result.result.processed_str,
                geometry_type=
                result.result.geometry.type if hasattr(result.result.geometry, "type") else "unknown",
                coordinates=str(coordinates),
            )

            response = call_llm(
                prompt=prompt,
                model=LLM_EVALUATION_MODEL,
                openai_api_key=openai_api_key,
            )

            evaluation = json.loads(response)
            return evaluation

        except Exception as e:
            logger.error(f"Error evaluating result: {e}")
            return None

    def _is_good_area_result(self, result: GeocodingResult) -> bool:
        """Check if the result is appropriate for an area (has bounding box or is area-type)."""
        if not result or not result.result:
            return False

        if hasattr(result.result.geometry, "type") and result.result.geometry.type == "Polygon":
            return True

        return True

    ########## PUBLIC METHODS ##########

    async def geocode(
        self,
        pelias_api_key: Optional[str] = None,
        geocodio_api_key: Optional[str] = None,
        openai_api_key: Optional[str] = None,
    ) -> Optional[GeocodingResult]:
        """Geocode an area using Pelias → Geocodio → Nominatim fallback chain."""
        logger.info(f"Geocoding area: {self.name}")
        
        # Try Pelias structured first (most accurate for areas with known components)
        if pelias_api_key:
            try:
                prep_data = self._prep()
                if "pelias_structured" in prep_data:
                    result = await pelias_structured(
                        **prep_data["pelias_structured"],
                        api_key=pelias_api_key
                    )

                    if result:
                        if self._is_clear_match(result):
                            logger.info(f"Pelias structured success for {self.name} (rules-based)")
                            self.geocoding_result = result
                            return result
                        elif openai_api_key:
                            evaluation = self._evaluate_result(result, "Pelias Structured", openai_api_key)
                            if evaluation and evaluation.get("quality") == "good":
                                logger.info(f"Pelias structured success for {self.name} (LLM evaluation)")
                                self.geocoding_result = result
                                return result
                            else:
                                reason = evaluation.get('reason', 'No reason') if evaluation else 'LLM evaluation failed'
                                logger.info(f"Pelias structured result poor for {self.name}: {reason}")
            except Exception as e:
                logger.warning(f"Pelias structured failed for {self.name}: {e}")
        
        # Try Pelias search
        if pelias_api_key:
            try:
                prep_data = self._prep()
                if "pelias_search" in prep_data:
                    result = await pelias_search(
                        text=prep_data["pelias_search"]["text"],
                        api_key=pelias_api_key
                    )
                    if result:
                        if self._is_clear_match(result):
                            logger.info(f"Pelias search success for {self.name} (rules-based)")
                            self.geocoding_result = result
                            return result
                        elif openai_api_key:
                            evaluation = self._evaluate_result(result, "Pelias Search", openai_api_key)
                            if evaluation and evaluation.get("quality") == "good":
                                logger.info(f"Pelias search success for {self.name} (LLM evaluation)")
                                self.geocoding_result = result
                                return result
                            else:
                                reason = evaluation.get('reason', 'No reason') if evaluation else 'LLM evaluation failed'
                                logger.info(f"Pelias search result poor for {self.name}: {reason}")
            except Exception as e:
                logger.warning(f"Pelias search failed for {self.name}: {e}")
        
        # Try Geocodio
        if geocodio_api_key:
            try:
                prep_data = self._prep()
                if "geocodio" in prep_data:
                    result = geocodio_search(
                        query=prep_data["geocodio"]["query"],
                        api_key=geocodio_api_key,
                        placetype=self._get_placetype()
                    )
                    if result:
                        if self._is_clear_match(result):
                            logger.info(f"Geocodio success for {self.name} (rules-based)")
                            self.geocoding_result = result
                            return result
                        elif openai_api_key:
                            evaluation = self._evaluate_result(result, "Geocodio", openai_api_key)
                            if evaluation and evaluation.get("quality") == "good":
                                logger.info(f"Geocodio success for {self.name} (LLM evaluation)")
                                self.geocoding_result = result
                                return result
                            else:
                                reason = evaluation.get('reason', 'No reason') if evaluation else 'LLM evaluation failed'
                                logger.info(f"Geocodio result poor for {self.name}: {reason}")
            except Exception as e:
                logger.warning(f"Geocodio failed for {self.name}: {e}")
        
        # Fallback to Nominatim
        try:
            prep_data = self._prep()
            if "nominatim" in prep_data:
                result = geocode_address(
                    address=prep_data["nominatim"]["query"],
                    user_agent="agate-ai-platform/1.0",
                    placetype=self._get_placetype()
                )
                if result:
                    if self._is_clear_match(result):
                        logger.info(f"Nominatim success for {self.name} (rules-based)")
                        self.geocoding_result = result
                        return result
                    elif openai_api_key:
                        evaluation = self._evaluate_result(result, "Nominatim", openai_api_key)
                        if evaluation and evaluation.get("quality") == "good":
                            logger.info(f"Nominatim success for {self.name} (LLM evaluation)")
                            self.geocoding_result = result
                            return result
                        else:
                            reason = evaluation.get('reason', 'No reason') if evaluation else 'LLM evaluation failed'
                            logger.info(f"Nominatim result poor for {self.name}: {reason}")
        except Exception as e:
            logger.warning(f"Nominatim failed for {self.name}: {e}")
        
        logger.warning(f"All geocoding services failed for {self.name}")
        return None