"""Stylebook domain logic shared by worker, stylebook-api, and core-api."""

from backfield_stylebook.bootstrap import ensure_default_stylebook_for_organization
from backfield_stylebook.canonical_link import (
    CANONICAL_LINK_LINKED,
    CANONICAL_LINK_PENDING,
    CANONICAL_LINK_UNLINKED,
    CANONICAL_LINK_WAIVED,
)
from backfield_stylebook.canonical_policy import (
    CanonicalPersistDecision,
    CanonicalPersistPlan,
    decide_canonical_persist_plan,
    find_existing_canonical_id_by_alias,
)
from backfield_stylebook.locations import (
    apply_canonical_persist_plan,
    assert_canonical_link_invariant,
    create_standalone_canonical,
    link_to_existing_canonical,
    materialize_new_canonical_and_link,
    refresh_aliases_for_linked_location,
    sync_substrate_location_into_stylebook,
)
from backfield_stylebook.resolve import resolve_stylebook_id_for_project_id

__all__ = [
    "CANONICAL_LINK_LINKED",
    "CANONICAL_LINK_PENDING",
    "CANONICAL_LINK_UNLINKED",
    "CANONICAL_LINK_WAIVED",
    "CanonicalPersistDecision",
    "CanonicalPersistPlan",
    "apply_canonical_persist_plan",
    "assert_canonical_link_invariant",
    "create_standalone_canonical",
    "decide_canonical_persist_plan",
    "ensure_default_stylebook_for_organization",
    "find_existing_canonical_id_by_alias",
    "link_to_existing_canonical",
    "materialize_new_canonical_and_link",
    "refresh_aliases_for_linked_location",
    "resolve_stylebook_id_for_project_id",
    "sync_substrate_location_into_stylebook",
]
