"""Shared types for automatic connection inference."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field, field_validator

AssertedConnectionCurrentness = Literal["current", "former", "unspecified"]


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


@dataclass(frozen=True)
class PairEvidencePacket:
    """Evidence and lower-trust hints for one candidate canonical pair."""

    snippets: tuple[str, ...]
    source: str
    score: int
    match_basis: str | None = None
    hints: tuple[str, ...] = ()


@dataclass(frozen=True)
class AutoConnectionCandidatePair:
    """One endpoint pair submitted to connection classification."""

    candidate_id: str
    from_entity: LinkedEntitySnapshot
    to_entity: LinkedEntitySnapshot
    evidence: PairEvidencePacket

    @property
    def from_entity_type(self) -> str:
        return self.from_entity.entity_type

    @property
    def to_entity_type(self) -> str:
        return self.to_entity.entity_type


class AutoConnectionEdgeProposal(BaseModel):
    candidate_id: str | None = None
    from_entity_id: str
    to_entity_id: str
    description: str = Field(min_length=1)
    nature: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    quote: str = Field(min_length=1)
    reason: str = ""
    asserted_currentness: AssertedConnectionCurrentness = "unspecified"
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


class AutoConnectionCandidateDecision(BaseModel):
    """Model judgment for one candidate pair before edge validation."""

    candidate_id: str = Field(min_length=1)
    link: bool
    from_entity_id: str | None = None
    to_entity_id: str | None = None
    description: str = ""
    nature: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    quote: str = ""
    reason: str = Field(min_length=1)
    asserted_currentness: AssertedConnectionCurrentness

    @field_validator("candidate_id", "reason")
    @classmethod
    def _strip_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must be non-empty after stripping")
        return stripped

    @field_validator("nature")
    @classmethod
    def _normalize_decision_nature(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip().lower()
        return stripped or None

