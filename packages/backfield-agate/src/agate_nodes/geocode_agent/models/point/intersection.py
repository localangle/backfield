"""Intersection geocoding model for road intersections."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from agate_utils.geocoding.geocodio import geocode_search as geocodio_search, is_valid_intersection_result
from agate_utils.geocoding.geocoding_types import GeocodingResult, GeocodingResultData, GeometryPoint
from agate_utils.geocoding.overpass import find_intersection_coordinates_from_text
from agate_utils.llm import call_llm

from .point import Point

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).resolve().parent.parent.parent / "prompts" / "estimate_intersection_point.md"
_MIN_LLM_CONFIDENCE = 40

########## INTERSECTION MODEL ##########


class Intersection(Point):
    """Model for street or highway intersections."""

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self._original_text: Optional[str] = None
        self._geocode_hints: Optional[str] = None

    ########## PRIVATE/HELPER METHODS ##########

    def _geocode_hints_prompt_value(self) -> str:
        raw = (self._geocode_hints or "").strip()
        return raw if raw else "(none)"

    def _geographic_reasoning_litellm_model(self) -> str:
        raw = getattr(self, "_geographic_reasoning_llm_model", None)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
        return "gpt-5-nano"

    def _geographic_reasoning_model_config_id(self) -> str | None:
        raw = getattr(self, "_geographic_reasoning_ai_model_config_id", None)
        if raw is None:
            return None
        s = str(raw).strip()
        return s or None

    @staticmethod
    def _safe_float(value: object) -> float | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value.strip())
            except ValueError:
                return None
        return None

    @staticmethod
    def _valid_lat_lon(lat: float, lon: float) -> bool:
        return -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0

    def _build_llm_estimate_id(self) -> str:
        return f"intersection_llm:{hash(self.name) & 0xFFFFFFFFFFFF:012x}"

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
            if self._geocode_hints and self._geocode_hints.strip():
                search_text = f"{search_text}\n\nGeocode hints: {self._geocode_hints.strip()}"
            intersections, queries = await find_intersection_coordinates_from_text(search_text, openai_api_key)
            for idx, query in enumerate(queries):
                logger.info("Overpass query %d for %s: %s", idx + 1, self.name, query[:200])

            if not intersections:
                return None

            point = intersections[0].get("point")
            if not point:
                return None

            lat, lon = point.y, point.x

            result_data = GeocodingResultData(
                id=f"overpass:{lon:.6f},{lat:.6f}",
                processed_str=self.name,
                geometry=GeometryPoint(type="Point", coordinates=[lon, lat]),
                confidence={},
            )
            return GeocodingResult(geocoder="overpass", input_str=self.name, result=result_data)
        except Exception as exc:
            logger.error("Overpass geocoding failed for %s: %s", self.name, exc)
            return None

    def _try_llm_point_estimate(self, openai_api_key: Optional[str]) -> Optional[GeocodingResult]:
        if not openai_api_key:
            logger.warning("Intersection LLM estimate requires an OpenAI API key.")
            return None

        try:
            template = _PROMPT_PATH.read_text(encoding="utf-8")
        except OSError as exc:
            logger.error("Intersection LLM estimate prompt missing: %s", exc)
            return None

        prompt = template.format(
            intersection_text=self.name,
            original_text=(self._original_text or "").strip() or "(none)",
            geocode_hints=self._geocode_hints_prompt_value(),
            city=(self.city or "").strip() or "(unknown)",
            state_abbr=(self.state_abbr or "").strip() or "(unknown)",
            country=(self.country or "US").strip() or "US",
        )

        try:
            response_text = call_llm(
                prompt=prompt,
                model=self._geographic_reasoning_litellm_model(),
                openai_api_key=openai_api_key,
                force_json=True,
                model_config_id=self._geographic_reasoning_model_config_id(),
            )
            payload = json.loads(response_text)
        except Exception as exc:
            logger.error("Intersection LLM estimate failed for %s: %s", self.name, exc)
            return None

        lat = self._safe_float(payload.get("lat"))
        lon = self._safe_float(payload.get("lon"))
        confidence = payload.get("confidence", 0)
        if lat is None or lon is None or not self._valid_lat_lon(lat, lon):
            logger.warning("Intersection LLM estimate returned invalid coordinates for %s", self.name)
            return None

        if isinstance(confidence, (int, float)) and confidence < _MIN_LLM_CONFIDENCE:
            logger.info(
                "Intersection LLM estimate confidence too low (%s) for %s",
                confidence,
                self.name,
            )
            return None

        result_data = GeocodingResultData(
            id=self._build_llm_estimate_id(),
            processed_str=f"{self.name} (LLM intersection estimate)",
            geometry=GeometryPoint(type="Point", coordinates=[lon, lat]),
            confidence={
                "method": "llm_intersection_estimate",
                "confidence": confidence,
                "reasoning": payload.get("reasoning"),
            },
        )
        return GeocodingResult(
            geocoder="intersection_llm_estimate",
            input_str=self.name,
            result=result_data,
        )

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

        logger.info("Falling back to LLM point estimate for intersection '%s'", self.name)
        llm_result = self._try_llm_point_estimate(openai_api_key)
        if llm_result:
            self.geocoding_result = llm_result
            return llm_result

        logger.warning("All intersection geocoding methods failed for %s", self.name)
        return None
