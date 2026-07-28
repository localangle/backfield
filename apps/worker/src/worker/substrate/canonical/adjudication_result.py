"""Strict structured output for person/organization/location canonical adjudication."""

from __future__ import annotations

import math
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


class CanonicalAdjudicationDecision(StrEnum):
    LINK_EXISTING = "link_existing"
    NO_MATCH = "no_match"
    UNCERTAIN = "uncertain"


class CanonicalAdjudicationResult(BaseModel):
    """Validated LLM adjudication payload used at the resolve boundary."""

    # Keep enum string coercion; reject non-numeric confidence via validators below.
    model_config = ConfigDict(extra="forbid")

    decision: CanonicalAdjudicationDecision
    canonical_id: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    same_identity: bool
    conflicting_identity_evidence: bool
    rationale: str = ""

    @field_validator("confidence", mode="before")
    @classmethod
    def _reject_non_finite_confidence(cls, value: Any) -> Any:
        if isinstance(value, bool):
            raise ValueError("confidence must be a number, not a boolean")
        if isinstance(value, str):
            raise ValueError("confidence must be a number, not a string")
        if isinstance(value, (int, float)):
            if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
                raise ValueError("confidence must be a finite number")
            return float(value)
        raise ValueError("confidence must be a number")

    @field_validator("canonical_id", mode="before")
    @classmethod
    def _normalize_canonical_id(cls, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, bool):
            raise ValueError("canonical_id must be a UUID string or null")
        if not isinstance(value, str):
            raise ValueError("canonical_id must be a UUID string or null")
        cleaned = value.strip()
        return cleaned or None

    @field_validator("same_identity", "conflicting_identity_evidence", mode="before")
    @classmethod
    def _require_bool(cls, value: Any) -> Any:
        if not isinstance(value, bool):
            raise ValueError("must be a boolean")
        return value

    @model_validator(mode="after")
    def _decision_consistency(self) -> CanonicalAdjudicationResult:
        if self.decision == CanonicalAdjudicationDecision.LINK_EXISTING:
            if self.canonical_id is None:
                raise ValueError("link_existing requires canonical_id")
            if not self.same_identity:
                raise ValueError("link_existing requires same_identity=true")
            if self.conflicting_identity_evidence:
                raise ValueError("link_existing forbids conflicting_identity_evidence=true")
        else:
            if self.canonical_id is not None:
                raise ValueError(f"{self.decision.value} requires canonical_id=null")
        return self


ADJUDICATION_JSON_CONTRACT = (
    "Return JSON only with these keys:\n"
    "- decision: exactly one of \"link_existing\", \"no_match\", \"uncertain\"\n"
    "- canonical_id: UUID string matching one candidate id when decision is "
    "\"link_existing\", otherwise null\n"
    "- confidence: number from 0.0 to 1.0 (not a string)\n"
    "- same_identity: boolean; true only when the chosen candidate is the same "
    "real-world entity as the substrate row\n"
    "- conflicting_identity_evidence: boolean; true when article/name/type evidence "
    "indicates a different entity or namesake\n"
    "- rationale: short audit string\n"
    "If the entities are different people/places/organizations or namesakes, you MUST "
    "set decision=\"no_match\", canonical_id=null, same_identity=false, and "
    "conflicting_identity_evidence=true (or uncertain when evidence is insufficient)."
)

ADJUDICATION_CORRECTIVE_SUFFIX = (
    "\n\nYour previous JSON was invalid or inconsistent with the contract. "
    "Reply again with ONLY valid JSON matching the contract exactly. "
    "If you concluded the candidate is a different entity/namesake, decision must be "
    "\"no_match\" with canonical_id null."
)


def parse_canonical_adjudication_result(
    data: dict[str, Any] | None,
    *,
    candidate_ids: set[str],
) -> CanonicalAdjudicationResult | None:
    """Parse and validate adjudication JSON; return None when invalid."""
    if not isinstance(data, dict):
        return None
    try:
        parsed = CanonicalAdjudicationResult.model_validate(data)
    except ValidationError:
        return None
    if (
        parsed.decision == CanonicalAdjudicationDecision.LINK_EXISTING
        and parsed.canonical_id is not None
        and parsed.canonical_id not in candidate_ids
    ):
        return None
    return parsed


def adjudication_allows_link(
    result: CanonicalAdjudicationResult,
    *,
    min_confidence: float,
) -> bool:
    """True when structured fields authorize an auto-link attempt (gate still applies)."""
    return (
        result.decision == CanonicalAdjudicationDecision.LINK_EXISTING
        and result.canonical_id is not None
        and result.same_identity
        and not result.conflicting_identity_evidence
        and result.confidence >= min_confidence
    )


def adjudication_audit_fields(
    result: CanonicalAdjudicationResult,
    *,
    linked: bool = False,
) -> dict[str, Any]:
    """Fields to merge into ``canonical_adjudication`` review reasons."""
    return {
        "decision": result.decision.value,
        "canonical_id": result.canonical_id,
        "confidence": result.confidence,
        "same_identity": result.same_identity,
        "conflicting_identity_evidence": result.conflicting_identity_evidence,
        "rationale": result.rationale or None,
        "outcome": "link_existing" if linked else "no_high_confidence_link",
    }


OutcomeLiteral = Literal["link_existing", "no_high_confidence_link"]
