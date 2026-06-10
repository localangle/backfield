"""Parse and validate Article Metadata LLM JSON responses."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, field_validator

from agate_nodes.article_metadata.presets import MAX_MULTI_VALUE_COUNT


class ArticleMetadataLLMResponse(BaseModel):
    category: str
    rationale: str
    confidence: float

    @field_validator("category", "rationale", mode="before")
    @classmethod
    def _coerce_optional_str(cls, value: Any) -> Any:
        if value is None:
            return value
        if isinstance(value, str):
            return value
        return str(value)

    @field_validator("confidence", mode="before")
    @classmethod
    def _coerce_confidence(cls, value: Any) -> Any:
        if value is None:
            return value
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str) and value.strip():
            return float(value.strip())
        return value

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


_MULTI_VALUE_WRAPPER_KEYS = (
    "subjects",
    "needs",
    "items",
    "results",
    "categories",
    "information_needs",
)


def _first_non_empty_str(raw: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _normalize_subject_item(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("each subject entry must be a JSON object")
    category = _first_non_empty_str(
        raw,
        "category",
        "subject",
        "need",
        "label",
        "name",
    )
    rationale = _first_non_empty_str(
        raw,
        "rationale",
        "subject_rationale",
        "need_rationale",
        "reason",
        "explanation",
    )
    confidence = raw.get("confidence")
    if confidence is None:
        confidence = raw.get("subject_confidence")
    if confidence is None:
        confidence = raw.get("need_confidence")
    if confidence is None:
        confidence = raw.get("score")
    return {
        "category": category,
        "rationale": rationale,
        "confidence": confidence,
    }


def _looks_like_metadata_item(raw: dict[str, Any]) -> bool:
    normalized = _normalize_subject_item(raw)
    return any(normalized.get(key) is not None for key in ("category", "rationale", "confidence"))


def _unwrap_multi_value_items(data: Any) -> list[Any]:
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        raise ValueError("LLM response must be a JSON array of subject objects")

    if _looks_like_metadata_item(data):
        return [data]

    for key in _MULTI_VALUE_WRAPPER_KEYS:
        wrapped = data.get(key)
        if isinstance(wrapped, list):
            return wrapped
        if isinstance(wrapped, dict):
            return [wrapped]

    return [data]


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


def parse_multi_value_metadata_response(
    data: Any,
    *,
    allowed_categories: list[str],
) -> list[ArticleMetadataLLMResponse]:
    items_raw = _unwrap_multi_value_items(data)

    if not items_raw:
        raise ValueError("At least one item is required")
    if len(items_raw) > MAX_MULTI_VALUE_COUNT:
        raise ValueError(f"At most {MAX_MULTI_VALUE_COUNT} items are allowed")

    allowed = {label.strip() for label in allowed_categories if label.strip()}
    parsed_items: list[ArticleMetadataLLMResponse] = []
    seen_categories: set[str] = set()

    for raw_item in items_raw:
        normalized = _normalize_subject_item(raw_item)
        try:
            parsed = ArticleMetadataLLMResponse.model_validate(normalized)
        except Exception as exc:
            raise ValueError(f"Invalid subject entry: {exc}") from exc
        if parsed.category not in allowed:
            options = ", ".join(sorted(allowed))
            raise ValueError(
                f"Category {parsed.category!r} is not allowed. Choose one of: {options}"
            )
        if parsed.category in seen_categories:
            raise ValueError(f"Duplicate subject category {parsed.category!r}")
        seen_categories.add(parsed.category)
        parsed_items.append(parsed)

    parsed_items.sort(key=lambda item: item.confidence, reverse=True)
    return parsed_items


def parse_subject_metadata_response(
    data: Any,
    *,
    allowed_categories: list[str],
) -> list[ArticleMetadataLLMResponse]:
    """Backward-compatible alias for multi-value subject parsing."""
    return parse_multi_value_metadata_response(data, allowed_categories=allowed_categories)
