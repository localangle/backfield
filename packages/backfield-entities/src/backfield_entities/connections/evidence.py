"""Typed creation evidence for auto-linked ``stylebook_connections`` rows."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from backfield_entities.connections.taxonomy import (
    AUTO_CONNECTION_EVIDENCE_SOURCE,
    AUTO_CONNECTION_PROMPT_VERSION,
)

_FORBIDDEN_EVIDENCE_KEYS = frozenset(
    {
        "raw_prompt",
        "raw_response",
        "prompt",
        "response",
        "full_prompt",
        "full_response",
        "model_response",
    }
)


class ConnectionCreationEvidence(BaseModel):
    """Normalized evidence stored on auto-created connection rows."""

    source: Literal["dboutput_auto_connections"] = AUTO_CONNECTION_EVIDENCE_SOURCE
    prompt_version: str = AUTO_CONNECTION_PROMPT_VERSION
    confidence: float = Field(ge=0.0, le=1.0)
    quote: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    from_entity_type: str
    from_entity_id: str
    from_display_name: str
    to_entity_type: str
    to_entity_id: str
    to_display_name: str
    article_id: int | None = None
    run_id: str | None = None
    processed_item_id: int | None = None
    adjudication_model: str | None = None
    adjudication_ai_model_config_id: int | None = None
    match_basis: str | None = None

    @field_validator("quote", "reason", "from_display_name", "to_display_name")
    @classmethod
    def _strip_non_empty(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must be non-empty after stripping")
        return stripped

    def to_storage_dict(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json", exclude_none=True)
        for key in _FORBIDDEN_EVIDENCE_KEYS:
            if key in payload:
                raise ValueError(f"evidence must not include {key!r}")
        return payload


def build_connection_creation_evidence(
    *,
    confidence: float,
    quote: str,
    reason: str,
    from_entity_type: str,
    from_entity_id: str,
    from_display_name: str,
    to_entity_type: str,
    to_entity_id: str,
    to_display_name: str,
    article_id: int | None = None,
    run_id: str | None = None,
    processed_item_id: int | None = None,
    adjudication_model: str | None = None,
    adjudication_ai_model_config_id: int | None = None,
    prompt_version: str = AUTO_CONNECTION_PROMPT_VERSION,
    match_basis: str | None = None,
) -> ConnectionCreationEvidence:
    return ConnectionCreationEvidence(
        prompt_version=prompt_version,
        confidence=confidence,
        quote=quote,
        reason=reason,
        from_entity_type=from_entity_type,
        from_entity_id=from_entity_id,
        from_display_name=from_display_name,
        to_entity_type=to_entity_type,
        to_entity_id=to_entity_id,
        to_display_name=to_display_name,
        article_id=article_id,
        run_id=run_id,
        processed_item_id=processed_item_id,
        adjudication_model=adjudication_model,
        adjudication_ai_model_config_id=adjudication_ai_model_config_id,
        match_basis=match_basis,
    )
