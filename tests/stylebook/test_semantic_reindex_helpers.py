"""Unit tests for semantic re-index helpers."""

from __future__ import annotations

from backfield_stylebook.semantic_indexing.reindex import (
    location_patch_affects_semantic_index,
    person_patch_affects_semantic_index,
    person_patch_entity_fields_changed,
)
from stylebook_api.entities.location.locations import PatchLocationBody
from stylebook_api.entities.person.people import PatchSubstratePersonBody


def test_person_patch_sort_key_only_does_not_affect_semantic_index() -> None:
    body = PatchSubstratePersonBody(sort_key="smith-j")
    assert person_patch_affects_semantic_index(body) is False
    assert person_patch_entity_fields_changed(body) is False


def test_person_patch_name_affects_semantic_index() -> None:
    body = PatchSubstratePersonBody(name="Jane Smith")
    assert person_patch_affects_semantic_index(body) is True
    assert person_patch_entity_fields_changed(body) is True


def test_person_patch_role_affects_semantic_index() -> None:
    body = PatchSubstratePersonBody(role_in_story="protagonist")
    assert person_patch_affects_semantic_index(body) is True
    assert person_patch_entity_fields_changed(body) is False


def test_location_patch_status_only_does_not_affect_semantic_index() -> None:
    body = PatchLocationBody(status="active")
    assert location_patch_affects_semantic_index(body) is False


def test_location_patch_name_affects_semantic_index() -> None:
    body = PatchLocationBody(name="City Hall")
    assert location_patch_affects_semantic_index(body) is True
