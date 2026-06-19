import asyncio, logging, json
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import Field
from agate_utils.geocoding.geocoding_types import (
    GeocodingResult,
    GeocodingResultData,
    GeometryPoint,
    GeometryPolygon,
    bbox_west_south_east_north_to_polygon_coordinates,
)
from agate_utils.geocoding.nominatim import NominatimGeocoder
from agate_utils.llm import call_llm
from .area import Area

logger = logging.getLogger(__name__)

########## NATURAL PLACE MODEL ##########

class NaturalPlace(Area):
    """Area model for natural features (lakes, mountains, rivers, forests)."""

    city: Optional[str] = Field(default=None, description="City or locality context")
    state: Optional[str] = Field(default=None, description="State or regional context")
    additional_context: Optional[str] = Field(
        default=None, description="Additional textual context from the document"
    )
    place_name: Optional[str] = Field(
        default=None, description="Name provided by the place component"
    )
    place_is_natural: bool = Field(
        default=False, description="Whether the upstream place component flagged this as natural"
    )

    _USER_AGENT = "agate-ai-platform/1.0"
    _prep_cache: Optional[Dict[str, Any]] = None

    ########## PRIVATE/HELPER METHODS ##########

    def _prep(self) -> Dict[str, Any]:
        if self._prep_cache:
            return self._prep_cache

        query = self._build_query()
        context = self._build_context_string()

        prep_data = {
            "nominatim": {"query": query, "limit": 50},
            "context": context,
        }

        self._prep_cache = prep_data
        logger.info("Prepared natural place query: %s", query)
        return prep_data

    def _build_query(self) -> str:
        if self.place_is_natural and self.place_name:
            parts = [self.place_name.strip()]
            if self.state_abbr:
                abbr = self.state_abbr.strip() if isinstance(self.state_abbr, str) else self.state_abbr
                if abbr:
                    parts.append(abbr)
            return ", ".join(part for part in parts if part)

        normalized = self.name.strip() if isinstance(self.name, str) else ""
        parts: List[str] = [normalized] if normalized else []

        if self.country:
            country = self.country.strip() if isinstance(self.country, str) else self.country
            if country and (not normalized or country.lower() not in normalized.lower()):
                parts.append(country)

        deduped: List[str] = []
        seen = set()
        for part in parts:
            normalized_part = part.strip() if isinstance(part, str) else part
            if normalized_part and normalized_part.lower() not in seen:
                deduped.append(normalized_part)
                seen.add(normalized_part.lower())

        return ", ".join(deduped)

    async def _search_nominatim(self, query: str, limit: int) -> List[Dict[str, Any]]:
        geocoder = NominatimGeocoder(user_agent=self._USER_AGENT)

        def _run_search() -> List[Dict[str, Any]]:
            return geocoder.search_raw(
                query=query,
                limit=limit,
                addressdetails=True,
                extratags=True,
                namedetails=True,
                layer="natural",
                dedupe=1,
            )

        results = await asyncio.to_thread(_run_search)
        logger.info("NaturalPlace Nominatim returned %d candidate(s)", len(results))
        return results

    def _choose_candidate_with_llm(
        self,
        candidates: List[Dict[str, Any]],
        openai_api_key: Optional[str],
        context: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        if not candidates:
            return None
        if not openai_api_key or len(candidates) == 1:
            return candidates[0]

        prompt = self._build_selection_prompt(candidates=candidates, context=context)
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
            logger.warning("NaturalPlace candidate selection LLM failed: %s", exc)
            return candidates[0]

        selected_index = payload.get("selected_index")
        confidence = payload.get("confidence", 0)
        if not isinstance(selected_index, int) or not (1 <= selected_index <= len(candidates)):
            logger.warning("NaturalPlace candidate selection returned invalid index: %s", selected_index)
            return candidates[0]

        if isinstance(confidence, (int, float)) and confidence < 40:
            logger.info(
                "NaturalPlace candidate selection confidence too low (%s). Falling back to first candidate.",
                confidence,
            )
            return candidates[0]

        return candidates[selected_index - 1]

    def _location_to_geocoding_result(
        self,
        candidate: Dict[str, Any],
        query: str,
    ) -> Optional[GeocodingResult]:
        bbox = self._parse_bounding_box(candidate.get("boundingbox"))
        geometry = self._geometry_from_candidate(candidate, bbox)
        if not geometry:
            logger.warning("NaturalPlace candidate missing valid geometry for %s", self.name)
            return None

        result_id = self._candidate_result_id(candidate)
        confidence_data: Dict[str, Any] = {
            "method": "nominatim_natural",
            "importance": candidate.get("importance"),
        }
        try:
            result = GeocodingResult(
                geocoder="nominatim_natural",
                input_str=query,
                result=GeocodingResultData(
                    id=result_id,
                    processed_str=candidate.get("display_name", self.name),
                    geometry=geometry,
                    confidence=confidence_data,
                ),
            )
        except Exception as exc:
            logger.error("NaturalPlace failed to build GeocodingResult: %s", exc)
            return None

        return result

    def _geometry_from_candidate(
        self,
        candidate: Dict[str, Any],
        bbox: Optional[List[float]],
    ) -> Optional[GeometryPolygon | GeometryPoint]:
        if bbox:
            west = bbox[1]
            south = bbox[0]
            east = bbox[3]
            north = bbox[2]
            try:
                if self._is_bbox_small(west, south, east, north):
                    lon = self._safe_float(candidate.get("lon"))
                    lat = self._safe_float(candidate.get("lat"))
                    if lon is not None and lat is not None:
                        return GeometryPoint(coordinates=[lon, lat])
                    return None
                return GeometryPolygon(
                    coordinates=bbox_west_south_east_north_to_polygon_coordinates([west, south, east, north]),
                )
            except Exception as exc:
                logger.debug("Invalid polygon for natural place: %s", exc)

        lon = self._safe_float(candidate.get("lon"))
        lat = self._safe_float(candidate.get("lat"))
        if lon is not None and lat is not None:
            try:
                return GeometryPoint(coordinates=[lon, lat])
            except Exception as exc:
                logger.debug("Invalid point geometry for natural place: %s", exc)
        return None

    def _is_bbox_small(self, west: float, south: float, east: float, north: float) -> bool:
        return abs(east - west) < 0.001 and abs(north - south) < 0.001

    def _estimate_bbox_with_llm(
        self,
        openai_api_key: Optional[str],
        context: Optional[str],
    ) -> Optional[GeocodingResult]:
        if not openai_api_key:
            logger.warning("NaturalPlace fallback bounding box requires an OpenAI API key.")
            return None

        prompt_path = Path(__file__).parent.parent.parent / "prompts" / "create_natural_bbox.md"
        try:
            template = prompt_path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:  # pragma: no cover - defensive
            logger.error("NaturalPlace fallback prompt missing: %s", exc)
            return None

        prompt = template.format(
            location_str=self.name,
            additional_prompting=context or "No additional context provided.",
        )

        try:
            response_text = call_llm(
                prompt=prompt,
                model=self._geographic_estimation_litellm_model(),
                openai_api_key=openai_api_key,
                force_json=True,
                model_config_id=self._geographic_estimation_model_config_id(),
            )
            payload = json.loads(response_text)
        except Exception as exc:
            logger.error("NaturalPlace fallback LLM failed: %s", exc)
            return None

        raw_bbox = payload.get("bounding_box") or payload.get("bbox")
        bbox = self._parse_bounding_box(raw_bbox)
        if not bbox or not self._is_valid_bbox(bbox):
            logger.warning(
                "NaturalPlace fallback produced invalid bounding box for '%s': %s (payload=%s)",
                self.name,
                raw_bbox,
                payload,
            )
            return None

        south, west, north, east = bbox
        min_lat, min_lon, max_lat, max_lon = south, west, north, east
        west, south, east, north = min_lon, min_lat, max_lon, max_lat

        try:
            geometry = GeometryPolygon(
                coordinates=bbox_west_south_east_north_to_polygon_coordinates([west, south, east, north]),
            )
        except Exception as exc:
            logger.error("NaturalPlace fallback polygon invalid: %s", exc)
            return None

        confidence = {
            "method": "llm_natural_estimate",
            "confidence": payload.get("confidence"),
        }

        center_lat = self._safe_float(payload.get("center_lat")) or (min_lat + max_lat) / 2
        center_lon = self._safe_float(payload.get("center_lon")) or (min_lon + max_lon) / 2

        result = GeocodingResult(
            geocoder="natural_llm_estimate",
            input_str=self.name,
            result=GeocodingResultData(
                id=self._build_fallback_id(),
                processed_str=f"{self.name} (LLM natural estimate)",
                geometry=geometry,
                confidence={"center": {"lat": center_lat, "lon": center_lon}, **confidence},
            ),
        )

        return result

    def _parse_bounding_box(self, bbox: Any) -> Optional[List[float]]:
        if bbox is None:
            return None
        try:
            if isinstance(bbox, dict):
                keys = ["south", "west", "north", "east"]
                if all(key in bbox for key in keys):
                    south = float(bbox["south"])
                    west = float(bbox["west"])
                    north = float(bbox["north"])
                    east = float(bbox["east"])
                    return [south, west, north, east]
                alt_keys = ["min_latitude", "min_longitude", "max_latitude", "max_longitude"]
                if all(key in bbox for key in alt_keys):
                    south = float(bbox["min_latitude"])
                    west = float(bbox["min_longitude"])
                    north = float(bbox["max_latitude"])
                    east = float(bbox["max_longitude"])
                    return [south, west, north, east]
            elif isinstance(bbox, (list, tuple)) and len(bbox) == 4:
                south, north, west, east = [float(value) for value in bbox]
                return [south, west, north, east]
        except (TypeError, ValueError):
            return None
        return None

    def _build_context_string(self) -> Optional[str]:
        context_bits = []
        if self.city:
            context_bits.append(f"City/locality: {self.city}")
        if self.state:
            context_bits.append(f"State/region: {self.state}")
        if self.additional_context:
            context_bits.append(self.additional_context)
        return "\n".join(context_bits) if context_bits else None

    def _build_selection_prompt(self, candidates: List[Dict[str, Any]], context: Optional[str]) -> str:
        prompt_path = Path(__file__).parent.parent.parent / "prompts" / "select_natural_candidate.md"
        try:
            template = prompt_path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:  # pragma: no cover - defensive
            raise FileNotFoundError(f"NaturalPlace selection prompt not found at {prompt_path}") from exc

        formatted_candidates: List[Dict[str, Any]] = []
        for idx, candidate in enumerate(candidates, start=1):
            formatted_candidates.append(
                {
                    "index": idx,
                    "display_name": candidate.get("display_name"),
                    "class": candidate.get("class"),
                    "type": candidate.get("type"),
                    "category": candidate.get("category"),
                    "importance": candidate.get("importance"),
                    "lat": self._safe_float(candidate.get("lat")),
                    "lon": self._safe_float(candidate.get("lon")),
                    "bounding_box": self._parse_bounding_box(candidate.get("boundingbox")),
                    "address": candidate.get("address"),
                    "osm_id": candidate.get("osm_id"),
                    "osm_type": candidate.get("osm_type"),
                }
            )

        context_part = f"\nContext from document: {context}" if context else ""
        candidates_json = json.dumps(formatted_candidates, indent=2, ensure_ascii=False)

        return template.format(
            location=self.name,
            context_part=context_part,
            candidates_json=candidates_json,
        )

    def _is_valid_bbox(self, bbox: List[float]) -> bool:
        if not isinstance(bbox, list) or len(bbox) != 4:
            return False
        try:
            min_lat, min_lon, max_lat, max_lon = [float(value) for value in bbox]
        except (TypeError, ValueError):
            return False
        if not (-90 <= min_lat <= 90 and -90 <= max_lat <= 90):
            return False
        if not (-180 <= min_lon <= 180 and -180 <= max_lon <= 180):
            return False
        if min_lat >= max_lat or min_lon >= max_lon:
            return False
        return True

    def _build_fallback_id(self) -> str:
        return f"natural_llm:{hash(self.name) & 0xFFFFFFFFFFFF:012x}"

    def _candidate_result_id(self, candidate: Dict[str, Any]) -> str:
        osm_type = str(candidate.get("osm_type", "")).lower()
        osm_id = candidate.get("osm_id")
        if osm_type and osm_id:
            return f"osm:{osm_type}:{osm_id}"
        return f"osm:natural:{hash(candidate.get('display_name', self.name)) & 0xFFFFFFFFFFFF:012x}"

    @staticmethod
    def _safe_float(value: Any) -> Optional[float]:
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    ########## PUBLIC METHODS ##########

    async def geocode(
        self,
        pelias_api_key: Optional[str] = None,
        geocodio_api_key: Optional[str] = None,
        openai_api_key: Optional[str] = None,
        **_: Dict[str, Any],
    ) -> Optional[GeocodingResult]:
        prep_data = self._prep()
        query = prep_data["nominatim"]["query"]
        limit = prep_data["nominatim"]["limit"]

        try:
            candidates = await self._search_nominatim(query=query, limit=limit)
        except Exception as exc:  # pragma: no cover - network/IO guarded
            logger.error("NaturalPlace Nominatim search failed for %s: %s", self.name, exc)
            candidates = []

        if candidates:
            chosen = self._choose_candidate_with_llm(
                candidates=candidates,
                openai_api_key=openai_api_key,
                context=prep_data.get("context"),
            )
            if chosen:
                result = self._location_to_geocoding_result(chosen, query)
                if result:
                    self.geocoding_result = result
                    return result
        else:
            logger.info("NaturalPlace Nominatim found no candidates for '%s'", self.name)

        logger.info("Falling back to LLM bounding box estimate for natural place '%s'", self.name)
        fallback_result = self._estimate_bbox_with_llm(
            openai_api_key=openai_api_key,
            context=prep_data.get("context"),
        )
        if fallback_result:
            self.geocoding_result = fallback_result
            return fallback_result

        logger.warning("NaturalPlace geocoding failed for '%s'", self.name)
        return None

