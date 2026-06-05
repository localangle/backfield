"""Tests for backfield_entities.registry.entity_types registry and fingerprint helper."""

from __future__ import annotations

from backfield_entities.registry.entity_types import (
    ENTITY_REGISTRY,
    all_entity_types,
    compute_identity_fingerprint,
    consolidated_key_for,
    entity_type_from_consolidated_key,
    normalize_entity_name,
)


def test_registry_covers_all_entity_types() -> None:
    assert set(all_entity_types()) == {"location", "person", "organization", "work"}
    assert len(ENTITY_REGISTRY) == 4


def test_consolidated_keys_match_entity_type_slugs() -> None:
    assert consolidated_key_for("location") == "places"
    assert consolidated_key_for("person") == "people"
    assert consolidated_key_for("organization") == "organizations"
    assert consolidated_key_for("work") == "works"


def test_entity_type_from_consolidated_key_round_trip() -> None:
    for slug in all_entity_types():
        key = consolidated_key_for(slug)
        assert entity_type_from_consolidated_key(key) == slug


def test_compute_identity_fingerprint_is_stable_and_sensitive() -> None:
    fp1 = compute_identity_fingerprint("person", normalized_name="Jane Doe")
    fp2 = compute_identity_fingerprint("person", normalized_name="jane doe")
    fp3 = compute_identity_fingerprint(
        "person",
        normalized_name="Jane Doe",
        birth_year=1980,
    )
    assert fp1 == fp2
    assert fp1 != fp3
    assert len(fp1) == 64


def test_normalize_entity_name_strips_and_lowercases() -> None:
    assert normalize_entity_name("  Chicago  ") == "chicago"
