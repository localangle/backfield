"""Country-level Pelias boundary lookup (ISO identity remains the accept gate)."""

from __future__ import annotations

import logging
from typing import Any, Optional

from agate_utils.geocoding.geocoding_types import GeocodingResult
from agate_utils.geocoding.pelias import (
    geocode_search_candidates as pelias_search_candidates,
)
from agate_utils.geocoding.pelias import (
    geocode_structured_candidates as pelias_structured_candidates,
)

from .area import Area

logger = logging.getLogger(__name__)


class Country(Area):
    """Model for country-level locations.

    PlaceExtract / GeocodeAgent already require a valid ISO alpha-2 identity.
    This model only asks Pelias for a country-layer bbox polygon that matches
    that code. No Geocodio/Nominatim/LLM fallback — miss → identity-only row.
    """

    def _expected_country_code(self) -> str:
        return str(self.country or "").strip().upper()

    def _prep(self) -> dict[str, Any]:
        code = self._expected_country_code()
        return {
            "pelias_structured": {
                "country": code or self.name,
                "size": 5,
                "layers": "country",
            },
            "pelias_search": {
                "text": self.name,
                "size": 5,
                "layers": "country",
                **({"boundary.country": code.lower()} if len(code) == 2 else {}),
            },
        }

    def _candidate_country_code(self, result: GeocodingResult) -> str:
        if not result or not result.result:
            return ""
        conf = result.result.confidence or {}
        return str(conf.get("pelias_country_code") or "").strip().upper()

    def _score_area_candidate(self, result: GeocodingResult, *, expected_layer: str) -> int:
        """Require country layer, matching ISO code, and a bbox polygon."""
        if not result or not result.result:
            return -10_000
        layer = self._candidate_layer(result)
        if expected_layer and layer and layer != expected_layer:
            return -10_000
        if layer and layer != "country":
            return -10_000
        expected = self._expected_country_code()
        got = self._candidate_country_code(result)
        if expected and got and got != expected:
            return -10_000
        if expected and not got:
            return -10_000
        if not self._candidate_has_bbox(result):
            return -10_000
        return super()._score_area_candidate(result, expected_layer=expected_layer or "country")

    async def geocode(
        self,
        pelias_api_key: Optional[str] = None,
        geocodio_api_key: Optional[str] = None,
        openai_api_key: Optional[str] = None,
    ) -> Optional[GeocodingResult]:
        """Pelias country-layer bbox only; never invent geometry via other providers."""
        del geocodio_api_key, openai_api_key  # unused — countries stay Pelias-only
        logger.info("Geocoding country boundary: %s (%s)", self.name, self._expected_country_code())
        if not pelias_api_key:
            logger.info("No Pelias key for country '%s'; skipping boundary lookup", self.name)
            return None

        try:
            prep_data = self._prep()
        except Exception as exc:
            logger.error("Country prep failed for %s: %s", self.name, exc)
            return None

        # Structured first (country code is the strongest signal).
        try:
            structured_params = dict(prep_data.get("pelias_structured") or {})
            candidates = await pelias_structured_candidates(
                api_key=pelias_api_key,
                **structured_params,
            )
            chosen = self._choose_best_area_candidate(candidates, expected_layer="country")
            if chosen is not None:
                logger.info(
                    "Pelias structured country bbox for %s (wof=%s)",
                    self.name,
                    self._is_wof_candidate(chosen),
                )
                self.geocoding_result = chosen
                return chosen
        except Exception as exc:
            logger.warning("Pelias structured country lookup failed for %s: %s", self.name, exc)

        # Free-text search constrained to country layer.
        try:
            search_params = dict(prep_data.get("pelias_search") or {})
            text = str(search_params.pop("text") or "").strip()
            if text:
                candidates = await pelias_search_candidates(
                    text=text,
                    api_key=pelias_api_key,
                    **search_params,
                )
                chosen = self._choose_best_area_candidate(candidates, expected_layer="country")
                if chosen is not None:
                    logger.info(
                        "Pelias search country bbox for %s (wof=%s)",
                        self.name,
                        self._is_wof_candidate(chosen),
                    )
                    self.geocoding_result = chosen
                    return chosen
        except Exception as exc:
            logger.warning("Pelias search country lookup failed for %s: %s", self.name, exc)

        logger.info("No Pelias country bbox for %s; identity-only fallback", self.name)
        return None
