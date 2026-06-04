"""Compatibility re-exports: use ``canonical.plan_types`` and ``entities.location.policy``."""

from backfield_stylebook.canonical.plan_types import (
    ADJUDICATION_LINK_MIN_CONFIDENCE,
    CanonicalPersistDecision,
    CanonicalPersistPlan,
)
from backfield_stylebook.entities.location.policy import (
    decide_canonical_persist_plan,
    decide_location_canonical_persist_plan,
    defer_reason_payload,
    find_existing_canonical_id_by_alias,
    plan_has_ambiguous_canonical_match,
    plan_requires_llm_canonical_adjudication,
    rank_scored_canonical_recall_matches,
    substrate_may_materialize_canonical_after_recall,
)

__all__ = [
    "ADJUDICATION_LINK_MIN_CONFIDENCE",
    "CanonicalPersistDecision",
    "CanonicalPersistPlan",
    "decide_canonical_persist_plan",
    "decide_location_canonical_persist_plan",
    "defer_reason_payload",
    "find_existing_canonical_id_by_alias",
    "plan_has_ambiguous_canonical_match",
    "plan_requires_llm_canonical_adjudication",
    "rank_scored_canonical_recall_matches",
    "substrate_may_materialize_canonical_after_recall",
]
