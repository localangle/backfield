import json, logging, os
from typing import Optional
from pydantic import Field
from agate_utils.geocoding.geocoding_types import (
    GeocodingResult,
    GeocodingResultData,
    GeometryPolygon,
    bbox_west_south_east_north_to_polygon_coordinates,
)
from agate_utils.llm import call_llm
from ...llm_auth import has_llm_auth
from .area import Area

logger = logging.getLogger(__name__)

########## HELPER FUNCTIONS ##########

def _load_prompt_template() -> str:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    prompt_path = os.path.join(current_dir, "..", "..", "prompts", "create_region_bbox.md")
    with open(prompt_path, "r", encoding="utf-8") as handle:
        return handle.read()

def _is_valid_bbox(bbox) -> bool:
    if not isinstance(bbox, list) or len(bbox) != 4:
        return False
    try:
        min_lat, min_lon, max_lat, max_lon = (float(value) for value in bbox)
    except (TypeError, ValueError):
        return False
    if not (-90 <= min_lat <= 90 and -90 <= max_lat <= 90):
        return False
    if not (-180 <= min_lon <= 180 and -180 <= max_lon <= 180):
        return False
    return min_lat < max_lat and min_lon < max_lon

########## REGION MODEL ##########

class Region(Area):
    """Area model for loosely defined regions estimated via LLM."""

    additional_context: Optional[str] = Field(
        default=None, description="Optional context to include in the LLM prompt."
    )

    ########## PRIVATE/HELPER METHODS ##########

    def _build_prompt(self) -> str:
        template = _load_prompt_template()
        additional = (
            f"\nAdditional context: {self.additional_context}"
            if self.additional_context
            else ""
        )
        return template.format(location_str=self.name, additional_prompting=additional)

    def _build_result_id(self) -> str:
        return f"region:{hash(self.name) & 0xFFFFFFFFFFFF:012x}"

    ########## PUBLIC METHODS ##########

    async def geocode(
        self,
        pelias_api_key: Optional[str] = None,
        geocodio_api_key: Optional[str] = None,
        openai_api_key: Optional[str] = None,
        **_: dict,
    ) -> Optional[GeocodingResult]:
        if not has_llm_auth(openai_api_key, self._geographic_estimation_model_config_id()):
            logger.warning("Region geocoding requires LLM auth (API key or model config).")
            return None

        prompt = self._build_prompt()

        try:
            response_text = call_llm(
                prompt=prompt,
                model=self._geographic_estimation_litellm_model(),
                force_json=True,
                openai_api_key=openai_api_key,
                model_config_id=self._geographic_estimation_model_config_id(),
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Region LLM call failed for %s: %s", self.name, exc)
            return None

        try:
            payload = json.loads(response_text)
        except json.JSONDecodeError as exc:
            logger.error("Failed to parse region LLM response for %s: %s", self.name, exc)
            return None

        bounding_box = payload.get("bounding_box")
        if not _is_valid_bbox(bounding_box):
            logger.warning("Invalid or missing bounding box for region '%s'", self.name)
            return None

        min_lat, min_lon, max_lat, max_lon = bounding_box
        west, south, east, north = min_lon, min_lat, max_lon, max_lat

        try:
            geometry = GeometryPolygon(
                coordinates=bbox_west_south_east_north_to_polygon_coordinates([west, south, east, north]),
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to build polygon for region '%s': %s", self.name, exc)
            return None

        confidence_data = {
            "method": "llm_region_estimate",
            "confidence": payload.get("confidence"),
            "center": {
                "lat": payload.get("center_lat"),
                "lon": payload.get("center_lon"),
            },
        }

        result = GeocodingResult(
            geocoder="region_llm",
            input_str=self.name,
            result=GeocodingResultData(
                id=self._build_result_id(),
                processed_str=f"{self.name} (region estimate)",
                geometry=geometry,
                confidence=confidence_data,
            ),
        )

        self.geocoding_result = result
        return result

