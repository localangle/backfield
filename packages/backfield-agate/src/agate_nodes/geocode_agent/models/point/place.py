import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional

from agate_utils.geocoding.geocoding_types import GeocodingResult
from agate_utils.llm import call_llm
from agate_utils.search import SearchResponse, brave_place_search, search_web_duckduckgo

from .address import Address

logger = logging.getLogger(__name__)

PLACE_LLM_MODEL = "gpt-5-nano"

########## PLACE MODEL ##########

class Place(Address):
    """Model for place-level locations (POIs, landmarks, venues, etc.)."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._input_addressability: Optional[bool] = None
        self._original_text: Optional[str] = None
        self._geocode_hints: Optional[str] = None
        self._failure_reason: Optional[str] = None

    def _geocode_hints_prompt_value(self) -> str:
        raw = (self._geocode_hints or "").strip()
        return raw if raw else "(none)"

    ########## PRIVATE/HELPER METHODS ##########

    def _prep(self) -> Dict[str, Any]:
        parts = [self.name]
        if self.city:
            parts.append(self.city)
        if self.state_abbr:
            parts.append(self.state_abbr)
        if self.country:
            parts.append(self.country)
        full_place = ", ".join(parts)

        return {
            "pelias_structured": {
                "address": self.name,
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
                model=PLACE_LLM_MODEL,
                openai_api_key=openai_api_key,
                force_json=False,
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
                model=PLACE_LLM_MODEL,
                openai_api_key=openai_api_key,
                force_json=False,
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

    def _search_for_address(
        self,
        brave_search_api_key: Optional[str],
        original_text: str,
        openai_api_key: str,
        *,
        allow_web_search: bool = True,
    ) -> Optional[SearchResponse]:
        if not allow_web_search:
            logger.info("Web search disabled for place '%s'; skipping Brave and DuckDuckGo", self.name)
            return None

        query = self._generate_search_query(original_text, openai_api_key)
        location_hint = None
        if self.city or self.state_abbr or self.country:
            parts = [p for p in (self.city, self.state_abbr, self.country) if p]
            location_hint = " ".join(parts).strip() or None

        if brave_search_api_key:
            try:
                response = brave_place_search(
                    brave_search_api_key,
                    q=query,
                    location=location_hint,
                    count=10,
                )
                if response.success and response.results:
                    return response
                logger.info("Brave place search returned no results for %s; trying DuckDuckGo", query[:50])
            except Exception as exc:
                logger.warning("Brave place search failed for %s: %s; trying DuckDuckGo", self.name, exc)

        try:
            response = search_web_duckduckgo(query, max_results=10, timeout=15.0)
            if response.success and response.results:
                return response
            logger.warning("DuckDuckGo returned no results for query: %s", query)
        except Exception as exc:
            logger.error("DuckDuckGo search failed for %s: %s", self.name, exc)
        return None

    def _extract_and_parse_address(
        self,
        search_query: str,
        search_results: SearchResponse,
        openai_api_key: str,
    ) -> Optional[Dict[str, str]]:
        try:
            prompt_path = Path(__file__).parent.parent.parent / "prompts" / "extract_best_address.md"
            template = prompt_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            logger.error("Extract best address prompt not found")
            return None

        try:
            formatted_results = [
                {"title": result.title, "url": result.url, "snippet": result.snippet}
                for result in search_results.results
            ]
            prompt = template.format(
                original_text=self._original_text or "",
                geocode_hints=self._geocode_hints_prompt_value(),
                query=search_query,
                search_results=json.dumps(formatted_results, indent=2),
            )
            result = call_llm(
                prompt=prompt,
                model=PLACE_LLM_MODEL,
                openai_api_key=openai_api_key,
                force_json=True,
            )
            address_data = json.loads(result)
            return address_data if address_data.get("address_found") else None
        except Exception as exc:
            logger.error("Error extracting address for %s: %s", self.name, exc)
            return None

    def _update_prep_with_address(self, address_data: Dict[str, str]) -> Dict[str, Any]:
        address_parts = [
            address_data.get("street"),
            address_data.get("city"),
            address_data.get("state"),
            address_data.get("zipcode"),
        ]
        full_address = ", ".join(part for part in address_parts if part)

        return {
            "pelias_structured": {
                "address": address_data.get("street"),
                "locality": address_data.get("city"),
                "region": address_data.get("state"),
                "postalcode": address_data.get("zipcode"),
                "country": address_data.get("country", "USA"),
            },
            "full_address": full_address,
        }

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
        logger.info("Starting place geocoding: %s", self.name)

        if not openai_api_key:
            logger.warning("No OpenAI API key provided; falling back to Address geocoding")
            return await super().geocode(pelias_api_key, geocodio_api_key, openai_api_key)

        if self._input_addressability is not None:
            addressability = "addressable" if self._input_addressability else "not addressable"
        else:
            addressability = self._check_if_addressable(openai_api_key)

        if addressability == "not addressable":
            logger.info("Place '%s' marked not addressable; skipping", self.name)
            return None

        if addressability == "has address":
            mock_results = SearchResponse(success=True, results=[], query=self.name)
            address_data = self._extract_and_parse_address(self.name, mock_results, openai_api_key)
            if address_data:
                self._prep = lambda: self._update_prep_with_address(address_data)

        elif addressability == "addressable":
            search_response = self._search_for_address(
                brave_search_api_key,
                self._original_text or "",
                openai_api_key,
                allow_web_search=allow_web_search,
            )
            if search_response:
                address_data = self._extract_and_parse_address(
                    search_response.query,
                    search_response,
                    openai_api_key,
                )
                if address_data:
                    self._prep = lambda: self._update_prep_with_address(address_data)

        return await super().geocode(pelias_api_key, geocodio_api_key, openai_api_key)

