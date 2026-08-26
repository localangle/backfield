"""Typed creation evidence for auto-linked ``stylebook_connections`` rows."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from backfield_db import StylebookConnectionEvidence
from pydantic import BaseModel, Field, field_validator

from backfield_entities.connections.taxonomy import (
    AUTO_CONNECTION_EVIDENCE_SOURCE,
    AUTO_CONNECTION_PROMPT_VERSION,
)
from backfield_entities.connections.types import AssertedConnectionCurrentness

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


def reference_time_is_newer(
    candidate: datetime,
    current: datetime | None,
) -> bool:
    """Compare DB timestamps consistently across timezone-aware and SQLite values."""
    if current is None:
        return True
    candidate_utc = (
        candidate.replace(tzinfo=UTC)
        if candidate.tzinfo is None
        else candidate.astimezone(UTC)
    )
    current_utc = (
        current.replace(tzinfo=UTC) if current.tzinfo is None else current.astimezone(UTC)
    )
    return candidate_utc > current_utc


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
    asserted_currentness: AssertedConnectionCurrentness = "unspecified"

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
    asserted_currentness: AssertedConnectionCurrentness = "unspecified",
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
        asserted_currentness=asserted_currentness,
    )


def evidence_row_from_creation(
    *,
    connection_id: int,
    evidence: ConnectionCreationEvidence,
    description: str | None,
    observed_at: datetime | None = None,
) -> StylebookConnectionEvidence:
    """Map typed creation evidence into a ``stylebook_connection_evidence`` row."""
    payload: dict[str, Any] = {}
    for key, value in (
        ("from_entity_type", evidence.from_entity_type),
        ("from_entity_id", evidence.from_entity_id),
        ("from_display_name", evidence.from_display_name),
        ("to_entity_type", evidence.to_entity_type),
        ("to_entity_id", evidence.to_entity_id),
        ("to_display_name", evidence.to_display_name),
        ("adjudication_model", evidence.adjudication_model),
        ("adjudication_ai_model_config_id", evidence.adjudication_ai_model_config_id),
    ):
        if value is not None:
            payload[key] = value

    return StylebookConnectionEvidence(
        connection_id=int(connection_id),
        article_id=evidence.article_id,
        description=(description or "").strip() or None,
        quote=evidence.quote,
        reason=evidence.reason,
        confidence=float(evidence.confidence),
        source=evidence.source,
        prompt_version=evidence.prompt_version,
        run_id=evidence.run_id,
        processed_item_id=evidence.processed_item_id,
        match_basis=evidence.match_basis,
        asserted_currentness=evidence.asserted_currentness,
        observed_at=observed_at,
        payload_json=payload or None,
    )
