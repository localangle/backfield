"""Sync auto-ingest veto before committing substrate→canonical links.

Blocks high-confidence but obviously wrong links (and alias-poisoned exact matches)
during ingest. Manual Stylebook UI commits are not gated here.
"""

from __future__ import annotations

from typing import Any, Literal

from backfield_db import (
    StylebookLocationCanonical,
    StylebookOrganizationCanonical,
    StylebookPersonCanonical,
    SubstrateLocation,
    SubstrateOrganization,
    SubstratePerson,
)
from sqlmodel import Session

from backfield_entities.canonical.jurisdiction import place_extract_components_from_entry
from backfield_entities.canonical.link_matrix import (
    autolink_container_to_fine_denied,
    link_pair_allowed,
)
from backfield_entities.canonical.plan_types import (
    CanonicalPersistDecision,
    CanonicalPersistPlan,
)
from backfield_entities.ingest.geocode_cache.sanity import (
    substrate_canonical_link_blocked_by_content_sanity,
)

EntityType = Literal["person", "organization", "location"]

VETO_OBVIOUS_NAME_MISMATCH = "obvious_name_mismatch"
VETO_CONTENT_SANITY_BLOCKED = "content_sanity_blocked"
VETO_LINK_PAIR_DENIED = "link_pair_denied"
VETO_CANONICAL_MISSING = "canonical_missing"


def _person_link_blocked(
    session: Session,
    *,
    person: SubstratePerson,
    canonical_id: str,
) -> str | None:
    from backfield_entities.entities.person.name_mismatch import person_link_is_obvious_mismatch
    from backfield_entities.quality.finders._name_mismatch_common import (
        load_person_editorial_alias_keys,
    )

    canon = session.get(StylebookPersonCanonical, canonical_id)
    if canon is None:
        return VETO_CANONICAL_MISSING
    editorial = load_person_editorial_alias_keys(session, canonical_ids=[canonical_id])
    alias_keys = editorial.get(canonical_id, frozenset())
    substrate_name = str(person.name or person.normalized_name or "")
    if person_link_is_obvious_mismatch(
        substrate_name=substrate_name,
        canonical_label=str(canon.label or ""),
        editorial_alias_keys=alias_keys,
    ):
        return VETO_OBVIOUS_NAME_MISMATCH
    return None


def _organization_link_blocked(
    session: Session,
    *,
    organization: SubstrateOrganization,
    canonical_id: str,
) -> str | None:
    from backfield_entities.entities.organization.name_mismatch import (
        organization_link_is_obvious_mismatch,
    )
    from backfield_entities.quality.finders._name_mismatch_common import (
        load_organization_editorial_alias_keys,
    )

    canon = session.get(StylebookOrganizationCanonical, canonical_id)
    if canon is None:
        return VETO_CANONICAL_MISSING
    editorial = load_organization_editorial_alias_keys(session, canonical_ids=[canonical_id])
    alias_keys = editorial.get(canonical_id, frozenset())
    substrate_name = str(organization.name or organization.normalized_name or "")
    if organization_link_is_obvious_mismatch(
        substrate_name=substrate_name,
        canonical_label=str(canon.label or ""),
        editorial_alias_keys=alias_keys,
    ):
        return VETO_OBVIOUS_NAME_MISMATCH
    return None


def _location_link_blocked(
    session: Session,
    *,
    location: SubstrateLocation,
    canonical_id: str,
    entry: dict[str, Any] | None = None,
) -> str | None:
    from backfield_entities.entities.location.link_identity import location_link_is_obvious_mismatch
    from backfield_entities.quality.finders._name_mismatch_common import (
        load_location_editorial_alias_keys,
    )

    canon = session.get(StylebookLocationCanonical, canonical_id)
    if canon is None:
        return VETO_CANONICAL_MISSING
    if not link_pair_allowed(location.location_type, canon.location_type):
        return VETO_LINK_PAIR_DENIED
    if autolink_container_to_fine_denied(location.location_type, canon.location_type):
        return VETO_LINK_PAIR_DENIED

    comps = place_extract_components_from_entry(location, entry)
    if substrate_canonical_link_blocked_by_content_sanity(
        substrate_location_type=location.location_type,
        location_text=str(location.name or ""),
        components=comps,
        match_label=str(canon.label or ""),
        match_formatted_address=canon.formatted_address,
        match_location_type=canon.location_type,
        match_geometry_type=canon.geometry_type,
    ):
        return VETO_CONTENT_SANITY_BLOCKED

    editorial = load_location_editorial_alias_keys(session, canonical_ids=[canonical_id])
    alias_keys = editorial.get(canonical_id, frozenset())
    if location_link_is_obvious_mismatch(
        substrate_name=str(location.name or ""),
        substrate_normalized_name=str(location.normalized_name or ""),
        substrate_location_type=location.location_type,
        components=comps,
        formatted_address=location.formatted_address,
        geometry_type=location.geometry_type,
        canonical_label=str(canon.label or ""),
        canonical_location_type=canon.location_type,
        editorial_alias_keys=alias_keys,
    ):
        return VETO_OBVIOUS_NAME_MISMATCH
    return None


