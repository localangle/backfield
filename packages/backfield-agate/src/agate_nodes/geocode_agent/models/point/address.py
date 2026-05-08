import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from agate_utils.geocoding.geocoding_types import GeocodingResult
from agate_utils.geocoding.pelias import (
    geocode_search as pelias_search,
    geocode_search_candidates,
    geocode_structured as pelias_structured,
)
from agate_utils.geocoding.geocodio import geocode_search as geocodio_search
from agate_utils.geocoding.nominatim import geocode_address
from agate_utils.llm import call_llm

from .point import Point

logger = logging.getLogger(__name__)

_ADDRESS_PICKER_PROMPT = Path(__file__).parent.parent.parent / "prompts" / "address_candidate_picker.md"

########## ADDRESS MODEL ##########

class Address(Point):
    """Model for address-level locations."""

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self._geocode_hints: Optional[str] = None
        self._original_text: Optional[str] = None

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

    def _address_candidate_rows(self, candidates: List[GeocodingResult]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for idx, cand in enumerate(candidates, start=1):
            label = ""
            coords: Optional[List[float]] = None
            if cand.result:
                label = cand.result.processed_str or ""
                geom = cand.result.geometry
                if getattr(geom, "type", None) == "Point":
                    coords = list(geom.coordinates)
            rows.append(
                {
                    "index": idx,
                    "label": label,
                    "coordinates": coords,
                    "confidence": None,
                }
            )
        return rows

    def _pick_pelias_candidate_with_llm(
        self,
        candidates: List[GeocodingResult],
        query: str,
        openai_api_key: str,
    ) -> Optional[GeocodingResult]:
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]

        try:
            template = _ADDRESS_PICKER_PROMPT.read_text(encoding="utf-8")
        except OSError as exc:
            logger.error("Address candidate picker prompt missing: %s", exc)
            return candidates[0]

        rows = self._address_candidate_rows(candidates)
        prompt = template.format(
            original_text=self._original_text or "",
            geocode_hints=self._geocode_hints_prompt_value(),
            query=query,
            candidates_json=json.dumps(rows, indent=2, ensure_ascii=False),
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
            logger.warning("Address candidate selection LLM failed: %s", exc)
            return candidates[0]

        selected_index = payload.get("selected_index")
        confidence = payload.get("confidence", 0)
        if not isinstance(selected_index, int) or not (1 <= selected_index <= len(candidates)):
            logger.warning("Address candidate selection returned invalid index: %s", selected_index)
            return candidates[0]

        if isinstance(confidence, (int, float)) and confidence < 40:
            logger.info(
                "Address candidate selection confidence too low (%s); using first candidate.",
                confidence,
            )
            return candidates[0]

        return candidates[selected_index - 1]

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

        # Pelias search: multi-candidate + LLM picker when OpenAI is available; else single search
        if pelias_api_key and openai_api_key:
            try:
                candidates = await geocode_search_candidates(
                    text=full_address,
                    api_key=pelias_api_key,
                    size=5,
                )
                if len(candidates) > 1:
                    picked = self._pick_pelias_candidate_with_llm(
                        candidates,
                        full_address,
                        openai_api_key,
                    )
                    if picked and self._is_good_point_result(picked):
                        logger.info("Pelias search + LLM picker success for %s", self.name)
                        self.geocoding_result = picked
                        return picked
                elif len(candidates) == 1 and self._is_good_point_result(candidates[0]):
                    logger.info("Pelias search (single candidate) success for %s", self.name)
                    self.geocoding_result = candidates[0]
                    return candidates[0]
            except Exception as exc:
                logger.warning("Pelias search candidates failed for %s: %s", self.name, exc)

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
