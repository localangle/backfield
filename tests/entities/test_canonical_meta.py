"""Unit tests for typed canonical metadata helpers."""

from __future__ import annotations

import pytest
from backfield_entities.catalog.canonical_meta import (
    AttrFilterError,
    CanonicalMetaWrite,
    coerce_import_scalar,
    normalize_meta_type,
    parse_attr_clauses,
    typed_columns_for_value,
)


def test_normalize_meta_type_slug() -> None:
    assert normalize_meta_type("Party") == "party"
    assert normalize_meta_type("school-district") == "school_district"
    with pytest.raises(ValueError):
        normalize_meta_type("Bad Key!")


def test_typed_columns_and_write() -> None:
    assert typed_columns_for_value("text", "Democratic") == ("Democratic", None, None)
    write = CanonicalMetaWrite(meta_type="Population", value_type="number", value=12000)
    assert write.meta_type == "population"
    assert write.value == 12000
    with pytest.raises(Exception):
        CanonicalMetaWrite(meta_type="party", value_type="text", value=" ")


def test_parse_attr_clauses_grammar() -> None:
    clauses = parse_attr_clauses(
        ["party", "!population", "party:Democratic", "population:lt:50000", "party:ieq:dem"]
    )
    assert clauses[0].op == "exists" and clauses[0].meta_type == "party"
    assert clauses[1].negate and clauses[1].op == "exists"
    assert clauses[2].op == "eq" and clauses[2].values == ("Democratic",)
    assert clauses[3].op == "lt"
    assert clauses[4].op == "ieq"
    or_clause = parse_attr_clauses(["party:eq:Democratic|Republican"])[0]
    assert or_clause.values == ("Democratic", "Republican")
    with pytest.raises(AttrFilterError):
        parse_attr_clauses(["population:lt:1|2"])
    with pytest.raises(AttrFilterError):
        parse_attr_clauses(["note:hello:world:extra"])


def test_coerce_import_scalar() -> None:
    assert coerce_import_scalar(42)[0] == "number"
    assert coerce_import_scalar(True) == ("boolean", True)
    assert coerce_import_scalar("hello") == ("text", "hello")
    with pytest.raises(ValueError):
        coerce_import_scalar({"nested": True})
