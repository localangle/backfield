"""Tests for shared accent/apostrophe normalization."""

from __future__ import annotations

from backfield_entities.entities.location.recall import location_alias_lookup_keys
from backfield_entities.text.match_normalize import (
    alias_lookup_keys,
    match_fold_key,
    normalize_match_text,
)


def test_normalize_match_text_maps_unicode_apostrophes() -> None:
    assert normalize_match_text("Cook County State\u2019s Attorney\u2019s Office") == (
        "cook county state's attorney's office"
    )


def test_match_fold_key_folds_accents() -> None:
    assert match_fold_key("São Paulo, Brazil") == match_fold_key("Sao Paulo, Brazil")


def test_alias_lookup_keys_include_folded_variant() -> None:
    keys = alias_lookup_keys("São Paulo, Brazil")
    assert "são paulo, brazil" in keys
    assert "sao paulo, brazil" in keys


def test_location_alias_lookup_keys_include_loose_form() -> None:
    keys = location_alias_lookup_keys("Cook County State\u2019s Attorney\u2019s Office, IL")
    assert "cook county state's attorney's office, il" in keys
    assert "cook county state s attorney s office il" in keys
