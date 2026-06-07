"""Shared types for automatic connection inference."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field


@dataclass(frozen=True)
class LinkedEntitySnapshot:
    entity_type: str
    substrate_id: int
    canonical_id: str
    label: str
    location_type: str | None = None
    affiliation: str | None = None
    organization_type: str | None = None
    snippets: tuple[str, ...] = ()


class AutoConnectionEdgeProposal(BaseModel):
    from_entity_id: str
    to_entity_id: str
    nature: str
    confidence: float = Field(ge=0.0, le=1.0)
    quote: str = Field(min_length=1)
    reason: str = ""


class AutoConnectionFamilyResponse(BaseModel):
    edges: list[AutoConnectionEdgeProposal] = Field(default_factory=list)
