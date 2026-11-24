"""Candidate decisions: link a candidate to a record, create a record from it, or defer it.

A candidate is a project-level record (a "substrate" row) waiting for a canonical. These three
functions are the one implementation the Stylebook app's accept and defer routes and the cleanup
API share, for locations, people and organizations. They change rows and write events, and never
commit: the caller owns the transaction.

Problems are raised as ``CandidateDecisionError`` subclasses so each caller can report them its own
way (an HTTP status in the app, a reason code in the cleanup API).
"""

from __future__ import annotations

from typing import Any

from backfield_db import StylebookLocationCanonical
from backfield_events import record_canonical_created
from sqlmodel import Session

from backfield_entities.canonical.jurisdiction import (
    place_extract_components_from_entry,
    stylebook_district_fields_from_components,
    stylebook_jurisdiction_fields_from_components,
)
from backfield_entities.canonical.link import (
    CANONICAL_LINK_LINKED,
    CANONICAL_LINK_PENDING,
    CANONICAL_LINK_WAIVED,
)
from backfield_entities.canonical.slug import allocate_unique_canonical_slug
from backfield_entities.cleanup.entity_models import CleanupEntityModels, SubstrateRow
from backfield_entities.entities.linking.substrate_actions import (
    link_substrate_to_canonical_atomic as link_location_to_canonical,
)
from backfield_entities.entities.location.persist import refresh_aliases_for_linked_location
from backfield_entities.entities.location.types import PLACE_EXTRACT_LOCATION_TYPES
from backfield_entities.entities.organization.persist import (
    link_substrate_to_canonical_atomic as link_organization_to_canonical,
)
from backfield_entities.entities.organization.persist import (
    materialize_new_canonical_and_link as materialize_organization,
)
from backfield_entities.entities.person.persist import (
    link_substrate_to_canonical_atomic as link_person_to_canonical,
)
from backfield_entities.entities.person.persist import (
    materialize_new_canonical_and_link as materialize_person,
)
from backfield_entities.geo.geometry_bind import GeometryBindError, assign_geojson_geometry

LINKED_EXISTING_REASON = "linked_manual_accept_existing"
LINKED_NEW_REASON = "linked_manual_accept_create_new"
DEFERRED_REASON = "deferred_manual"


class CandidateDecisionError(ValueError):
    """A decision that cannot be made on this candidate."""


class CandidateAlreadyLinkedError(CandidateDecisionError):
    """The candidate already points at a canonical."""


class CandidateNotInQueueError(CandidateDecisionError):
    """The candidate is not waiting for a decision (its status is not pending or deferred)."""


class CandidateCanonicalNotFoundError(CandidateDecisionError):
    """The canonical to link to does not exist."""


class CandidateCanonicalElsewhereError(CandidateDecisionError):
    """The canonical to link to belongs to another Stylebook."""


class CandidateInvalidError(CandidateDecisionError):
    """The request cannot make a record: a missing name, an unknown type, or unusable geometry."""


def _linked_canonical_id(models: CleanupEntityModels, candidate: SubstrateRow) -> str | None:
    value = getattr(candidate, models.substrate_canonical_column)
    return str(value) if value is not None else None


def _require_open_candidate(
    models: CleanupEntityModels, candidate: SubstrateRow, *, allowed: tuple[str, ...]
) -> None:
    if _linked_canonical_id(models, candidate) is not None:
        raise CandidateAlreadyLinkedError(f"This {models.singular} is already linked to a record.")
    if candidate.canonical_link_status not in allowed:
        raise CandidateNotInQueueError(
            f"This {models.singular} is not waiting for a decision "
            f"(its status is {candidate.canonical_link_status})."
        )


def defer_candidate(
    session: Session,
    models: CleanupEntityModels,
    candidate: SubstrateRow,
    *,
    provenance: str,
) -> None:
    """Take a pending candidate out of the open queue without linking it."""
    _require_open_candidate(models, candidate, allowed=(CANONICAL_LINK_PENDING,))
    candidate.canonical_link_status = CANONICAL_LINK_WAIVED
    candidate.canonical_review_reasons_json = [{"code": DEFERRED_REASON, "provenance": provenance}]
    session.add(candidate)


def _link_to_canonical(
    session: Session,
    models: CleanupEntityModels,
    candidate: SubstrateRow,
    *,
    stylebook_id: int,
    canonical_id: str,
    provenance: str,
) -> None:
    link = {
        "locations": link_location_to_canonical,
        "people": link_person_to_canonical,
        "organizations": link_organization_to_canonical,
    }[models.name]
    kwargs: dict[str, Any] = {
        "stylebook_id": stylebook_id,
        models.singular: candidate,
        "target_canonical_id": canonical_id,
        "provenance": provenance,
    }
    link(session, **kwargs)


def link_candidate(
    session: Session,
    models: CleanupEntityModels,
    candidate: SubstrateRow,
    *,
    stylebook_id: int,
    canonical_id: str,
    provenance: str,
) -> str:
    """Link a pending or deferred candidate to an existing canonical; returns its id."""
    _require_open_candidate(
        models, candidate, allowed=(CANONICAL_LINK_PENDING, CANONICAL_LINK_WAIVED)
    )
    canonical = session.get(models.canonical, str(canonical_id))
    if canonical is None:
        raise CandidateCanonicalNotFoundError("That record does not exist.")
    if int(canonical.stylebook_id) != int(stylebook_id):
        raise CandidateCanonicalElsewhereError("That record is not in this Stylebook.")
    _link_to_canonical(
        session,
        models,
        candidate,
        stylebook_id=stylebook_id,
        canonical_id=str(canonical.id),
        provenance=provenance,
    )
    candidate.canonical_review_reasons_json = [
        {"code": LINKED_EXISTING_REASON, "canonical_id": str(canonical.id)}
    ]
    session.add(candidate)
    return str(canonical.id)


