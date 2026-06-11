"""User-declared record schema for Custom Extract (record type, fields, dynamic model)."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, create_model, field_validator, model_validator

_SLUG_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")

CustomFieldType = Literal["string", "number", "boolean", "date", "string_list"]

ALLOWED_FIELD_TYPES: tuple[str, ...] = ("string", "number", "boolean", "date", "string_list")

# Record-payload keys owned by the node contract, never by a declared field.
RESERVED_FIELD_NAMES: frozenset[str] = frozenset({"fields", "mentions", "confidence", "key"})

MAX_FIELD_COUNT = 20


def normalize_slug(raw: str | None, *, kind: str) -> str:
    """Validate a user-defined slug (record type or field name)."""
    value = (raw or "").strip().lower().replace("-", "_").replace(" ", "_")
    if not value:
        raise ValueError(f"{kind} is required (for example ingredients).")
    if not _SLUG_PATTERN.match(value):
        raise ValueError(
            f"{kind} must start with a letter and use only lowercase letters, "
            "numbers, and underscores."
        )
    return value


class CustomFieldSpec(BaseModel):
    """One declared column in the record schema."""

    name: str
    label: str = ""
    type: CustomFieldType = "string"
    description: str = ""

    @field_validator("name", mode="before")
    @classmethod
    def _normalize_name(cls, value: Any) -> str:
        name = normalize_slug(value if isinstance(value, str) else None, kind="Field name")
        if name in RESERVED_FIELD_NAMES:
            raise ValueError(f"Field name {name!r} is reserved; choose a different name.")
        return name

    @model_validator(mode="after")
    def _default_label(self) -> CustomFieldSpec:
        if not self.label.strip():
            self.label = self.name.replace("_", " ").capitalize()
        return self


class CustomRecordSchema(BaseModel):
    """Validated record type + field list declared on the node."""

    record_type: str
    label: str = ""
    fields: list[CustomFieldSpec] = Field(min_length=1, max_length=MAX_FIELD_COUNT)

    @field_validator("record_type", mode="before")
    @classmethod
    def _normalize_record_type(cls, value: Any) -> str:
        return normalize_slug(value if isinstance(value, str) else None, kind="Record type")

    @model_validator(mode="after")
    def _unique_field_names(self) -> CustomRecordSchema:
        seen: set[str] = set()
        for spec in self.fields:
            if spec.name in seen:
                raise ValueError(f"Duplicate field name {spec.name!r} in record schema.")
            seen.add(spec.name)
        if not self.label.strip():
            self.label = self.record_type.replace("_", " ").capitalize()
        return self


def _coerce_string(value: Any) -> Any:
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return value


def _coerce_number(value: Any) -> Any:
    if value is None or isinstance(value, bool):
        return None if value is None else value
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value.strip().replace(",", ""))
        except ValueError:
            return value
    return value


def _coerce_boolean(value: Any) -> Any:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes"}:
            return True
        if lowered in {"false", "no"}:
            return False
    return value


def _coerce_date(value: Any) -> Any:
    if value is None or isinstance(value, str) is False:
        return value
    cleaned = value.strip()
    if not cleaned:
        return None
    try:
        # Accept full ISO datetimes by keeping the date portion.
        parsed = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
        return parsed.date().isoformat()
    except ValueError:
        pass
    try:
        return date.fromisoformat(cleaned).isoformat()
    except ValueError as exc:
        raise ValueError(f"Date values must be ISO formatted (got {value!r}).") from exc


def _coerce_string_list(value: Any) -> Any:
    if value is None or isinstance(value, list):
        return value
    if isinstance(value, str):
        return [value] if value.strip() else []
    return value


_FIELD_TYPE_ANNOTATIONS: dict[str, type] = {
    "string": str,
    "number": float,
    "boolean": bool,
    "date": str,
    "string_list": list[str],
}

_FIELD_TYPE_COERCERS: dict[str, Any] = {
    "string": _coerce_string,
    "number": _coerce_number,
    "boolean": _coerce_boolean,
    "date": _coerce_date,
    "string_list": _coerce_string_list,
}


class _CustomRecordFieldsBase(BaseModel):
    @model_validator(mode="after")
    def _require_one_populated_field(self) -> _CustomRecordFieldsBase:
        values = self.model_dump()
        if not any(value not in (None, "", []) for value in values.values()):
            raise ValueError("Record must include at least one populated field value.")
        return self


def _make_field_coercer(coerce: Any) -> Any:
    def _validator(cls: type, value: Any) -> Any:  # noqa: ANN401 - dynamic coercion
        return coerce(value)

    return _validator


def build_record_fields_model(fields: list[CustomFieldSpec]) -> type[BaseModel]:
    """Build a Pydantic model validating one record's ``fields`` payload."""
    definitions: dict[str, Any] = {}
    validators: dict[str, Any] = {}
    for spec in fields:
        annotation = _FIELD_TYPE_ANNOTATIONS[spec.type]
        definitions[spec.name] = (annotation | None, None)
        validators[f"_coerce_{spec.name}"] = field_validator(spec.name, mode="before")(
            _make_field_coercer(_FIELD_TYPE_COERCERS[spec.type])
        )
    return create_model(
        "CustomRecordFields",
        __base__=_CustomRecordFieldsBase,
        __validators__=validators,
        **definitions,
    )
