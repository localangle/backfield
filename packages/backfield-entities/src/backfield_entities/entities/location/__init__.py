"""Location canonical persist, policy, and PlaceExtract type helpers."""

from backfield_entities.entities.location.geometry_apply import (
    apply_canonical_geometry_to_substrates,
    suggest_substrate_for_geometry_apply,
)
from backfield_entities.entities.location.persist import (
    apply_canonical_persist_plan,
    apply_canonical_persist_plan_review_only,
    assert_canonical_link_invariant,
    create_standalone_canonical,
    link_to_existing_canonical,
    location_canonical_has_editorial_catalog_provenance,
    materialize_new_canonical_and_link,
    maybe_prune_ingest_orphan_location_canonical,
    refresh_aliases_for_linked_location,
)
from backfield_entities.entities.location.policy import (
    decide_location_canonical_persist_plan,
    find_existing_canonical_id_by_alias,
    plan_has_ambiguous_canonical_match,
    plan_requires_llm_canonical_adjudication,
    rank_scored_canonical_recall_matches,
    substrate_may_materialize_canonical_after_recall,
)

__all__ = [
    "apply_canonical_geometry_to_substrates",
    "apply_canonical_persist_plan",
    "apply_canonical_persist_plan_review_only",
    "assert_canonical_link_invariant",
    "create_standalone_canonical",
    "decide_location_canonical_persist_plan",
    "find_existing_canonical_id_by_alias",
    "link_to_existing_canonical",
    "location_canonical_has_editorial_catalog_provenance",
    "materialize_new_canonical_and_link",
    "maybe_prune_ingest_orphan_location_canonical",
    "plan_has_ambiguous_canonical_match",
    "plan_requires_llm_canonical_adjudication",
    "rank_scored_canonical_recall_matches",
    "refresh_aliases_for_linked_location",
    "substrate_may_materialize_canonical_after_recall",
    "suggest_substrate_for_geometry_apply",
]
