import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from agate_utils.geocoding.geocoding_types import (
    GeocodingResult,
    GeocodingResultData,
    GeometryPolygon,
    bbox_west_south_east_north_to_polygon_coordinates,
)
from agate_utils.geocoding.nominatim import geocode_address_raw
from agate_utils.geocoding.pelias import geocode_search_candidates as pelias_search_candidates
from agate_utils.llm import call_llm

from .area import Area

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "create_street_road_bounding_box.md"

_DIRECTIONAL_TOKENS = frozenset(
    {
        "n",
        "north",
        "s",
        "south",
        "e",
        "east",
        "w",
        "west",
        "ne",
        "nw",
        "se",
        "sw",
    }
)
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_ROUTE_RE = re.compile(
    r"^(?:(?P<scope>u\.?s\.?|us|united states|missouri|mo|illinois|il|"
    r"iowa|ia|kansas|ks|arkansas|ar|oklahoma|ok|texas|tx|"
    r"county|co|state|boone county|boone)\s+)?"
    r"(?:route|hwy|highway|rt|rte|interstate|i)\s+"
    r"(?P<label>[a-z0-9]+)$",
    flags=re.IGNORECASE,
)
_ROUTE_DASH_RE = re.compile(
    r"^(?P<scope>mo|us|il|ia|ks|ar|ok|tx|i|cr)[-\s]+(?P<label>[a-z0-9]+)$",
    flags=re.IGNORECASE,
)
_INTERSTATE_RE = re.compile(
    r"^(?:interstate|i)[-\s]*(?P<label>\d+[a-z]?)$",
    flags=re.IGNORECASE,
)
_COUNTY_ROUTE_RE = re.compile(
    r"^(?:(?P<county>[a-z]+(?:\s+county)?)\s+)?(?:county\s+)?(?:route|rd|road|cr)[-\s]+(?P<label>[a-z0-9]+)$",
    flags=re.IGNORECASE,
)

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


def _tokenize(text: str) -> list[str]:
    return [t for t in _NON_ALNUM_RE.sub(" ", (text or "").lower()).split() if t]


def _route_aliases(name: str) -> set[str]:
    """Normalize route spellings like Missouri Route J / MO-J / Route J."""
    raw = str(name or "").strip()
    aliases = {raw} if raw else set()
    compact = _NON_ALNUM_RE.sub(" ", raw.lower()).strip()
    compact = re.sub(r"\bu\s+s\b", "us", compact)
    compact = re.sub(r"\bunited\s+states\b", "us", compact)
    if not compact:
        return aliases

    interstate = _INTERSTATE_RE.match(compact)
    if interstate is not None:
        label = str(interstate.group("label") or "").strip().upper()
        if label:
            aliases.update(
                {
                    f"Interstate {label}",
                    f"I-{label}",
                    f"I {label}",
                    f"I{label}",
                }
            )
            return {a for a in aliases if a}

    # Prefer state/US highway patterns before the looser county-route matcher.
    match = _ROUTE_RE.match(compact) or _ROUTE_DASH_RE.match(compact)
    if match is not None:
        scope = str(match.groupdict().get("scope") or "").strip().lower()
        label = str(match.group("label") or "").strip().upper()
        if label:
            scope_aliases = {scope} if scope else set()
            if scope in {"missouri", "mo"}:
                scope_aliases.update({"mo", "missouri"})
            elif scope in {"u.s.", "us", "united states"}:
                scope_aliases.update({"us", "u.s."})
            elif scope in {"county", "co"} or "county" in scope:
                # Prefer CR-/County Route forms; avoid "CO-" which reads as Colorado.
                aliases.update(
                    {
                        f"Route {label}",
                        f"County Route {label}",
                        f"CR-{label}",
                        f"Co Rd {label}",
                        label,
                    }
                )
                if "county" in scope and not scope.endswith("county"):
                    aliases.add(f"{scope.title()} County Route {label}")
                elif scope.endswith("county"):
                    aliases.add(f"{scope.title()} Route {label}")
                return {a for a in aliases if a}
            elif scope in {"interstate", "i"}:
                aliases.update({f"Interstate {label}", f"I-{label}", f"I{label}"})
                return {a for a in aliases if a}

            for sc in scope_aliases or {""}:
                if sc:
                    aliases.add(f"{sc.upper()}-{label}")
                    aliases.add(f"{sc.title()} Route {label}")
                    aliases.add(f"{sc.upper()} Route {label}")
                    aliases.add(f"Route {label}")
                else:
                    aliases.add(f"Route {label}")
                    aliases.add(label)
            aliases.add(f"Route {label}")
            aliases.add(label)
            return {a for a in aliases if a}

    # County routes only when the string actually looks like one.
    if "county" in compact or compact.startswith("cr ") or compact.startswith("co rd"):
        county_route = _COUNTY_ROUTE_RE.match(compact)
        if county_route is not None:
            label = str(county_route.group("label") or "").strip().upper()
            county = str(county_route.groupdict().get("county") or "").strip()
            if label:
                aliases.update(
                    {
                        f"Route {label}",
                        f"County Route {label}",
                        f"CR-{label}",
                        f"Co Rd {label}",
                    }
                )
                if county:
                    aliases.add(f"{county.title()} Route {label}")
                return {a for a in aliases if a}

    return aliases


