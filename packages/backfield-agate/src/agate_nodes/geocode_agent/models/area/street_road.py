import json
import logging
from pathlib import Path
from typing import Optional, List, Dict
from agate_utils.geocoding.geocoding_types import (
    GeocodingResult,
    GeocodingResultData,
    GeometryPolygon,
    bbox_west_south_east_north_to_polygon_coordinates,
)
from agate_utils.geocoding.nominatim import geocode_address_raw
from agate_utils.llm import call_llm
from .area import Area

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "create_street_road_bounding_box.md"

########## HELPER FUNCTIONS ##########

def _load_prompt() -> str:
    with PROMPT_PATH.open("r", encoding="utf-8") as handle:
        return handle.read()

def _validate_bbox(west: float, south: float, east: float, north: float) -> bool:
    if not (-180 <= west <= 180) or not (-180 <= east <= 180):
        return False
    if not (-90 <= south <= 90) or not (-90 <= north <= 90):
        return False
    return west < east and south < north

def _query_string(name: str, city: str, state: str, country: str) -> str:
    parts = [name]
    if city:
        parts.append(city)
    if state:
        parts.append(state)
    parts.append(country or "US")
    return ", ".join(parts)

########## STREET ROAD MODEL ##########

class StreetRoad(Area):
    """Model for geocoding entire street/road spans."""

    def __init__(self, name: str, city: str = "", state: str = "", country: str = "US", **kwargs):
        super().__init__(name=name, city=city, state_abbr=state, country=country, **kwargs)
        self._geocode_hints: Optional[str] = None

    ########## PRIVATE/HELPER METHODS ##########

    async def _create_llm_bounding_box(self, raw_json: str, original_text: str, openai_api_key: str) -> Optional[GeocodingResult]:
        try:
            geocode_hints = (self._geocode_hints or "").strip() or "(none)"
            prompt = _load_prompt().format(
                street_name=self.name,
                city=self.city,
                state_abbr=self.state_abbr,
                original_text=original_text,
                geocode_hints=geocode_hints,
                raw_nominatim_data=raw_json,
            )

            response = call_llm(
                prompt=prompt,
                model=self._geographic_reasoning_litellm_model(),
                openai_api_key=openai_api_key,
                force_json=True,
                model_config_id=self._geographic_reasoning_model_config_id(),
            )

            bbox_data = json.loads(response.strip())
            if not all(key in bbox_data for key in ("west", "south", "east", "north")):
                logger.warning("LLM response missing required bounding box fields")
                return None

            west = float(bbox_data["west"])
            south = float(bbox_data["south"])
            east = float(bbox_data["east"])
            north = float(bbox_data["north"])
            if not _validate_bbox(west, south, east, north):
                logger.warning("Invalid bounding box from LLM: %s", bbox_data)
                return None

            geometry = GeometryPolygon(
                type="Polygon",
                coordinates=bbox_west_south_east_north_to_polygon_coordinates([west, south, east, north]),
            )
            result_data = GeocodingResultData(
                id=f"street_road_llm_{self.name.replace(' ', '_')}",
                processed_str=f"{self.name} (LLM bounding box)",
                geometry=geometry,
                confidence={
                    "llm_reasoning": bbox_data.get("reasoning"),
                    "selected_segments": bbox_data.get("selected_segments", []),
                },
            )

            return GeocodingResult(
                geocoder="nominatim_llm_raw",
                input_str=f"{self.name} {self.city} {self.state_abbr}".strip(),
                result=result_data,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Error creating LLM bounding box from raw JSON: %s", exc)
            return None

    def _create_bbox_from_raw_data(self, raw_data: List[Dict]) -> Optional[GeocodingResult]:
        if not raw_data:
            return None

        west_values: List[float] = []
        south_values: List[float] = []
        east_values: List[float] = []
        north_values: List[float] = []

        for segment in raw_data:
            bbox = segment.get("boundingbox", [])
            if len(bbox) == 4:
                south, north, west, east = map(float, bbox)
                west_values.append(west)
                south_values.append(south)
                east_values.append(east)
                north_values.append(north)

        if not west_values:
            logger.warning("No valid bounding boxes found in raw data")
            return None

        west = min(west_values)
        south = min(south_values)
        east = max(east_values)
        north = max(north_values)

        if not _validate_bbox(west, south, east, north):
            logger.warning("Combined bounding box invalid for %s", self.name)
            return None

        geometry = GeometryPolygon(
            type="Polygon",
            coordinates=bbox_west_south_east_north_to_polygon_coordinates([west, south, east, north]),
        )
        result_data = GeocodingResultData(
            id=f"street_road_combined_{self.name.replace(' ', '_')}",
            processed_str=f"{self.name} (combined from {len(raw_data)} raw segments)",
            geometry=geometry,
            confidence={"method": "combined_all_raw_segments"},
        )

        return GeocodingResult(
            geocoder="nominatim_raw_combined",
            input_str=f"{self.name} {self.city} {self.state_abbr}".strip(),
            result=result_data,
        )

    ########## PUBLIC METHODS ##########

    async def geocode(
        self,
        pelias_api_key: Optional[str] = None,
        geocodio_api_key: Optional[str] = None,
        openai_api_key: Optional[str] = None,
        original_text: Optional[str] = None,
    ) -> Optional[GeocodingResult]:
        logger.info("Geocoding street/road: %s in %s, %s", self.name, self.city, self.state_abbr)

        try:
            query = _query_string(self.name, self.city, self.state_abbr, self.country)
            raw_json = geocode_address_raw(address=query, user_agent="agate-ai-platform/1.0", limit=20)
            if not raw_json:
                logger.warning("No response from Nominatim for: %s", query)
                return None

            if openai_api_key and original_text:
                llm_result = await self._create_llm_bounding_box(raw_json, original_text, openai_api_key)
                if llm_result:
                    self.geocoding_result = llm_result
                    return llm_result

            try:
                raw_data = json.loads(raw_json)
            except json.JSONDecodeError as exc:
                logger.error("Failed to parse Nominatim JSON response: %s", exc)
                return None

            bbox_result = self._create_bbox_from_raw_data(raw_data)
            if bbox_result:
                self.geocoding_result = bbox_result
                return bbox_result

            logger.warning("Failed to create bounding box from Nominatim response")
            return None
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Error geocoding street/road %s: %s", self.name, exc)
            return None
