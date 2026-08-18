"""Unit tests for catalog-geography apply helpers."""

from __future__ import annotations

from backfield_entities.entities.location.geometry_apply import (
    suggest_substrate_for_geometry_apply,
)


def test_suggest_same_neighborhood_types() -> None:
    assert (
        suggest_substrate_for_geometry_apply(
            substrate_location_type="neighborhood",
            canonical_location_type="neighborhood",
        )
        is True
    )


def test_suggest_comparable_admin_types() -> None:
    assert (
        suggest_substrate_for_geometry_apply(
            substrate_location_type="community_area",
            canonical_location_type="neighborhood",
        )
        is True
    )


def test_skip_address_like_even_if_types_otherwise_open() -> None:
    assert (
        suggest_substrate_for_geometry_apply(
            substrate_location_type="address",
            canonical_location_type="neighborhood",
        )
        is False
    )


def test_skip_place_linked_to_neighborhood() -> None:
    assert (
        suggest_substrate_for_geometry_apply(
            substrate_location_type="place",
            canonical_location_type="neighborhood",
        )
        is False
    )