def sync_link_commit_blocked(
    session: Session,
    *,
    entity_type: EntityType,
    substrate_row: SubstratePerson | SubstrateOrganization | SubstrateLocation,
    canonical_id: str,
    stylebook_id: int,
    entry: dict[str, Any] | None = None,
) -> str | None:
    """Return a veto code when auto-ingest must not commit this link, else ``None``.

    ``stylebook_id`` is accepted for call-site uniformity; lookups use the canonical id.
    """
    _ = stylebook_id
    cid = str(canonical_id or "").strip()
    if not cid:
        return VETO_CANONICAL_MISSING
    if entity_type == "person":
        assert isinstance(substrate_row, SubstratePerson)
        return _person_link_blocked(session, person=substrate_row, canonical_id=cid)
    if entity_type == "organization":
        assert isinstance(substrate_row, SubstrateOrganization)
        return _organization_link_blocked(
            session, organization=substrate_row, canonical_id=cid
        )
    assert isinstance(substrate_row, SubstrateLocation)
    return _location_link_blocked(
        session, location=substrate_row, canonical_id=cid, entry=entry
    )


def coerce_blocked_link_plan(
    plan: CanonicalPersistPlan,
    *,
    entity_type: EntityType,
    substrate_row: SubstratePerson | SubstrateOrganization | SubstrateLocation,
    veto_code: str,
) -> CanonicalPersistPlan:
    """Coerce a blocked ``LINK_EXISTING`` plan to ``materialize_new`` or ``defer``."""
    extra: dict[str, Any] = {
        "code": "sync_link_commit_veto",
        "veto_code": veto_code,
        "outcome": "coerced",
        "blocked_canonical_id": plan.existing_canonical_id,
    }
    merged = tuple(list(plan.resolution_reasons) + [extra])
    # Lazy imports avoid circular deps with entity policy modules that call this gate.
    may_materialize = False
    if entity_type == "person":
        from backfield_entities.entities.person.policy import (
            person_may_materialize_canonical_after_recall,
        )

        assert isinstance(substrate_row, SubstratePerson)
        may_materialize = person_may_materialize_canonical_after_recall(substrate_row)
    elif entity_type == "organization":
        from backfield_entities.entities.organization.policy import (
            organization_may_materialize_canonical_after_recall,
        )

        assert isinstance(substrate_row, SubstrateOrganization)
        may_materialize = organization_may_materialize_canonical_after_recall(substrate_row)
    else:
        from backfield_entities.entities.location.policy import (
            substrate_may_materialize_canonical_after_recall,
        )

        assert isinstance(substrate_row, SubstrateLocation)
        may_materialize = substrate_may_materialize_canonical_after_recall(substrate_row)
    if may_materialize:
        return CanonicalPersistPlan(
            decision=CanonicalPersistDecision.MATERIALIZE_NEW,
            resolution_reasons=merged,
        )
    return CanonicalPersistPlan(
        decision=CanonicalPersistDecision.DEFER,
        resolution_reasons=merged,
    )


def gate_or_coerce_link_plan(
    session: Session,
    plan: CanonicalPersistPlan,
    *,
    entity_type: EntityType,
    substrate_row: SubstratePerson | SubstrateOrganization | SubstrateLocation,
    stylebook_id: int,
    entry: dict[str, Any] | None = None,
) -> CanonicalPersistPlan:
    """If ``plan`` is ``LINK_EXISTING`` and blocked, return the coerced plan; else ``plan``."""
    if plan.decision != CanonicalPersistDecision.LINK_EXISTING:
        return plan
    if plan.existing_canonical_id is None:
        return plan
    veto = sync_link_commit_blocked(
        session,
        entity_type=entity_type,
        substrate_row=substrate_row,
        canonical_id=str(plan.existing_canonical_id),
        stylebook_id=stylebook_id,
        entry=entry,
    )
    if veto is None:
        return plan
    return coerce_blocked_link_plan(
        plan,
        entity_type=entity_type,
        substrate_row=substrate_row,
        veto_code=veto,
    )
