"""Shared types for automatic connection inference."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field, field_validator


@dataclass(frozen=True)
class LinkedEntitySnapshot:
    entity_type: str
    substrate_id: int
    canonical_id: str
    label: str
    location_type: str | None = None
    affiliation: str | None = None
    person_type: str | None = None
    organization_type: str | None = None
    snippets: tuple[str, ...] = ()


class AutoConnectionEdgeProposal(BaseModel):
    from_entity_id: str
    to_entity_id: str
    description: str = Field(min_length=1)
    nature: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    quote: str = Field(min_length=1)
    reason: str = ""
    match_basis: str | None = None
    prompt_version: str | None = None

    @field_validator("description", "quote")
    @classmethod
    def _strip_non_empty(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must be non-empty after stripping")
        return stripped

    @field_validator("nature")
    @classmethod
    def _normalize_nature(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip().lower()
        return stripped or None


class AutoConnectionFamilyResponse(BaseModel):
    edges: list[AutoConnectionEdgeProposal] = Field(default_factory=list)
