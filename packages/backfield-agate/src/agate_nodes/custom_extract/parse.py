"""Parse and validate Custom Extract LLM JSON responses against the declared schema."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from agate_nodes.custom_extract.schema import CustomRecordSchema, build_record_fields_model


class CustomRecordMention(BaseModel):
    """One evidence snippet grounding a record (passage only — no attributed quotes)."""

    text: str
    quote: bool = False

    @field_validator("text")
    @classmethod
    def _non_empty_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("mention text must be a non-empty string")
        return cleaned

    @model_validator(mode="after")
    def _mentions_only(self) -> CustomRecordMention:
        self.quote = False
        return self


class ParsedCustomRecord(BaseModel):
    key: str
    fields: dict[str, Any]
    mentions: list[CustomRecordMention]
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class CustomExtractParseResult(BaseModel):
    records: list[ParsedCustomRecord]
    dropped_ungrounded: int


def normalize_llm_json_payload(data: Any) -> Any:
    """Decode nested JSON strings returned by json_object-mode LLM calls."""
    if isinstance(data, str):
        stripped = data.strip()
        if stripped.startswith(("{", "[")):
            try:
                return normalize_llm_json_payload(json.loads(stripped))
            except json.JSONDecodeError:
                return data
        return data
    if isinstance(data, dict):
        return {key: normalize_llm_json_payload(value) for key, value in data.items()}
    if isinstance(data, list):
        return [normalize_llm_json_payload(item) for item in data]
    return data


def _record_key(record_type: str, fields: dict[str, Any], used_keys: set[str]) -> str:
    """Stable payload-based identity for overlay edits (deterministic across re-parse)."""
    digest = hashlib.sha1(
        json.dumps({"record_type": record_type, "fields": fields}, sort_keys=True).encode("utf-8")
    ).hexdigest()[:12]
    key = digest
    suffix = 1
    while key in used_keys:
        suffix += 1
        key = f"{digest}-{suffix}"
    used_keys.add(key)
    return key


def _coerce_mentions(raw: Any) -> list[CustomRecordMention]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError(f"'mentions' must be an array (got {type(raw).__name__}).")
    mentions: list[CustomRecordMention] = []
    for entry in raw:
        if isinstance(entry, str):
            entry = {"text": entry}
        if not isinstance(entry, dict):
            continue
        try:
            mentions.append(CustomRecordMention.model_validate(entry))
        except ValidationError:
            continue
    return mentions


def _coerce_confidence(raw: Any) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        value = float(raw)
    elif isinstance(raw, str) and raw.strip():
        try:
            value = float(raw.strip())
        except ValueError:
            return None
    else:
        return None
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"confidence must be between 0.0 and 1.0 (got {value}).")
    return value


def parse_custom_extract_response(
    response_data: Any,
    *,
    record_schema: CustomRecordSchema,
) -> CustomExtractParseResult:
    """Validate the strict ``{"records": [...]}`` contract against the declared schema.

    Records the model cannot ground in article text (no valid mentions) are dropped
    and counted; rows that violate the field schema fail the node with a clear error.
    """
    data = normalize_llm_json_payload(response_data)

    if isinstance(data, list):
        raw_records: Any = data
    elif isinstance(data, dict) and "records" in data:
        raw_records = data["records"] if data["records"] is not None else []
    else:
        raise ValueError(
            'Expected a JSON object with a "records" array in the model response. '
            f"Got keys: {sorted(data.keys()) if isinstance(data, dict) else type(data).__name__}"
        )
    if not isinstance(raw_records, list):
        raise ValueError("'records' must be an array.")

    fields_model = build_record_fields_model(record_schema.fields)
    declared_names = {spec.name for spec in record_schema.fields}

    parsed: list[ParsedCustomRecord] = []
    dropped_ungrounded = 0
    used_keys: set[str] = set()

    for index, raw_record in enumerate(raw_records):
        if not isinstance(raw_record, dict):
            raise ValueError(f"Record {index + 1} must be an object (got {raw_record!r}).")

        raw_fields = raw_record.get("fields")
        if raw_fields is None:
            # Tolerate flat records where field values sit at the top level.
            raw_fields = {
                key: value for key, value in raw_record.items() if key in declared_names
            }
        if not isinstance(raw_fields, dict):
            raise ValueError(f"Record {index + 1} 'fields' must be an object.")

        try:
            validated_fields = fields_model.model_validate(raw_fields)
        except ValidationError as exc:
            raise ValueError(
                f"Record {index + 1} does not match the declared fields: {exc}"
            ) from exc

        mentions = _coerce_mentions(raw_record.get("mentions"))
        if not mentions:
            dropped_ungrounded += 1
            continue

        fields_payload = validated_fields.model_dump(include=declared_names)
        parsed.append(
            ParsedCustomRecord(
                key=_record_key(record_schema.record_type, fields_payload, used_keys),
                fields=fields_payload,
                mentions=mentions,
                confidence=_coerce_confidence(raw_record.get("confidence")),
            )
        )

    return CustomExtractParseResult(records=parsed, dropped_ungrounded=dropped_ungrounded)
