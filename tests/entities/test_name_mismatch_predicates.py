"""Unit tests for person/organization obvious link mismatch predicates."""

from __future__ import annotations

from backfield_entities.entities.organization.name_mismatch import (
    organization_link_is_obvious_mismatch,
    organization_names_share_significant_token,
)
from backfield_entities.entities.person.name_mismatch import person_link_is_obvious_mismatch


def test_person_mismatch_clear_positive() -> None:
    assert person_link_is_obvious_mismatch(
        substrate_name="John Smith",
        canonical_label="Jane Doe",
    )


def test_person_mismatch_same_name_rescued() -> None:
    assert not person_link_is_obvious_mismatch(
        substrate_name="John Smith",
        canonical_label="John Smith",
    )


def test_person_mismatch_surname_only_rescued() -> None:
    assert not person_link_is_obvious_mismatch(
        substrate_name="Smith",
        canonical_label="Jane Smith",
    )


def test_person_mismatch_single_token_excluded() -> None:
    assert not person_link_is_obvious_mismatch(
        substrate_name="Bob",
        canonical_label="Robert Smith",
    )


def test_person_mismatch_editorial_alias_rescued() -> None:
    assert not person_link_is_obvious_mismatch(
        substrate_name="Mark Zuckerberg",
        canonical_label="Meta Platforms",
        editorial_alias_keys=frozenset({"mark zuckerberg"}),
    )


def test_organization_mismatch_clear_positive() -> None:
    assert organization_link_is_obvious_mismatch(
        substrate_name="Acme Corporation",
        canonical_label="Globex Industries",
    )


def test_organization_mismatch_acronym_rescued() -> None:
    assert not organization_link_is_obvious_mismatch(
        substrate_name="CPS",
        canonical_label="Chicago Public Schools",
    )


def test_organization_mismatch_shared_token_rescued() -> None:
    assert organization_names_share_significant_token(
        "Chicago Teachers Union",
        "Chicago Public Schools",
    )
    assert not organization_link_is_obvious_mismatch(
        substrate_name="Chicago Teachers Union",
        canonical_label="Chicago Public Schools",
    )


def test_organization_mismatch_editorial_alias_rescued() -> None:
    assert not organization_link_is_obvious_mismatch(
        substrate_name="Facebook",
        canonical_label="Meta Platforms",
        editorial_alias_keys=frozenset({"facebook"}),
    )


def test_organization_mismatch_equal_normalized_rescued() -> None:
    assert not organization_link_is_obvious_mismatch(
        substrate_name="Chicago Police Department",
        canonical_label="Chicago Police Department",
    )
