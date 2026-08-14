"""Typed Stylebook canonical metadata: validation, serialization, and attr filters."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, TypeAlias

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import ColumnElement, exists, func
from sqlmodel import col

MetaValueType = Literal["text", "number", "boolean"]
AttrOp = Literal["eq", "neq", "ieq", "ineq", "lt", "lte", "gt", "gte", "exists"]

META_TYPE_PATTERN = re.compile(r"^[a-z0-9_]+$")
MAX_ATTR_CLAUSES = 25
MAX_ATTR_VALUES_PER_CLAUSE = 50

CanonicalMetaScalar: TypeAlias = str | int | float | bool | Decimal


class CanonicalMetaItemOut(BaseModel):
    """Public/Stylebook metadata item: discriminated scalar ``value``."""

    meta_type: str
    value_type: MetaValueType
    value: str | float | bool
    id: int | None = None


class CanonicalMetaWrite(BaseModel):
    """Validated write payload for a typed metadata attribute."""

    meta_type: str = Field(..., min_length=1)
    value_type: MetaValueType
    value: str | int | float | bool

    @model_validator(mode="after")
    def _normalize_and_validate(self) -> CanonicalMetaWrite:
        normalized = normalize_meta_type(self.meta_type)
        validate_typed_value(self.value_type, self.value)
        if self.value_type == "text":
            text = str(self.value).strip()
            if ":" in text:
                raise ValueError("text metadata values cannot contain ':'")
            object.__setattr__(self, "value", text)
        object.__setattr__(self, "meta_type", normalized)
        return self


@dataclass(frozen=True)
class AttrClause:
    meta_type: str
    op: AttrOp
    values: tuple[str, ...] = ()
    negate: bool = False


class AttrFilterError(ValueError):
    """Invalid ``attr`` filter clause."""


def normalize_meta_type(raw: str) -> str:
    """Normalize a metadata key to a slug; raise ValueError if invalid."""
    slug = raw.strip().lower().replace("-", "_").replace(" ", "_")
    if not slug or not META_TYPE_PATTERN.fullmatch(slug):
        raise ValueError(
            "meta_type must be a lowercase slug using letters, digits, and underscores"
        )
    return slug


def validate_typed_value(value_type: MetaValueType, value: object) -> None:
    """Raise ValueError when ``value`` does not match ``value_type``."""
    if value_type == "text":
        if not isinstance(value, str):
            raise ValueError("text metadata requires a string value")
        if not value.strip():
            raise ValueError("text metadata cannot be empty")
        return
    if value_type == "boolean":
        if type(value) is not bool:
            raise ValueError("boolean metadata requires a boolean value")
        return
    if value_type == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float, Decimal, str)):
            raise ValueError("number metadata requires a numeric value")
        number = _coerce_number(value)
        if number is None:
            raise ValueError("number metadata must be a finite number")
        return
    raise ValueError(f"unsupported value_type: {value_type}")


def _coerce_number(value: object) -> Decimal | None:
    try:
        if isinstance(value, bool):
            return None
        if isinstance(value, Decimal):
            number = value
        elif isinstance(value, int):
            number = Decimal(value)
        elif isinstance(value, float):
            if not math.isfinite(value):
                return None
            number = Decimal(str(value))
        elif isinstance(value, str):
            text = value.strip()
            if not text:
                return None
            number = Decimal(text)
        else:
            return None
    except (InvalidOperation, ValueError):
        return None
    if not number.is_finite():
        return None
    return number


def typed_columns_for_value(
    value_type: MetaValueType,
    value: object,
) -> tuple[str | None, Decimal | None, bool | None]:
    """Return ``(value_text, value_number, value_boolean)`` for storage."""
    validate_typed_value(value_type, value)
    if value_type == "text":
        return str(value).strip(), None, None
    if value_type == "number":
        number = _coerce_number(value)
        assert number is not None
        return None, number, None
    assert type(value) is bool
    return None, None, value


def api_value_from_row(
    *,
    value_type: str,
    value_text: str | None,
    value_number: Decimal | None,
    value_boolean: bool | None,
) -> str | float | bool:
    """Build the discriminated API ``value`` from typed columns."""
    if value_type == "text":
        return value_text or ""
    if value_type == "number":
        if value_number is None:
            return 0.0
        # Prefer int when integral for cleaner JSON.
        if value_number == value_number.to_integral_value():
            return int(value_number)
        return float(value_number)
    return bool(value_boolean)


def meta_row_to_api(
    row: Any,
    *,
    include_id: bool = True,
) -> dict[str, Any]:
    """Serialize a Stylebook*Meta ORM row to the public/Stylebook JSON shape."""
    value = api_value_from_row(
        value_type=str(row.value_type),
        value_text=row.value_text,
        value_number=row.value_number,
        value_boolean=row.value_boolean,
    )
    out: dict[str, Any] = {
        "meta_type": str(row.meta_type),
        "value_type": str(row.value_type),
        "value": value,
    }
    if include_id and getattr(row, "id", None) is not None:
        out["id"] = int(row.id)
    return out


def apply_typed_values_to_row(
    row: Any,
    *,
    meta_type: str,
    value_type: MetaValueType,
    value: object,
) -> None:
    """Set typed columns on an existing meta ORM row."""
    value_text, value_number, value_boolean = typed_columns_for_value(value_type, value)
    row.meta_type = meta_type
    row.value_type = value_type
    row.value_text = value_text
    row.value_number = value_number
    row.value_boolean = value_boolean


def infer_eq_value_type(raw: str) -> MetaValueType:
    """Infer value type for ``eq``/``neq`` filter literals."""
    if raw in ("true", "false"):
        return "boolean"
    if _coerce_number(raw) is not None:
        return "number"
    return "text"


def parse_attr_clauses(attr: list[str]) -> tuple[AttrClause, ...]:
    """Parse repeatable ``attr`` query tokens into filter clauses."""
    if not attr:
        return ()
    if len(attr) > MAX_ATTR_CLAUSES:
        raise AttrFilterError(f"Too many attr clauses. Maximum is {MAX_ATTR_CLAUSES}.")

    clauses: list[AttrClause] = []
    for raw_token in attr:
        token = raw_token.strip()
        if not token:
            raise AttrFilterError("Invalid attr clause: empty token.")
        negate = False
        if token.startswith("!"):
            negate = True
            token = token[1:].strip()
            if not token:
                raise AttrFilterError("Invalid attr clause: missing key after '!'.")

        parts = token.split(":")
        if any(part == "" for part in parts):
            raise AttrFilterError(f"Invalid attr clause: {raw_token!r}.")

        try:
            meta_type = normalize_meta_type(parts[0])
        except ValueError as exc:
            raise AttrFilterError(str(exc)) from exc

        if len(parts) == 1:
            clauses.append(AttrClause(meta_type=meta_type, op="exists", negate=negate))
            continue

        if len(parts) == 2:
            op: AttrOp = "eq"
            values_raw = parts[1]
        elif len(parts) == 3:
            op_raw = parts[1].strip().lower()
            if op_raw not in {"eq", "neq", "ieq", "ineq", "lt", "lte", "gt", "gte"}:
                raise AttrFilterError(f"Unsupported attr operator: {op_raw!r}.")
            op = op_raw  # type: ignore[assignment]
            values_raw = parts[2]
        else:
            raise AttrFilterError(
                "Invalid attr clause: too many ':' segments "
                "(text values cannot contain ':')."
            )

        values = tuple(v for v in (part.strip() for part in values_raw.split("|")) if v)
        if not values:
            raise AttrFilterError(f"Invalid attr clause for '{meta_type}': missing value.")
        if len(values) > MAX_ATTR_VALUES_PER_CLAUSE:
            raise AttrFilterError(
                f"Too many values in attr clause for '{meta_type}'. "
                f"Maximum is {MAX_ATTR_VALUES_PER_CLAUSE}."
            )
        if len(values) > 1 and op not in {"eq", "ieq"}:
            raise AttrFilterError(
                f"OR ('|') is only supported for eq/ieq (got {op} on '{meta_type}')."
            )
        if op in {"ieq", "ineq"}:
            for value in values:
                if infer_eq_value_type(value) != "text":
                    raise AttrFilterError(
                        f"Operator {op} requires text values (got {value!r})."
                    )
        if op in {"lt", "lte", "gt", "gte"}:
            if _coerce_number(values[0]) is None:
                raise AttrFilterError(
                    f"Operator {op} requires a numeric value (got {values[0]!r})."
                )
        if op in {"eq", "neq"}:
            inferred = {infer_eq_value_type(v) for v in values}
            if len(inferred) != 1:
                raise AttrFilterError(
                    f"OR values for '{meta_type}' must share one value type."
                )
        clauses.append(
            AttrClause(meta_type=meta_type, op=op, values=values, negate=negate)
        )
    return tuple(clauses)


def _value_predicate(
    meta_model: type[Any],
    clause: AttrClause,
) -> ColumnElement[bool]:
    """Build the value-matching predicate for one attr clause (excluding existence)."""
    op = clause.op
    if op == "exists":
        return True  # type: ignore[return-value]

    if op in {"ieq", "ineq"}:
        lowered = [v.lower() for v in clause.values]
        pred = func.lower(col(meta_model.value_text)).in_(lowered)
        typed = col(meta_model.value_type) == "text"
        match = typed & pred
        if op == "ineq":
            # "not equal to any" for multi-value is unusual; single-value ineq:
            # value_type text AND lower(text) not in values — still require the row exists
            # with that meta_type (caller wraps exists). For ineq, match rows whose text
            # is not in the set.
            match = typed & ~pred
        return match

    if op in {"lt", "lte", "gt", "gte"}:
        number = _coerce_number(clause.values[0])
        assert number is not None
        column = col(meta_model.value_number)
        typed = col(meta_model.value_type) == "number"
        if op == "lt":
            return typed & (column < number)
        if op == "lte":
            return typed & (column <= number)
        if op == "gt":
            return typed & (column > number)
        return typed & (column >= number)

    # eq / neq
    value_type = infer_eq_value_type(clause.values[0])
    typed = col(meta_model.value_type) == value_type
    if value_type == "text":
        pred = col(meta_model.value_text).in_(clause.values)
    elif value_type == "number":
        numbers = [_coerce_number(v) for v in clause.values]
        assert all(n is not None for n in numbers)
        pred = col(meta_model.value_number).in_(numbers)
    else:
        bools = [v == "true" for v in clause.values]
        pred = col(meta_model.value_boolean).in_(bools)
    match = typed & pred
    if op == "neq":
        match = typed & ~pred
    return match


def canonical_attr_exists_filter(
    *,
    meta_model: type[Any],
    canonical_fk_attr: str,
    canonical_id_column: Any,
    clause: AttrClause,
) -> ColumnElement[bool]:
    """Return an EXISTS (or NOT EXISTS) filter linking a canonical row to meta."""
    fk = getattr(meta_model, canonical_fk_attr)
    conditions = [
        fk == canonical_id_column,
        col(meta_model.meta_type) == clause.meta_type,
    ]
    if clause.op != "exists":
        conditions.append(_value_predicate(meta_model, clause))
    statement = exists().where(*conditions)
    if clause.negate:
        # For exists, negate means lacking the key.
        # For value ops, negate means NOT matching the value predicate (still via NOT EXISTS
        # of matching rows). Note: "not equal" is also available as neq/ineq without '!'.
        return ~statement
    return statement


def apply_attr_clauses_to_filters(
    filters: list[ColumnElement[bool]],
    *,
    meta_model: type[Any],
    canonical_fk_attr: str,
    canonical_id_column: Any,
    clauses: tuple[AttrClause, ...],
) -> None:
    """Append AND-combined attr clause filters onto ``filters``."""
    for clause in clauses:
        filters.append(
            canonical_attr_exists_filter(
                meta_model=meta_model,
                canonical_fk_attr=canonical_fk_attr,
                canonical_id_column=canonical_id_column,
                clause=clause,
            )
        )


def coerce_import_scalar(raw: object) -> tuple[MetaValueType, CanonicalMetaScalar]:
    """Infer a typed scalar from a GeoJSON/CSV property value."""
    if isinstance(raw, bool):
        return "boolean", raw
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        number = _coerce_number(raw)
        if number is None:
            raise ValueError("non-finite numeric metadata")
        return "number", number
    if isinstance(raw, Decimal):
        if not raw.is_finite():
            raise ValueError("non-finite numeric metadata")
        return "number", raw
    if isinstance(raw, (dict, list)):
        raise ValueError("metadata values must be text, number, or boolean (not nested JSON)")
    text = str(raw).strip()
    if not text:
        raise ValueError("empty metadata value")
    if ":" in text:
        raise ValueError("text metadata values cannot contain ':'")
    return "text", text