def create_candidate_canonical(
    session: Session,
    models: CleanupEntityModels,
    candidate: SubstrateRow,
    *,
    stylebook_id: int,
    name: str | None,
    kind: str | None,
    geometry_json: dict[str, Any] | None,
    provenance: str,
) -> str:
    """Make a new canonical from a pending or deferred candidate and link it; returns its id.

    ``name`` defaults to the candidate's name. ``kind`` is the place kind, person type or
    organization type. ``geometry_json`` only applies to locations.
    """
    _require_open_candidate(
        models, candidate, allowed=(CANONICAL_LINK_PENDING, CANONICAL_LINK_WAIVED)
    )
    label = (name or candidate.name or "").strip()
    if not label:
        raise CandidateInvalidError("A name is required to create a record.")
    if models.name == "locations":
        canonical_id = _create_location(
            session,
            candidate,
            stylebook_id=stylebook_id,
            label=label,
            kind=kind,
            geometry_json=geometry_json,
            provenance=provenance,
        )
    else:
        canonical_id = _create_person_or_organization(
            session,
            models,
            candidate,
            stylebook_id=stylebook_id,
            label=label,
            kind=kind,
            provenance=provenance,
        )
    candidate.canonical_review_reasons_json = [
        {"code": LINKED_NEW_REASON, "canonical_id": canonical_id}
    ]
    session.add(candidate)
    return canonical_id


def _create_person_or_organization(
    session: Session,
    models: CleanupEntityModels,
    candidate: SubstrateRow,
    *,
    stylebook_id: int,
    label: str,
    kind: str | None,
    provenance: str,
) -> str:
    if kind is not None:
        setattr(candidate, models.kind_column, (kind or "").strip() or None)
        session.add(candidate)
        session.flush()
    materialize = materialize_person if models.name == "people" else materialize_organization
    materialize_kwargs: dict[str, Any] = {
        "stylebook_id": stylebook_id,
        models.singular: candidate,
        "label": label,
        "provenance": provenance,
    }
    materialize(session, **materialize_kwargs)
    canonical_id = str(getattr(candidate, models.substrate_canonical_column) or "")
    if not canonical_id:
        raise CandidateInvalidError("The record could not be created.")
    if kind is not None:
        canonical = session.get(models.canonical, canonical_id)
        if canonical is not None:
            setattr(canonical, models.kind_column, getattr(candidate, models.kind_column))
            session.add(canonical)
    return canonical_id


def _create_location(
    session: Session,
    loc: Any,
    *,
    stylebook_id: int,
    label: str,
    kind: str | None,
    geometry_json: dict[str, Any] | None,
    provenance: str,
) -> str:
    # Review UI often omits geometry; inherit from substrate (parity with ingest materialize).
    bind_body_geometry = isinstance(geometry_json, dict)
    if bind_body_geometry:
        gj: dict[str, Any] | None = dict(geometry_json or {})
        canon_geometry: object | None = None
    else:
        raw_gj = loc.geometry_json
        gj = dict(raw_gj) if isinstance(raw_gj, dict) else None
        canon_geometry = loc.geometry
    if kind is not None:
        lt_candidate = (kind or "").strip().lower() or None
        if lt_candidate is not None and lt_candidate not in PLACE_EXTRACT_LOCATION_TYPES:
            raise CandidateInvalidError("The place kind must be one of the supported kinds.")
        lt = lt_candidate
    else:
        lt = (loc.location_type or "").strip().lower() or None
    fa = (loc.formatted_address or "").strip() or None
    slug = allocate_unique_canonical_slug(session, stylebook_id=stylebook_id, label=label)
    geometry_type: str | None = None
    if isinstance(gj, dict):
        gt_raw = gj.get("type")
        if isinstance(gt_raw, str) and gt_raw.strip():
            geometry_type = gt_raw.strip()
    if geometry_type is None:
        geometry_type = (loc.geometry_type or "").strip() or None
    comps = place_extract_components_from_entry(loc, None)
    jur = stylebook_jurisdiction_fields_from_components(comps)
    dfields = stylebook_district_fields_from_components(comps)
    canon = StylebookLocationCanonical(
        stylebook_id=stylebook_id,
        label=label,
        slug=slug,
        location_type=lt,
        formatted_address=fa,
        primary_substrate_location_id=None,
        status="active",
        geometry_json=dict(gj) if isinstance(gj, dict) else gj,
        geometry_type=geometry_type,
        geometry=canon_geometry,
        country_code=jur["country_code"],
        subdivision_code=jur["subdivision_code"],
        city_name=jur["city_name"],
        district_kind=dfields["district_kind"],
        district_number=dfields["district_number"],
        district_key=dfields["district_key"],
    )
    session.add(canon)
    session.flush()
    # Body-supplied GeoJSON must also populate PostGIS (same as create_standalone_canonical).
    if bind_body_geometry and isinstance(gj, dict):
        try:
            assign_geojson_geometry(session, canon, gj)
        except GeometryBindError as exc:
            raise CandidateInvalidError(str(exc)) from exc
        session.flush()
    canonical_id = str(canon.id)
    loc.stylebook_location_canonical_id = canonical_id
    refresh_aliases_for_linked_location(
        session, stylebook_id=stylebook_id, location=loc, provenance=provenance
    )
    loc.canonical_link_status = CANONICAL_LINK_LINKED
    record_canonical_created(
        session,
        stylebook_id=stylebook_id,
        entity_type="location",
        canonical_id=canonical_id,
        label=str(canon.label),
    )
    return canonical_id
