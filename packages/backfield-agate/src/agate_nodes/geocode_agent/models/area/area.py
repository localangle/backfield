import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from agate_utils.geocoding.geocoding_types import GeocodingResult
from agate_utils.geocoding.pelias import (
    geocode_search_candidates as pelias_search_candidates,
    geocode_structured_candidates as pelias_structured_candidates,
)
from agate_utils.geocoding.geocodio import geocode_search as geocodio_search
from agate_utils.geocoding.nominatim import geocode_address
from agate_utils.llm import call_llm
from ..base import Location

logger = logging.getLogger(__name__)

########## BASE AREA MODEL ##########

class Area(Location):
    """Base class for area-type locations."""

    ########## PRIVATE/HELPER METHODS ##########

    @staticmethod
    def _is_wof_candidate(result: GeocodingResult) -> bool:
        if not result or not result.result:
            return False
        conf = result.result.confidence or {}
        src = str(conf.get("pelias_source") or "").strip().lower()
        gid = str(conf.get("pelias_gid") or result.result.id or "").strip().lower()
        return src == "whosonfirst" or gid.startswith("whosonfirst:")

    @staticmethod
    def _candidate_has_bbox(result: GeocodingResult) -> bool:
        if not result or not result.result:
            return False
        conf = result.result.confidence or {}
        if conf.get("pelias_has_bbox") is True:
            return True
        geom = getattr(result.result, "geometry", None)
        return getattr(geom, "type", None) == "Polygon"

    @staticmethod
    def _candidate_layer(result: GeocodingResult) -> str:
        if not result or not result.result:
            return ""
        conf = result.result.confidence or {}
        return str(conf.get("pelias_layer") or "").strip().lower()

    def _score_area_candidate(self, result: GeocodingResult, *, expected_layer: str) -> int:
        """Deterministic score; higher is better. Area models prefer WOF and bbox."""
        if not result or not result.result:
            return -10_000
        layer = self._candidate_layer(result)
        if expected_layer and layer and layer != expected_layer:
            return -10_000

        conf = result.result.confidence or {}
        score = 0

        # Strongly prefer WOF for admin/area layers.
        if self._is_wof_candidate(result):
            score += 100

        # Prefer bbox/polygon extents.
        if self._candidate_has_bbox(result):
            score += 20

        mt = str(conf.get("pelias_match_type") or "").strip().lower()
        if mt == "exact":
            score += 10

        # Prefer candidates whose label includes the queried name.
        try:
            label = str(result.result.processed_str or "").lower()
            name_lower = str(self.name or "").lower()
            if name_lower and name_lower in label:
                score += 5
        except Exception:
            pass

        return score

    def _choose_best_area_candidate(
        self, candidates: list[GeocodingResult], *, expected_layer: str
    ) -> GeocodingResult | None:
        if not candidates:
            return None
        scored = sorted(
            ((self._score_area_candidate(c, expected_layer=expected_layer), c) for c in candidates),
            key=lambda pair: pair[0],
            reverse=True,
        )
        best_score, best = scored[0]
        if best_score < 0:
            return None
        return best

    def _adjudicate_area_candidates_with_llm(
        self,
        *,
        candidates: list[GeocodingResult],
        expected_layer: str,
        openai_api_key: str,
    ) -> GeocodingResult | None:
        """Use LLM to pick among multiple plausible area candidates."""
        if not candidates:
            return None

        try:
            prompt_path = Path(__file__).parent.parent.parent / "prompts" / "choose_area_candidate.md"
            template = prompt_path.read_text(encoding="utf-8")
        except Exception as exc:
            logger.warning("Missing choose_area_candidate prompt: %s", exc)
            return None

        simplified: list[dict[str, Any]] = []
        for c in candidates:
            if not c or not c.result:
                continue
            conf = c.result.confidence or {}
            simplified.append(
                {
                    "label": c.result.processed_str,
                    "id": c.result.id,
                    "layer": conf.get("pelias_layer"),
                    "source": conf.get("pelias_source"),
                    "country_code": conf.get("pelias_country_code"),
                    "region": conf.get("pelias_region"),
                    "region_a": conf.get("pelias_region_a"),
                    "locality": conf.get("pelias_locality"),
                    "localadmin": conf.get("pelias_localadmin"),
                    "neighbourhood": conf.get("pelias_neighbourhood"),
                    "borough": conf.get("pelias_borough"),
                    "match_type": conf.get("pelias_match_type"),
                    "accuracy": conf.get("pelias_accuracy"),
                    "has_bbox": bool(conf.get("pelias_has_bbox")),
                }
            )

        original_text = str(getattr(self, "_original_text", "") or "")
        geocode_hints = str(getattr(self, "_geocode_hints", "") or "")
        # Some area types have `state` or `city` fields; pull best-effort hints.
        region_hint = str(getattr(self, "state", "") or getattr(self, "state_abbr", "") or "")
        locality_hint = str(getattr(self, "city", "") or "")
        country_code = str(self.country or "").strip().upper()

        prompt = template.format(
            query_name=self.name,
            expected_layer=expected_layer,
            country_code=country_code,
            region_hint=region_hint,
            locality_hint=locality_hint,
            original_text=original_text,
            geocode_hints=geocode_hints,
            candidates_json=json.dumps(simplified, indent=2),
        )

        try:
            response_text = call_llm(
                prompt=prompt,
                model=self._evaluation_litellm_model(),
                openai_api_key=openai_api_key,
                force_json=True,
                model_config_id=getattr(self, "_evaluation_ai_model_config_id", None),
            )
            payload = json.loads(response_text)
        except Exception as exc:
            logger.warning("Area candidate adjudication LLM failed: %s", exc)
            return None

        if payload.get("needs_review") is True:
            return None

        idx = payload.get("selected_index")
        if not isinstance(idx, int) or not (1 <= idx <= len(simplified)):
            return None
        # idx is 1-indexed over our filtered/simplified list, which aligns with candidates iteration order above.
        # Rebuild that order: pick from candidates in the same sequence.
        chosen_candidates: list[GeocodingResult] = [c for c in candidates if c and c.result]
        if idx <= len(chosen_candidates):
            return chosen_candidates[idx - 1]
        return None

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

    def _geographic_estimation_litellm_model(self) -> str:
        raw = getattr(self, "_geographic_estimation_llm_model", None)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
        return self._geographic_reasoning_litellm_model()

    def _geographic_estimation_model_config_id(self) -> str | None:
        raw = getattr(self, "_geographic_estimation_ai_model_config_id", None)
        if raw is not None:
            s = str(raw).strip()
            if s:
                return s
        return self._geographic_reasoning_model_config_id()

    def _evaluation_litellm_model(self) -> str:
        raw = getattr(self, "_evaluation_llm_model", None)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
        return "gpt-5-nano"

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

            model_name = self._evaluation_litellm_model()
            response = call_llm(
                prompt=prompt,
                model=model_name,
                openai_api_key=openai_api_key,
                model_config_id=getattr(self, "_evaluation_ai_model_config_id", None),
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
        """Geocode an area using Pelias candidates → Geocodio → Nominatim fallback chain."""
        logger.info(f"Geocoding area: {self.name}")
        
        # Try Pelias structured candidates first (most accurate for areas with known components)
        if pelias_api_key:
            try:
                prep_data = self._prep()
                if "pelias_structured" in prep_data:
                    structured_params = dict(prep_data["pelias_structured"])
                    expected_layer = str(structured_params.get("layers") or "").strip().lower()
                    candidates = await pelias_structured_candidates(
                        api_key=pelias_api_key,
                        **structured_params,
                    )
                    chosen = self._choose_best_area_candidate(candidates, expected_layer=expected_layer)
                    if chosen is not None:
                        logger.info(
                            "Pelias structured selected for %s (layer=%s wof=%s bbox=%s)",
                            self.name,
                            expected_layer,
                            self._is_wof_candidate(chosen),
                            self._candidate_has_bbox(chosen),
                        )
                        self.geocoding_result = chosen
                        return chosen
                    # LLM adjudication only when multiple plausible candidates exist.
                    if openai_api_key and len(candidates) >= 2:
                        llm_pick = self._adjudicate_area_candidates_with_llm(
                            candidates=candidates,
                            expected_layer=expected_layer,
                            openai_api_key=openai_api_key,
                        )
                        if llm_pick is not None:
                            logger.info(
                                "Pelias structured LLM-selected for %s (layer=%s wof=%s bbox=%s)",
                                self.name,
                                expected_layer,
                                self._is_wof_candidate(llm_pick),
                                self._candidate_has_bbox(llm_pick),
                            )
                            self.geocoding_result = llm_pick
                            return llm_pick
            except Exception as e:
                logger.warning(f"Pelias structured failed for {self.name}: {e}")
        
        # Try Pelias search candidates
        if pelias_api_key:
            try:
                prep_data = self._prep()
                if "pelias_search" in prep_data:
                    search_params = dict(prep_data["pelias_search"])
                    text = str(search_params.pop("text") or "").strip()
                    expected_layer = str(search_params.get("layers") or "").strip().lower()
                    if text:
                        candidates = await pelias_search_candidates(
                            text=text,
                            api_key=pelias_api_key,
                            **search_params,
                        )
                        chosen = self._choose_best_area_candidate(candidates, expected_layer=expected_layer)
                        if chosen is not None:
                            logger.info(
                                "Pelias search selected for %s (layer=%s wof=%s bbox=%s)",
                                self.name,
                                expected_layer,
                                self._is_wof_candidate(chosen),
                                self._candidate_has_bbox(chosen),
                            )
                            self.geocoding_result = chosen
                            return chosen
                        if openai_api_key and len(candidates) >= 2:
                            llm_pick = self._adjudicate_area_candidates_with_llm(
                                candidates=candidates,
                                expected_layer=expected_layer,
                                openai_api_key=openai_api_key,
                            )
                            if llm_pick is not None:
                                logger.info(
                                    "Pelias search LLM-selected for %s (layer=%s wof=%s bbox=%s)",
                                    self.name,
                                    expected_layer,
                                    self._is_wof_candidate(llm_pick),
                                    self._candidate_has_bbox(llm_pick),
                                )
                                self.geocoding_result = llm_pick
                                return llm_pick
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