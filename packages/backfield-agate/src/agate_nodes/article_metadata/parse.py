"""Parse and validate Article Metadata LLM JSON responses."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, field_validator


class ArticleMetadataLLMResponse(BaseModel):
    category: str
    rationale: str
    confidence: float

    @field_validator("category", "rationale")
    @classmethod
    def _non_empty_str(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must be a non-empty string")
        return cleaned

    @field_validator("confidence")
    @classmethod
    def _confidence_in_unit_interval(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")
        return float(value)


def parse_article_metadata_response(
    data: Any,
    *,
    allowed_categories: list[str],
) -> ArticleMetadataLLMResponse:
    if not isinstance(data, dict):
        raise ValueError("LLM response must be a JSON object")
    try:
        parsed = ArticleMetadataLLMResponse.model_validate(data)
    except Exception as exc:
        raise ValueError(f"Invalid article metadata response: {exc}") from exc

    allowed = {label.strip() for label in allowed_categories if label.strip()}
    if parsed.category not in allowed:
        options = ", ".join(sorted(allowed))
        raise ValueError(
            f"Category {parsed.category!r} is not allowed. Choose one of: {options}"
        )
    return parsed
