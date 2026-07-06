"""Stylebook catalog list/search filters with accent- and apostrophe-tolerant matching."""

from __future__ import annotations

from typing import Any

from sqlalchemy import exists, func, literal, or_, select
from sqlalchemy.sql.elements import ColumnElement

from backfield_entities.text.match_normalize import (
    escape_ilike_metacharacters,
    match_fold_key,
    normalize_match_text,
)

_UNICODE_APOSTROPHE_FROM = literal("\u2018\u2019\u02bc\u0060")
_UNICODE_APOSTROPHE_TO = literal("''''")


def label_apostrophe_normalized(column: Any) -> Any:
    """SQL expression: lowercase label with unicode apostrophes mapped to ASCII ``'``."""
    return func.lower(
        func.trim(
            func.translate(column, _UNICODE_APOSTROPHE_FROM, _UNICODE_APOSTROPHE_TO),
        )
    )


def _ilike_terms_for_query(q_text: str) -> list[str]:
    q = q_text.strip()
    if not q:
        return []
    terms = [f"%{escape_ilike_metacharacters(q)}%"]
    folded = match_fold_key(q)
    norm = normalize_match_text(q)
    if folded and folded != norm:
        terms.append(f"%{escape_ilike_metacharacters(folded)}%")
    # Preserve order, drop duplicates.
    seen: set[str] = set()
    out: list[str] = []
    for term in terms:
        if term not in seen:
            seen.add(term)
            out.append(term)
    return out


def catalog_label_alias_ilike_filter(
    q_text: str,
    *,
    label_column: Any,
    canonical_id_column: Any,
    alias_model: Any,
    alias_canonical_id_column: Any,
    alias_normalized_column: Any,
) -> ColumnElement[bool]:
    """Match catalog ``label`` or any non-suppressed alias for ``q_text``."""
    terms = _ilike_terms_for_query(q_text)
    if not terms:
        raise ValueError("q_text must be non-empty")

    label_conditions: list[ColumnElement[bool]] = []
    for term in terms:
        label_conditions.append(label_column.ilike(term, escape="\\"))
        label_conditions.append(label_apostrophe_normalized(label_column).ilike(term, escape="\\"))

    alias_conditions: list[ColumnElement[bool]] = [
        alias_normalized_column.ilike(term, escape="\\") for term in terms
    ]

    alias_match = exists(
        select(literal(1)).where(
            alias_canonical_id_column == canonical_id_column,
            alias_model.suppressed.is_(False),
            or_(*alias_conditions),
        )
    )
    return or_(*label_conditions, alias_match)


def substrate_name_ilike_filter(
    q_text: str,
    *,
    name_column: Any,
    normalized_name_column: Any,
) -> ColumnElement[bool]:
    """Match substrate display or normalized name with apostrophe and accent variants."""
    terms = _ilike_terms_for_query(q_text)
    if not terms:
        raise ValueError("q_text must be non-empty")

    conditions: list[ColumnElement[bool]] = []
    for term in terms:
        conditions.append(name_column.ilike(term, escape="\\"))
        conditions.append(normalized_name_column.ilike(term, escape="\\"))
        conditions.append(label_apostrophe_normalized(name_column).ilike(term, escape="\\"))
        conditions.append(
            label_apostrophe_normalized(normalized_name_column).ilike(term, escape="\\")
        )
    return or_(*conditions)
