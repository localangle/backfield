import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from agate_utils.geocoding.geocoding_types import GeocodingResult
from agate_utils.geocoding.geocodio import (
    geocode_search as geocodio_search,
    is_acceptable_geocodio_accuracy,
)
from agate_utils.geocoding.pelias import (
    geocode_search as pelias_search,
    geocode_search_candidates,
    geocode_structured as pelias_structured,
    geocode_structured_candidates,
)
from agate_utils.llm import call_llm
from agate_utils.search import (
    SearchResponse,
    brave_place_search,
    brave_web_search,
    search_web_duckduckgo,
)

from ...llm_auth import has_llm_auth
from ...poi_evidence import (
    components_from_place_fields,
    is_decisive_pelias_candidate,
    select_uniquely_decisive_candidate,
)
from .address import Address

logger = logging.getLogger(__name__)


class ExtractedAddress(BaseModel):
    """Typed result from address-evidence adjudication."""

    address_found: bool
    street: str | None = None
    city: str | None = None
    state: str | None = None
    zipcode: str | None = None
    country: str | None = None
    evidence_indexes: list[int] = Field(default_factory=list)


########## PLACE MODEL ##########

class Place(Address):
    """Model for place-level locations (POIs, landmarks, venues, etc.)."""

    street_address: Optional[str] = Field(
        default=None,
        description="Extracted street line from PlaceExtract components.address",
    )

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        raw = self.street_address
        if isinstance(raw, str):
            cleaned = raw.strip()
            object.__setattr__(self, "street_address", cleaned or None)
        self._input_addressability: Optional[bool] = None
        self._original_text: Optional[str] = None
        self._geocode_hints: Optional[str] = None
        self._failure_reason: Optional[str] = None
        self._web_search_used: bool = False
        self._web_search_fallback_used: bool = False
        self._address_search_attempts: list[dict[str, Any]] = []
        self._address_source: str | None = None

    def _geocode_hints_prompt_value(self) -> str:
        raw = (self._geocode_hints or "").strip()
        return raw if raw else "(none)"

    def _extract_components(self) -> dict[str, Any]:
        return components_from_place_fields(
            name=self.name,
            street_address=self.street_address,
            city=self.city,
            state_abbr=self.state_abbr,
            country=self.country,
        )

    ########## PRIVATE/HELPER METHODS ##########

    def _prep(self) -> Dict[str, Any]:
        street = (self.street_address or "").strip()
        parts = [self.name]
        if street:
            parts.append(street)
        if self.city:
            parts.append(self.city)
        if self.state_abbr:
            parts.append(self.state_abbr)
        if self.country:
            parts.append(self.country)
        full_place = ", ".join(parts)

        # Prefer the extracted street line for structured Pelias when present so
        # house-number QA can pass; venue name remains in free-text search.
        structured_address = street if street else self.name

        return {
            "pelias_structured": {
                "address": structured_address,
                "locality": self.city or None,
                "region": self.state_abbr or None,
                "country": self.country or "USA",
            },
            "full_place": full_place,
            # Address.geocode reads ``full_address``; keep alias for Place fallthrough.
            "full_address": full_place,
        }

    def _check_if_addressable(self, openai_api_key: str) -> str:
        try:
            prompt_path = Path(__file__).parent.parent.parent / "prompts" / "check_if_addressable.md"
            template = prompt_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            logger.error("Check if addressable prompt not found")
            return "addressable"

        location_parts = [self.name]
        if self.city:
            location_parts.append(self.city)
        if self.state_abbr:
            location_parts.append(self.state_abbr)
        full_location = ", ".join(location_parts)

        try:
            prompt = template.format(location=full_location)
            result = call_llm(
                prompt=prompt,
                model=self._geographic_reasoning_litellm_model(),
                openai_api_key=openai_api_key,
                force_json=False,
                model_config_id=self._geographic_reasoning_model_config_id(),
            )
            decision = result.strip()
            logger.info("Addressability check for '%s': %s", full_location, decision)
            return decision
        except Exception as exc:
            logger.error("Error checking if addressable for %s: %s", full_location, exc)
            return "addressable"

    def _generate_search_query(self, original_text: str, openai_api_key: str) -> str:
        try:
            prompt_path = Path(__file__).parent.parent.parent / "prompts" / "generate_search_query.md"
            template = prompt_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            logger.error("Generate search query prompt not found")
            return self._generate_deterministic_query()

        context_parts = [self.name]
        if self.city:
            context_parts.append(self.city)
        if self.state_abbr:
            context_parts.append(self.state_abbr)
        location_context = ", ".join(context_parts)

        try:
            prompt = template.format(
                place_name=self.name,
                location_context=location_context,
                original_text=original_text,
                geocode_hints=self._geocode_hints_prompt_value(),
            )
            result = call_llm(
                prompt=prompt,
                model=self._geographic_reasoning_litellm_model(),
                openai_api_key=openai_api_key,
                force_json=False,
                model_config_id=self._geographic_reasoning_model_config_id(),
            )
            return result.strip()
        except Exception as exc:
            logger.error("Error generating search query for %s: %s", self.name, exc)
            return self._generate_deterministic_query()

    def _generate_deterministic_query(self) -> str:
        query_parts = [f"Address for {self.name}"]
        if self.city:
            query_parts.append(self.city)
        if self.state_abbr:
            query_parts.append(self.state_abbr)
        return ", ".join(query_parts)

    def _country_code_for_search(self) -> str | None:
        country = str(self.country or "").strip().upper()
        if country in {"US", "USA", "UNITED STATES"}:
            return "US"
        return country if len(country) == 2 else None

    def _record_address_search_attempt(
        self,
        provider: str,
        response: SearchResponse | None,
        outcome: str,
    ) -> None:
        result_count = len(response.results) if response is not None else 0
        self._address_search_attempts.append(
            {
                "provider": provider,
                "result_count": result_count,
                "outcome": outcome,
            }
        )
        logger.info(
            "Geocode address search provider=%s place=%r result_count=%d outcome=%s",
            provider,
            self.name,
            result_count,
            outcome,
        )

    def _complete_extracted_address(
        self,
        extracted: ExtractedAddress,
        *,
        result_count: int,
    ) -> ExtractedAddress | None:
        if not extracted.address_found:
            return None

        street = str(extracted.street or "").strip()
        city = str(extracted.city or self.city or "").strip()
        state = str(extracted.state or self.state_abbr or "").strip()
        country = str(extracted.country or self.country or "").strip()
        country_upper = country.upper()
        if not street or not city or not country:
            return None
        if country_upper in {"US", "USA", "UNITED STATES"} and not re.search(
            r"\b\d+[A-Za-z]?\b", street
        ):
            return None

        evidence_indexes = [
            index for index in extracted.evidence_indexes if 0 <= index < result_count
        ]
        return extracted.model_copy(
            update={
                "street": street,
                "city": city,
                "state": state or None,
                "country": country,
                "evidence_indexes": evidence_indexes,
            }
        )

    def _extract_and_parse_address(
        self,
        search_query: str,
        search_results: SearchResponse,
        openai_api_key: str,
    ) -> ExtractedAddress | None:
        try:
            prompt_path = Path(__file__).parent.parent.parent / "prompts" / "extract_best_address.md"
            template = prompt_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            logger.error("Extract best address prompt not found")
            return None

        try:
            formatted_results = [
                {
                    "index": index,
                    "title": result.title,
                    "url": result.url,
                    "snippet": result.snippet,
                }
                for index, result in enumerate(search_results.results)
            ]
            prompt = template.format(
                original_text=self._original_text or "",
                geocode_hints=self._geocode_hints_prompt_value(),
                query=search_query,
                search_results=json.dumps(formatted_results, indent=2),
            )
            result = call_llm(
                prompt=prompt,
                model=self._geographic_reasoning_litellm_model(),
                openai_api_key=openai_api_key,
                force_json=True,
                model_config_id=self._geographic_reasoning_model_config_id(),
            )
            extracted = ExtractedAddress.model_validate_json(result)
            return self._complete_extracted_address(
                extracted,
                result_count=len(search_results.results),
            )
        except Exception as exc:
            logger.error("Error extracting address for %s: %s", self.name, exc)
            return None

    def _update_prep_with_address(self, address_data: Dict[str, str]) -> Dict[str, Any]:
        street = str(address_data.get("street") or "").strip()
        if street:
            self.street_address = street
        city = str(address_data.get("city") or "").strip()
        if city:
            self.city = city
        state = str(address_data.get("state") or "").strip()
        if state:
            self.state_abbr = state
        zipcode = str(address_data.get("zipcode") or "").strip()
        country = str(address_data.get("country") or self.country or "USA").strip()

        address_parts = [street or None, city or None, state or None, zipcode or None]
        full_address = ", ".join(part for part in address_parts if part)

        # Keep venue name in free-text query when we discovered a street line.
        search_parts = [self.name]
        if street:
            search_parts.append(street)
        if city:
            search_parts.append(city)
        if state:
            search_parts.append(state)
        full_place = ", ".join(search_parts)

        return {
            "pelias_structured": {
                "address": street or self.name,
                "locality": city or self.city or None,
                "region": state or self.state_abbr or None,
                "postalcode": zipcode or None,
                "country": country or "USA",
            },
            "full_place": full_place,
            "full_address": full_address or full_place,
        }

    def _acceptable_result(self, result: GeocodingResult | None) -> bool:
        if not result or not self._is_good_point_result(result):
            return False
        return is_decisive_pelias_candidate(self._extract_components(), result)

    def _select_from_candidates(
        self,
        candidates: list[GeocodingResult],
        query: str,
        openai_api_key: str | None,
    ) -> GeocodingResult | None:
        """Accept only a uniquely decisive Pelias candidate (LLM cannot invent certainty)."""
        components = self._extract_components()
        unique = select_uniquely_decisive_candidate(components, candidates)
        if unique is not None:
            return unique

        # Ambiguous decisive set → fail closed.
        decisive = [c for c in candidates if is_decisive_pelias_candidate(components, c)]
        if len(decisive) > 1:
            logger.info(
                "Place '%s' has %d decisive Pelias candidates with different identities; "
                "sending to needs_review",
                self.name,
                len(decisive),
            )
            return None

        # Optional LLM ranking only when zero decisive candidates so far; still must be decisive.
        if openai_api_key and len(candidates) > 1:
            picked = self._pick_pelias_candidate_with_llm(candidates, query, openai_api_key)
            if picked is not None and is_decisive_pelias_candidate(components, picked):
                return picked
        return None

    async def _geocode_pelias_decisive(
        self,
        *,
        pelias_api_key: str | None,
        openai_api_key: str | None,
    ) -> GeocodingResult | None:
        if not pelias_api_key:
            return None

        try:
            prep_data = self._prep()
        except Exception as exc:
            logger.error("Place prep failed for %s: %s", self.name, exc)
            return None

        full_address = str(prep_data.get("full_address") or prep_data.get("full_place") or "")
        pelias_bias = self._pelias_search_bias_kwargs()
        components = self._extract_components()

        # Structured candidates first when we have a street line or venue name.
        try:
            structured_params = {
                k: v for k, v in (prep_data.get("pelias_structured") or {}).items() if v
            }
            structured = await geocode_structured_candidates(
                **structured_params,
                api_key=pelias_api_key,
                size=5,
            )
            selected = self._select_from_candidates(structured, full_address, openai_api_key)
            if selected is not None:
                logger.info("Pelias structured decisive success for place %s", self.name)
                self.geocoding_result = selected
                return selected
            # Single-feature structured fallback when multi-candidate returned nothing decisive
            # but the top hit is decisive under evidence rules.
            if not structured:
                single = await pelias_structured(**structured_params, api_key=pelias_api_key)
                if single is not None and is_decisive_pelias_candidate(components, single):
                    self.geocoding_result = single
                    return single
        except Exception as exc:
            logger.warning("Pelias structured candidates failed for place %s: %s", self.name, exc)

        # Free-text search (venue + optional street).
        try:
            if openai_api_key:
                candidates = await geocode_search_candidates(
                    text=full_address,
                    api_key=pelias_api_key,
                    size=5,
                    **pelias_bias,
                )
                selected = self._select_from_candidates(candidates, full_address, openai_api_key)
                if selected is not None:
                    logger.info("Pelias search decisive success for place %s", self.name)
                    self.geocoding_result = selected
                    return selected
            else:
                result = await pelias_search(
                    text=full_address,
                    api_key=pelias_api_key,
                    **pelias_bias,
                )
                if result is not None and is_decisive_pelias_candidate(components, result):
                    self.geocoding_result = result
                    return result
        except Exception as exc:
            logger.warning("Pelias search failed for place %s: %s", self.name, exc)

        return None

    async def _geocode_pelias_venue(
        self,
        *,
        pelias_api_key: str | None,
        openai_api_key: str | None,
    ) -> GeocodingResult | None:
        """Name-only Pelias venue probe gated by uniquely decisive evidence."""
        if not pelias_api_key:
            return None
        # Prefer venue identity when extract already has no street line.
        if str(self.street_address or "").strip():
            return None

        parts = [self.name]
        if self.city:
            parts.append(self.city)
        if self.state_abbr:
            parts.append(self.state_abbr)
        text = ", ".join(parts)
        pelias_bias = self._pelias_search_bias_kwargs()
        try:
            candidates = await geocode_search_candidates(
                text=text,
                api_key=pelias_api_key,
                size=5,
                layers="venue",
                **pelias_bias,
            )
        except Exception as exc:
            logger.warning("Pelias venue probe failed for place %s: %s", self.name, exc)
            return None

        selected = self._select_from_candidates(candidates, text, openai_api_key)
        if selected is None:
            return None
        logger.info("Pelias venue decisive success for place %s", self.name)
        self.geocoding_result = selected
        self._address_source = self._address_source or "pelias_venue"
        return selected

    def _apply_discovered_address(self, address_data: Dict[str, str]) -> None:
        self._prep = lambda: self._update_prep_with_address(address_data)

    def _consider_address_search_response(
        self,
        *,
        provider: str,
        response: SearchResponse,
        openai_api_key: str,
    ) -> bool:
        if not response.success:
            self._record_address_search_attempt(provider, response, "error")
            return False
        if not response.results:
            self._record_address_search_attempt(provider, response, "empty")
            return False

        extracted = self._extract_and_parse_address(
            response.query,
            response,
            openai_api_key,
        )
        if extracted is None:
            self._record_address_search_attempt(
                provider,
                response,
                "no_usable_address",
            )
            return False

        self._record_address_search_attempt(provider, response, "complete_address")
        self._address_source = provider
        address_data = extracted.model_dump(exclude_none=True, exclude={"evidence_indexes"})
        self._apply_discovered_address(address_data)
        return True

    async def _try_web_search_address_discovery(
        self,
        *,
        brave_search_api_key: str | None,
        openai_api_key: str,
        is_fallback: bool,
    ) -> bool:
        """Run Web → Place → DDG discovery; stop at a complete address."""
        self._web_search_used = True
        if is_fallback:
            self._web_search_fallback_used = True

        query = self._generate_search_query(self._original_text or "", openai_api_key)
        location_parts = [part for part in (self.city, self.state_abbr, self.country) if part]
        location_hint = " ".join(location_parts).strip() or None

        if brave_search_api_key:
            try:
                web_response = brave_web_search(
                    brave_search_api_key,
                    q=query,
                    count=10,
                    country=self._country_code_for_search(),
                    search_lang="en",
                )
                if self._consider_address_search_response(
                    provider="brave_web",
                    response=web_response,
                    openai_api_key=openai_api_key,
                ):
                    return True
            except Exception as exc:
                logger.warning("Brave web search failed for place %s: %s", self.name, exc)
                self._record_address_search_attempt("brave_web", None, "error")

            try:
                place_response = brave_place_search(
                    brave_search_api_key,
                    q=query,
                    location=location_hint,
                    count=10,
                )
                if self._consider_address_search_response(
                    provider="brave_place",
                    response=place_response,
                    openai_api_key=openai_api_key,
                ):
                    return True
            except Exception as exc:
                logger.warning("Brave place search failed for place %s: %s", self.name, exc)
                self._record_address_search_attempt("brave_place", None, "error")

        try:
            ddg_response = search_web_duckduckgo(query, max_results=10, timeout=15.0)
            return self._consider_address_search_response(
                provider="duckduckgo",
                response=ddg_response,
                openai_api_key=openai_api_key,
            )
        except Exception as exc:
            logger.warning("DuckDuckGo search failed for place %s: %s", self.name, exc)
            self._record_address_search_attempt("duckduckgo", None, "error")
            return False

    ########## PUBLIC METHODS ##########

    async def geocode(
        self,
        pelias_api_key: Optional[str] = None,
        geocodio_api_key: Optional[str] = None,
        openai_api_key: Optional[str] = None,
        brave_search_api_key: Optional[str] = None,
        *,
        allow_web_search: bool = True,
    ) -> Optional[GeocodingResult]:
        """Geocode a named place as a POI.

        ``type: place`` always attempts resolution: explicit street from extract
        evidence, then web search when needed, then structured Pelias. Never
        early-return ``None`` solely because a name looks outdoor or was marked
        non-addressable by keyword heuristics.
        """
        logger.info("Starting place geocoding: %s", self.name)

        if not has_llm_auth(openai_api_key, self._geographic_reasoning_model_config_id()):
            logger.warning("No LLM auth provided; falling back to Address geocoding")
            return await super().geocode(pelias_api_key, geocodio_api_key, openai_api_key)

        openai_key = openai_api_key or ""

        if self._input_addressability is not None:
            addressability = "addressable" if self._input_addressability else "not addressable"
        else:
            addressability = self._check_if_addressable(openai_key)

        if addressability == "not addressable":
            # Still attempt Pelias/venue resolution for type=place destinations.
            logger.info(
                "Place '%s' marked not addressable; still attempting POI geocode",
                self.name,
            )
            return await super().geocode(pelias_api_key, geocodio_api_key, openai_api_key)

        if addressability == "has address":
            mock_results = SearchResponse(success=True, results=[], query=self.name)
            address_data = self._extract_and_parse_address(
                self.name,
                mock_results,
                openai_key,
            )
            if address_data:
                self._apply_discovered_address(address_data)

        elif addressability == "addressable":
            venue_hit = await self._geocode_pelias_venue(
                pelias_api_key=pelias_api_key,
                openai_api_key=openai_key,
            )
            if venue_hit is not None:
                return venue_hit
            if allow_web_search:
                await self._try_web_search_address_discovery(
                    brave_search_api_key=brave_search_api_key,
                    openai_api_key=openai_key,
                    is_fallback=False,
                )

        result = await self._geocode_pelias_decisive(
            pelias_api_key=pelias_api_key,
            openai_api_key=openai_api_key,
        )
        if result is not None:
            return result

        # Web search as fallback when direct Pelias was inconclusive (even if router
        # chose no_web_search upfront — address may already have been present).
        if not self._web_search_used and addressability == "addressable":
            logger.info(
                "Place '%s' Pelias inconclusive; trying web search fallback",
                self.name,
            )
            discovered = await self._try_web_search_address_discovery(
                brave_search_api_key=brave_search_api_key,
                openai_api_key=openai_key,
                is_fallback=True,
            )
            if discovered:
                result = await self._geocode_pelias_decisive(
                    pelias_api_key=pelias_api_key,
                    openai_api_key=openai_api_key,
                )
                if result is not None:
                    return result

        # Geocodio last resort: keep only when the label carries the extracted
        # house number and Geocodio reports a precise accuracy type.
        try:
            prep_data = self._prep()
        except Exception as exc:
            logger.error("Place prep failed for %s: %s", self.name, exc)
            return None
        full_address = str(prep_data.get("full_address") or prep_data.get("full_place") or "")

        from .address import _ADDRESS_NUMBER_RE

        def _label_has_requested_number(label: str) -> bool:
            requested = (self.street_address or "").strip()
            number_match = _ADDRESS_NUMBER_RE.search(requested) if requested else None
            if number_match is None:
                return False
            return number_match.group(1).lower() in {
                m.lower() for m in _ADDRESS_NUMBER_RE.findall(label)
            }

        if geocodio_api_key:
            try:
                result = geocodio_search(query=full_address, api_key=geocodio_api_key)
                conf = (
                    result.result.confidence
                    if result and result.result is not None
                    else None
                )
                if (
                    result
                    and self._is_good_point_result(result)
                    and result.result is not None
                    and _label_has_requested_number(str(result.result.processed_str or ""))
                    and is_acceptable_geocodio_accuracy(
                        conf if isinstance(conf, dict) else None
                    )
                ):
                    logger.info("Geocodio success for place %s", self.name)
                    self.geocoding_result = result
                    return result
            except Exception as exc:
                logger.warning("Geocodio failed for place %s: %s", self.name, exc)

        logger.warning("All geocoding services failed for place %s", self.name)
        return None

