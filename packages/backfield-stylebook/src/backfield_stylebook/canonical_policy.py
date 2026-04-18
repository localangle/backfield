"""Pure + session-backed policy: when to link, materialize, or defer Stylebook canonicals."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from backfield_db import StylebookLocationAlias, StylebookLocationCanonical, SubstrateLocation
from sqlmodel import Session, select

from backfield_stylebook.canonical_match_score import (
    AUTOLINK_MIN_SCORE,
    RECALL_MIN_SCORE,
    CanonicalMatchFeatures,
    SubstrateMatchInput,
    classify_recall_score,
    combined_score,
)
from backfield_stylebook.canonical_retrieval import (
    load_canonical_match_features,
    retrieve_candidate_canonical_ids,
)


class CanonicalPersistDecision(StrEnum):
    DEFER = "defer"
    LINK_EXISTING = "link_existing"
    MATERIALIZE_NEW = "materialize_new"


@dataclass(frozen=True)
class CanonicalPersistPlan:
    decision: CanonicalPersistDecision
    """When ``LINK_EXISTING``, the canonical row id to attach."""

    existing_canonical_id: int | None = None
    """Optional ``DEFER`` payload for ``canonical_review_reasons_json`` (fuzzy ambiguous path)."""

    defer_review_reasons: tuple[dict[str, Any], ...] | None = None


def find_existing_canonical_id_by_alias(
    session: Session,
    *,
    stylebook_id: int,
    normalized_name: str,
) -> int | None:
    """Return ``StylebookLocationCanonical.id`` if an alias matches in this Stylebook."""
    norm = str(normalized_name)
    stmt = (
        select(StylebookLocationCanonical)
        .join(
            StylebookLocationAlias,
            StylebookLocationAlias.location_canonical_id == StylebookLocationCanonical.id,
        )
        .where(
            StylebookLocationCanonical.stylebook_id == stylebook_id,
            StylebookLocationAlias.normalized_alias == norm,
        )
        .limit(1)
    )
    canon = session.exec(stmt).first()
    if canon is None or canon.id is None:
        return None
    return int(canon.id)


def _should_defer(*, places_bucket: str, location: SubstrateLocation) -> bool:
    if places_bucket == "needs_review":
        return True
    st = str(location.status or "")
    if st in ("needs_review", "failed"):
        return True
    lt = (location.location_type or "").strip().lower()
    if lt == "address":
        return True
    return False


def _should_materialize_new(location: SubstrateLocation) -> bool:
    if location.geometry_json is None:
        return False
    if str(location.status or "") != "resolved":
        return False
    return True


def decide_canonical_persist_plan(
    session: Session,
    *,
    stylebook_id: int,
    places_bucket: str,
    location: SubstrateLocation,
    entry: dict[str, Any],
) -> CanonicalPersistPlan:
    """Decide how persistence should treat Stylebook canonicalization for this substrate row.

    ``entry`` is reserved for future scoring (e.g. LLM hints); v1 rules use bucket + location only.
    """
    _ = entry
    if _should_defer(places_bucket=places_bucket, location=location):
        return CanonicalPersistPlan(decision=CanonicalPersistDecision.DEFER)

    cid = find_existing_canonical_id_by_alias(
        session, stylebook_id=stylebook_id, normalized_name=str(location.normalized_name)
    )
    if cid is not None:
        return CanonicalPersistPlan(
            decision=CanonicalPersistDecision.LINK_EXISTING,
            existing_canonical_id=cid,
        )

    recall = retrieve_candidate_canonical_ids(
        session,
        stylebook_id=stylebook_id,
        query_text=str(location.name),
        normalized_query=str(location.normalized_name),
    )
    if recall:
        cids = [cid for cid, _ in recall]
        bundles = load_canonical_match_features(session, canonical_ids=cids)
        substrate = SubstrateMatchInput(
            name=str(location.name),
            normalized_name=str(location.normalized_name),
            geometry_json=location.geometry_json,
        )
        best_id: int | None = None
        best_score = 0.0
        for canon_id, hint in recall:
            row = bundles.get(canon_id)
            if row is None:
                continue
            canon, alias_tup = row
            feat = CanonicalMatchFeatures(
                canonical_id=canon_id,
                label=str(canon.label),
                normalized_aliases=alias_tup,
                geometry_json=canon.geometry_json,
                retrieval_string_hint=hint,
            )
            sc = combined_score(substrate, feat)
            if sc >= best_score:
                best_score = sc
                best_id = canon_id
        tier = classify_recall_score(best_score)
        if tier == "autolink" and best_id is not None:
            return CanonicalPersistPlan(
                decision=CanonicalPersistDecision.LINK_EXISTING,
                existing_canonical_id=int(best_id),
            )
        if tier == "ambiguous" and best_id is not None:
            return CanonicalPersistPlan(
                decision=CanonicalPersistDecision.DEFER,
                defer_review_reasons=(
                    {
                        "code": "ambiguous_canonical_match",
                        "best_canonical_id": int(best_id),
                        "best_score": float(best_score),
                        "autolink_min_score": float(AUTOLINK_MIN_SCORE),
                        "recall_min_score": float(RECALL_MIN_SCORE),
                    },
                ),
            )

    if _should_materialize_new(location):
        return CanonicalPersistPlan(decision=CanonicalPersistDecision.MATERIALIZE_NEW)

    return CanonicalPersistPlan(decision=CanonicalPersistDecision.DEFER)


def defer_reason_payload(
    *,
    places_bucket: str,
    location: SubstrateLocation,
) -> list[dict[str, Any]]:
    """Structured reasons for ``canonical_review_reasons_json`` when deferring."""
    return [
        {
            "code": "deferred_policy",
            "places_bucket": places_bucket,
            "substrate_status": str(location.status or ""),
            "location_type": location.location_type,
        }
    ]
