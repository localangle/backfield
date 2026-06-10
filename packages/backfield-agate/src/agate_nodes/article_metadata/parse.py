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
    "article_metadata",
    "metadata",
    "response",
    "result",
    "data",
    "output",
)


def _get_field(raw: dict[str, Any], *keys: str) -> Any:
    lower_map = {str(key).lower(): key for key in raw if isinstance(key, str)}
    for key in keys:
        if key in raw:
            return raw[key]
        alt = lower_map.get(key.lower())
        if alt is not None:
            return raw[alt]
    return None


def _coerce_category_value(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, list):
        for item in value:
            coerced = _coerce_category_value(item)
            if coerced:
                return coerced
    if isinstance(value, dict):
        for key in ("category", "label", "name", "value", "id", "slug", "subject"):
            inner = value.get(key)
            if isinstance(inner, str) and inner.strip():
                return inner.strip()
    return None


def _first_non_empty_str(raw: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = _get_field(raw, key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _normalize_subject_item(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("each subject entry must be a JSON object")
    category = _coerce_category_value(
        _get_field(
            raw,
            "category",
            "categories",
            "category_name",
            "subject",
            "need",
            "label",
            "name",
        )
    )
    rationale = _first_non_empty_str(
        raw,
        "rationale",
        "subject_rationale",
        "need_rationale",
        "reason",
        "explanation",
    )
    confidence = _get_field(raw, "confidence", "subject_confidence", "need_confidence", "score")
    return {
        "category": category,
        "rationale": rationale,
        "confidence": confidence,
    }


def _looks_like_metadata_item(raw: dict[str, Any]) -> bool:
    normalized = _normalize_subject_item(raw)
    return normalized.get("category") is not None


def _unwrap_multi_value_items(data: Any) -> list[Any]:
    if data is None:
        return []

    if isinstance(data, list):
        if not data:
            return []
        cleaned = [item for item in data if item is not None]
        if cleaned and all(
            isinstance(item, dict) and _looks_like_metadata_item(item) for item in cleaned
        ):
            return cleaned
        out: list[Any] = []
        for item in cleaned:
            out.extend(_unwrap_multi_value_items(item))
        return out

    if not isinstance(data, dict):
        raise ValueError("LLM response must be a JSON array of subject objects")

    for key in _MULTI_VALUE_WRAPPER_KEYS:
        if key not in data:
            continue
        wrapped = data[key]
        if wrapped is None:
            continue
        if isinstance(wrapped, list):
            out: list[Any] = []
            for item in wrapped:
                if item is None:
                    continue
                out.extend(_unwrap_multi_value_items(item))
            if out:
                return out
        elif isinstance(wrapped, dict):
            unwrapped = _unwrap_multi_value_items(wrapped)
            if unwrapped:
                return unwrapped

    if _looks_like_metadata_item(data):
        return [data]

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
        if all(normalized.get(key) is None for key in ("category", "rationale", "confidence")):
            if isinstance(raw_item, dict) and any(
                key in raw_item for key in _MULTI_VALUE_WRAPPER_KEYS
            ):
                raise ValueError(
                    "LLM returned a wrapper object instead of subject entries; "
                    f"keys={sorted(raw_item.keys())!r}"
                )
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
