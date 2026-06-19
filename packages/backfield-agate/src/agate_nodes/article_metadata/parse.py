"""Parse and validate Article Metadata LLM JSON responses."""

from __future__ import annotations

import json
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
    "subject_areas",
    "subject_list",
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
    "analysis",
    "classifications",
    "tags",
    "topics",
    "answers",
    "array",
)


def normalize_llm_json_payload(data: Any) -> Any:
    """Decode nested JSON strings returned by json_object-mode LLM calls."""
    if isinstance(data, str):
        stripped = data.strip()
        if not stripped:
            return data
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            return data
        return normalize_llm_json_payload(parsed)
    return data


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
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, list):
        for item in value:
            coerced = _coerce_category_value(item)
            if coerced:
                return coerced
    if isinstance(value, dict):
        for key in ("category", "label", "name", "value", "id", "slug", "subject", "topic"):
            inner = value.get(key)
            if isinstance(inner, str) and inner.strip():
                return inner.strip()
    return None


def _expand_slug_keyed_items(data: dict[str, Any]) -> list[Any] | None:
    if _coerce_category_value(
        _get_field(
            data,
            "category",
            "categories",
            "category_name",
            "category_label",
            "subject",
            "subject_area",
            "primary_subject",
            "topic",
            "need",
            "label",
            "name",
        )
    ):
        return None
    if any(key in data for key in _MULTI_VALUE_WRAPPER_KEYS):
        return None

    reserved = {
        "category",
        "categories",
        "rationale",
        "confidence",
        "subject",
        "need",
        "meta_type",
        "prompt_preset",
    }
    items: list[Any] = []
    for key, value in data.items():
        if not isinstance(key, str) or not key.strip():
            return None
        if key.lower() in reserved:
            return None
        if isinstance(value, str) and value.strip():
            items.append(
                {
                    "category": key.strip(),
                    "rationale": value.strip(),
                    "confidence": data.get("confidence"),
                }
            )
        elif isinstance(value, dict):
            item = dict(value)
            if _normalize_subject_item(item).get("category") is None:
                item["category"] = key.strip()
            items.append(item)
        else:
            return None

    return items or None


def _expand_index_keyed_items(data: dict[str, Any]) -> list[Any] | None:
    if not data:
        return None
    keys = [key for key in data if isinstance(key, str)]
    if not keys or not all(key.isdigit() for key in keys):
        return None
    items = [data[key] for key in sorted(keys, key=int)]
    if not all(isinstance(item, dict) for item in items):
        return None
    return items


def _inherit_wrapper_sibling_fields(
    wrapper: dict[str, Any],
    items: list[Any],
) -> list[Any]:
    sibling_rationale = _first_non_empty_str(
        wrapper,
        "rationale",
        "subject_rationale",
        "need_rationale",
        "reason",
        "explanation",
    )
    sibling_confidence = _get_field(
        wrapper,
        "confidence",
        "subject_confidence",
        "need_confidence",
        "score",
    )
    if sibling_rationale is None and sibling_confidence is None:
        return items

    enriched: list[Any] = []
    for item in items:
        if not isinstance(item, dict):
            enriched.append(item)
            continue
        merged = dict(item)
        normalized = _normalize_subject_item(merged)
        if normalized.get("rationale") is None and sibling_rationale is not None:
            merged["rationale"] = sibling_rationale
        if normalized.get("confidence") is None and sibling_confidence is not None:
            merged["confidence"] = sibling_confidence
        enriched.append(merged)
    return enriched


def _unwrap_wrapped_value(wrapper: dict[str, Any], key: str, wrapped: Any) -> list[Any] | None:
    if wrapped is None:
        return None

    if isinstance(wrapped, list):
        if wrapped and all(isinstance(item, str) for item in wrapped):
            string_items = [
                {"category": item.strip()}
                for item in wrapped
                if isinstance(item, str) and item.strip()
            ]
            if string_items:
                return _inherit_wrapper_sibling_fields(wrapper, string_items)
        out: list[Any] = []
        for item in wrapped:
            if item is None:
                continue
            out.extend(_unwrap_multi_value_items(item))
        if out:
            return _inherit_wrapper_sibling_fields(wrapper, out)
        return None

    if isinstance(wrapped, dict):
        slug_items = _expand_slug_keyed_items(wrapped)
        if slug_items:
            return _inherit_wrapper_sibling_fields(wrapper, slug_items)
        unwrapped = _unwrap_multi_value_items(wrapped)
        if unwrapped:
            return _inherit_wrapper_sibling_fields(wrapper, unwrapped)
        return None

    if isinstance(wrapped, str):
        stripped = wrapped.strip()
        if not stripped:
            return None
        parsed = normalize_llm_json_payload(stripped)
        if parsed is not stripped:
            unwrapped = _unwrap_multi_value_items(parsed)
            if unwrapped:
                return _inherit_wrapper_sibling_fields(wrapper, unwrapped)
        if key in _MULTI_VALUE_WRAPPER_KEYS:
            return _inherit_wrapper_sibling_fields(
                wrapper,
                [{"category": stripped}],
            )
        return None

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
            "category_label",
            "subject",
            "subject_area",
            "primary_subject",
            "topic",
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
        "reasoning",
        "explanation",
        "summary",
    )
    confidence = _get_field(raw, "confidence", "subject_confidence", "need_confidence", "score")
    return {
        "category": category,
        "rationale": rationale,
        "confidence": confidence,
    }


def _looks_like_metadata_item(raw: dict[str, Any]) -> bool:
    return _coerce_category_value(
        _get_field(
            raw,
            "category",
            "categories",
            "category_name",
            "category_label",
            "subject",
            "subject_area",
            "primary_subject",
            "topic",
            "need",
            "label",
            "name",
        )
    ) is not None


def _unwrap_multi_value_items(data: Any) -> list[Any]:
    data = normalize_llm_json_payload(data)
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

    if _looks_like_metadata_item(data):
        return [data]

    for key in _MULTI_VALUE_WRAPPER_KEYS:
        if key not in data:
            continue
        unwrapped = _unwrap_wrapped_value(data, key, data[key])
        if unwrapped:
            return unwrapped

    slug_items = _expand_slug_keyed_items(data)
    if slug_items:
        return slug_items

    index_items = _expand_index_keyed_items(data)
    if index_items:
        out: list[Any] = []
        for item in index_items:
            out.extend(_unwrap_multi_value_items(item))
        if out:
            return out

    return [data]


def _coerce_single_value_response(data: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_subject_item(data)
    category = normalized.get("category")
    rationale = normalized.get("rationale")
    confidence = normalized.get("confidence")
    out: dict[str, Any] = {}
    if category is not None:
        out["category"] = category
    if rationale is not None:
        out["rationale"] = rationale
    if confidence is not None:
        out["confidence"] = confidence
    return out


def parse_article_metadata_response(
    data: Any,
    *,
    allowed_categories: list[str],
) -> ArticleMetadataLLMResponse:
    if not isinstance(data, dict):
        raise ValueError("LLM response must be a JSON object")
    data = _coerce_single_value_response(data)
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
            preview = raw_item if isinstance(raw_item, dict) else repr(raw_item)
            raise ValueError(f"Invalid subject entry: {exc}; raw={preview!r}") from exc
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
