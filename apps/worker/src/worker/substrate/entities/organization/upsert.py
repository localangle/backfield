"""Substrate organization upserts for worker persistence."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from backfield_db import SubstrateOrganization
from backfield_entities.entities.organization.types import (
    normalize_organization_type,
    organization_identity_fingerprint,
)
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from worker.substrate.common import _normalize_name, _utcnow

_ORGANIZATIONS_BUCKET_READY = "ready"


@dataclass(frozen=True)
class OrganizationUpsertResult:
    organization: SubstrateOrganization
    created: bool
    updated: bool


def _display_name_for_organization_entry(entry: dict[str, Any]) -> str:
    name = entry.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    return ""


def _optional_text(value: Any) -> str | None:
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    return None


def _organization_type_from_entry(entry: dict[str, Any]) -> str | None:
    return normalize_organization_type(_optional_text(entry.get("type")))


def _iter_organizations_entries(
    organizations: list[Any],
) -> Iterable[tuple[str, dict[str, Any]]]:
    for item in organizations:
        if isinstance(item, dict):
            yield _ORGANIZATIONS_BUCKET_READY, item


def _fetch_substrate_organization_after_unique_violation(
    session: Session,
    *,
    project_id: int,
    identity_fingerprint: str,
) -> SubstrateOrganization | None:
    return session.exec(
        select(SubstrateOrganization).where(
            SubstrateOrganization.project_id == project_id,
            SubstrateOrganization.identity_fingerprint == identity_fingerprint,
        )
    ).first()


def _apply_substrate_organization_merge(
    organization: SubstrateOrganization,
    *,
    display_name: str,
    normalized: str,
    organization_type: str | None,
    status: str,
    fingerprint: str,
    details: dict[str, Any],
) -> None:
    now = _utcnow()
    organization.name = display_name
    organization.normalized_name = normalized
    organization.organization_type = organization_type or organization.organization_type
    organization.status = status
    organization.identity_fingerprint = fingerprint
    organization.source_kind = "organization_extract"
    prev_details = (
        organization.source_details_json
        if isinstance(organization.source_details_json, dict)
        else {}
    )
    organization.source_details_json = {**prev_details, **details}
    organization.updated_at = now


def _upsert_organization(
    session: Session,
    *,
    project_id: int,
    bucket: str,
    entry: dict[str, Any],
    run_id: str,
    graph_id: str,
    update_existing: bool = True,
) -> OrganizationUpsertResult | None:
    display_name = _display_name_for_organization_entry(entry)
    normalized = _normalize_name(display_name)
    if not normalized:
        return None

    organization_type = _organization_type_from_entry(entry)
    fingerprint = organization_identity_fingerprint(
        normalized_name=normalized,
        organization_type=organization_type,
    )

    status = "provisional"
    details: dict[str, Any] = {
        "graph_id": graph_id,
        "run_id": run_id,
        "organizations_bucket": bucket,
    }
    raw_entry_id = entry.get("id") or entry.get("mention_id")
    if raw_entry_id is not None and str(raw_entry_id).strip():
        details["raw_entry_id"] = str(raw_entry_id).strip()

    organization = session.exec(
        select(SubstrateOrganization).where(
            SubstrateOrganization.project_id == project_id,
            SubstrateOrganization.identity_fingerprint == fingerprint,
        )
    ).first()

    if organization is None:
        new_organization = SubstrateOrganization(
            project_id=project_id,
            name=display_name,
            normalized_name=normalized,
            organization_type=organization_type,
            status=status,
            identity_fingerprint=fingerprint,
            source_kind="organization_extract",
            source_details_json=details,
        )
        try:
            with session.begin_nested():
                session.add(new_organization)
                session.flush()
        except IntegrityError as exc:
            organization = _fetch_substrate_organization_after_unique_violation(
                session,
                project_id=project_id,
                identity_fingerprint=fingerprint,
            )
            if organization is None:
                raise RuntimeError(
                    "substrate_organization insert collided on unique key but concurrent row "
                    "was not visible; retry the persistence step"
                ) from exc
            _apply_substrate_organization_merge(
                organization,
                display_name=display_name,
                normalized=normalized,
                organization_type=organization_type,
                status=status,
                fingerprint=fingerprint,
                details=details,
            )
            session.add(organization)
            session.flush()
        else:
            organization = new_organization
        return OrganizationUpsertResult(organization=organization, created=True, updated=False)

    if not update_existing:
        return OrganizationUpsertResult(organization=organization, created=False, updated=False)

    _apply_substrate_organization_merge(
        organization,
        display_name=display_name,
        normalized=normalized,
        organization_type=organization_type,
        status=status,
        fingerprint=fingerprint,
        details=details,
    )
    session.add(organization)
    session.flush()
    return OrganizationUpsertResult(organization=organization, created=False, updated=True)