def street_name_heads_compatible(requested: str, candidate: str) -> bool:
    """Accept exact street heads or requested name plus a directional suffix only."""
    req_aliases = {tuple(_tokenize(a)) for a in _route_aliases(requested)}
    req_aliases = {tokens for tokens in req_aliases if tokens}
    cand_tokens = tuple(_tokenize(candidate))
    if not req_aliases or not cand_tokens:
        return False

    for req_tokens in req_aliases:
        if cand_tokens == req_tokens:
            return True
        if len(cand_tokens) == len(req_tokens) + 1 and cand_tokens[: len(req_tokens)] == req_tokens:
            if cand_tokens[-1] in _DIRECTIONAL_TOKENS:
                return True
        if len(cand_tokens) == len(req_tokens) + 1 and cand_tokens[1:] == req_tokens:
            if cand_tokens[0] in _DIRECTIONAL_TOKENS:
                return True
    return False


########## STREET ROAD MODEL ##########


class StreetRoad(Area):
    """Model for geocoding entire street/road spans."""

    def __init__(self, name: str, city: str = "", state: str = "", country: str = "US", **kwargs):
        super().__init__(name=name, city=city, state_abbr=state, country=country, **kwargs)
        self._geocode_hints: Optional[str] = None

    ########## PRIVATE/HELPER METHODS ##########

    def _city_agrees(self, conf: dict[str, Any]) -> bool:
        expected_city = str(self.city or "").strip().lower()
        if not expected_city:
            return True
        # Skip city gate when extract incorrectly copied the street into city.
        if expected_city == str(self.name or "").strip().lower():
            return True
        candidates = [
            str(conf.get("pelias_locality") or "").strip().lower(),
            str(conf.get("pelias_localadmin") or "").strip().lower(),
            str(conf.get("pelias_county") or "").strip().lower(),
        ]
        return any(expected_city and expected_city in cand for cand in candidates if cand)

    def _state_agrees(self, conf: dict[str, Any]) -> bool:
        expected = str(self.state_abbr or "").strip().upper()
        if not expected:
            return True
        region_a = str(conf.get("pelias_region_a") or "").strip().upper()[:2]
        if region_a and region_a == expected:
            return True
        region = str(conf.get("pelias_region") or "").strip().upper()
        return bool(region and expected in region)

    def _candidate_accepted(self, result: GeocodingResult) -> bool:
        if not result or not result.result:
            return False
        conf = result.result.confidence if isinstance(result.result.confidence, dict) else {}
        if str(conf.get("pelias_layer") or "").strip().lower() != "street":
            return False
        if not self._state_agrees(conf):
            return False
        if not self._city_agrees(conf):
            return False
        cand_name = str(conf.get("pelias_name") or result.result.processed_str or "")
        return street_name_heads_compatible(str(self.name or ""), cand_name)

    def _union_pelias_street_bboxes(
        self, candidates: list[GeocodingResult]
    ) -> Optional[GeocodingResult]:
        accepted = [c for c in candidates if self._candidate_accepted(c)]
        if not accepted:
            return None

        west_values: list[float] = []
        south_values: list[float] = []
        east_values: list[float] = []
        north_values: list[float] = []
        for cand in accepted:
            conf = cand.result.confidence if cand.result and isinstance(cand.result.confidence, dict) else {}
            bbox = conf.get("pelias_bbox")
            if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
                continue
            try:
                west, south, east, north = (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
            except (TypeError, ValueError):
                continue
            if not _validate_bbox(west, south, east, north):
                continue
            west_values.append(west)
            south_values.append(south)
            east_values.append(east)
            north_values.append(north)

        if not west_values:
            return None

        west = min(west_values)
        south = min(south_values)
        east = max(east_values)
        north = max(north_values)
        if not _validate_bbox(west, south, east, north):
            return None

        geometry = GeometryPolygon(
            type="Polygon",
            coordinates=bbox_west_south_east_north_to_polygon_coordinates([west, south, east, north]),
        )
        label = f"{self.name}, {self.city}, {self.state_abbr}".strip(", ")
        result_data = GeocodingResultData(
            id=f"pelias_street_union:{self.name.replace(' ', '_')}",
            processed_str=label or self.name,
            geometry=geometry,
            confidence={
                "method": "pelias_street_bbox_union",
                "segment_count": len(west_values),
                "accepted_candidates": len(accepted),
            },
        )
        return GeocodingResult(
            geocoder="pelias_street_union",
            input_str=label or self.name,
            result=result_data,
        )

    async def _geocode_pelias_street(self, pelias_api_key: str) -> Optional[GeocodingResult]:
        query_names = [self.name, *_route_aliases(self.name)]
        # Preserve insertion order while de-duplicating.
        seen: set[str] = set()
        ordered_names: list[str] = []
        for name in query_names:
            key = name.strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            ordered_names.append(name.strip())

        city_for_query = str(self.city or "").strip()
        if city_for_query.lower() == str(self.name or "").strip().lower():
            # Extract sometimes copies the street into city; omit it from the query.
            city_for_query = ""

        all_candidates: list[GeocodingResult] = []
        for name in ordered_names[:6]:
            text = ", ".join(p for p in [name, city_for_query, self.state_abbr or ""] if p)
            try:
                candidates = await pelias_search_candidates(
                    text=text,
                    api_key=pelias_api_key,
                    size=8,
                    layers="street",
                    **{"boundary.country": str(self.country or "US").lower()},
                )
            except Exception as exc:
                logger.warning("Pelias street search failed for %s: %s", text, exc)
                continue
            all_candidates.extend(candidates)

        return self._union_pelias_street_bboxes(all_candidates)

    async def _create_llm_bounding_box(
        self, raw_json: str, original_text: str, openai_api_key: str
    ) -> Optional[GeocodingResult]:
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
                model=self._geographic_estimation_litellm_model(),
                openai_api_key=openai_api_key,
                force_json=True,
                model_config_id=self._geographic_estimation_model_config_id(),
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
                coordinates=bbox_west_south_east_north_to_polygon_coordinates(
                    [west, south, east, north]
                ),
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
            coordinates=bbox_west_south_east_north_to_polygon_coordinates(
                [west, south, east, north]
            ),
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
        del geocodio_api_key  # unused — street spans use Pelias/Nominatim only
        logger.info("Geocoding street/road: %s in %s, %s", self.name, self.city, self.state_abbr)

        if pelias_api_key:
            try:
                pelias_result = await self._geocode_pelias_street(pelias_api_key)
                if pelias_result is not None:
                    logger.info("Pelias street bbox union success for %s", self.name)
                    self.geocoding_result = pelias_result
                    return pelias_result
            except Exception as exc:
                logger.warning("Pelias street geocode failed for %s: %s", self.name, exc)

        try:
            city_for_query = str(self.city or "").strip()
            if city_for_query.lower() == str(self.name or "").strip().lower():
                city_for_query = ""
            query = _query_string(self.name, city_for_query, self.state_abbr, self.country)
            raw_json = geocode_address_raw(address=query, user_agent="agate/1.0", limit=20)
            if not raw_json:
                # Try route aliases when the extract used a verbose route name.
                for alias in sorted(_route_aliases(self.name)):
                    if alias == self.name:
                        continue
                    alt_query = _query_string(alias, city_for_query, self.state_abbr, self.country)
                    raw_json = geocode_address_raw(address=alt_query, user_agent="agate/1.0", limit=20)
                    if raw_json:
                        query = alt_query
                        break
            if not raw_json:
                logger.warning("No response from Nominatim for: %s", query)
                return None

            if openai_api_key and original_text:
                llm_result = await self._create_llm_bounding_box(
                    raw_json, original_text, openai_api_key
                )
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
