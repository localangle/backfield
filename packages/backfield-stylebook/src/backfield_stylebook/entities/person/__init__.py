"""Person canonical persist, policy, and link helpers."""

from backfield_stylebook.entities.person.persist import (
    allocate_unique_person_canonical_slug,
    apply_canonical_persist_plan,
    apply_canonical_persist_plan_review_only,
    assert_canonical_link_invariant,
    create_standalone_canonical,
    link_substrate_to_canonical_atomic,
    link_to_existing_canonical,
    materialize_new_canonical_and_link,
    rank_canonical_suggestions_for_substrate,
    refresh_aliases_for_linked_person,
    requeue_substrate_after_story_remove,
    sync_substrate_person_into_stylebook,
    unlink_substrate_from_canonical,
    upsert_alias_for_canonical_text,
)
from backfield_stylebook.entities.person.policy import (
    decide_person_canonical_persist_plan,
    find_existing_person_canonical_id_by_alias,
    find_existing_person_canonical_id_by_identity,
    rank_person_canonical_recall_matches,
)
from backfield_stylebook.entities.person.types import (
    PERSON_NATURE_VALUES,
    normalize_person_text,
    person_identity_fingerprint,
)

__all__ = [
    "PERSON_NATURE_VALUES",
    "allocate_unique_person_canonical_slug",
    "apply_canonical_persist_plan",
    "apply_canonical_persist_plan_review_only",
    "assert_canonical_link_invariant",
    "create_standalone_canonical",
    "decide_person_canonical_persist_plan",
    "find_existing_person_canonical_id_by_alias",
    "find_existing_person_canonical_id_by_identity",
    "link_substrate_to_canonical_atomic",
    "link_to_existing_canonical",
    "materialize_new_canonical_and_link",
    "normalize_person_text",
    "person_identity_fingerprint",
    "rank_canonical_suggestions_for_substrate",
    "rank_person_canonical_recall_matches",
    "refresh_aliases_for_linked_person",
    "requeue_substrate_after_story_remove",
    "sync_substrate_person_into_stylebook",
    "unlink_substrate_from_canonical",
    "upsert_alias_for_canonical_text",
]
