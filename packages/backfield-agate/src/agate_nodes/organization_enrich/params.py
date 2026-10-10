"""Organization Enrich node settings."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

WIKIDATA_SOURCE = "wikidata"
WIKIPEDIA_SOURCE = "wikipedia"
_KNOWN_SOURCES = {WIKIDATA_SOURCE, WIKIPEDIA_SOURCE}
DEFAULT_CONFIDENCE_CUTOFF = 0.8


class OrganizationEnrichParams(BaseModel):
    model: str = ""
    ai_model_config_id: str | None = Field(default=None, alias="aiModelConfigId")
    sources: list[str] = Field(default_factory=lambda: [WIKIDATA_SOURCE, WIKIPEDIA_SOURCE])
    confidence_cutoff: float = DEFAULT_CONFIDENCE_CUTOFF

    model_config = {"populate_by_name": True}

    @field_validator("sources", mode="before")
    @classmethod
    def _keep_known_sources(cls, value: object) -> list[str]:
        if not isinstance(value, list):
            return [WIKIDATA_SOURCE, WIKIPEDIA_SOURCE]
        kept: list[str] = []
        for item in value:
            if isinstance(item, str) and item in _KNOWN_SOURCES and item not in kept:
                kept.append(item)
        return kept

    @field_validator("confidence_cutoff", mode="before")
    @classmethod
    def _cutoff_or_default(cls, value: object) -> float:
        try:
            number = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return DEFAULT_CONFIDENCE_CUTOFF
        if number < 0 or number > 1:
            return DEFAULT_CONFIDENCE_CUTOFF
        return number

    def selected_sources(self) -> set[str]:
        return set(self.sources)
