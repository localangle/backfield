"""Read-only report on the catalog's own invariants for one entity kind.

The report only observes: dangling references, inconsistent link states, cross-Stylebook links and
open connections on canonicals that no longer exist or are inactive. What to do about a finding is
the caller's decision.
"""

from __future__ import annotations

from typing import Any

from backfield_db import BackfieldProject, StylebookConnection
from pydantic import BaseModel, Field
from sqlalchemy import and_, exists, func, or_
from sqlmodel import Session, col, select

from backfield_entities.canonical.link import (
    CANONICAL_LINK_LINKED,
    CANONICAL_LINK_PENDING,
    CANONICAL_LINK_WAIVED,
)
from backfield_entities.cleanup.entity_models import CleanupEntityModels

SAMPLE_SIZE = 20


class IntegrityIssue(BaseModel):
    code: str
    description: str
    count: int
    sample_ids: list[str] = Field(description=f"Up to {SAMPLE_SIZE} affected row ids.")


class IntegrityCounts(BaseModel):
    canonicals: int
    active_canonicals: int
    linked_records: int
    pending_records: int
    deferred_records: int
    aliases: int
    open_connections: int


class IntegrityReport(BaseModel):
    entity: str
    healthy: bool = Field(description="True when no issue was found.")
    counts: IntegrityCounts
    issues: list[IntegrityIssue]


def _count(session: Session, statement: Any) -> int:
    return int(session.scalar(select(func.count()).select_from(statement.subquery())) or 0)


def _issue(
    session: Session, *, code: str, description: str, statement: Any
) -> IntegrityIssue | None:
    count = _count(session, statement)
    if count == 0:
        return None
    samples = session.exec(statement.limit(SAMPLE_SIZE)).all()
    return IntegrityIssue(
        code=code, description=description, count=count, sample_ids=[str(s) for s in samples]
    )


def _stylebook_project_ids(session: Session, stylebook_id: int) -> Any:
    return select(BackfieldProject.id).where(BackfieldProject.stylebook_id == stylebook_id)


def _link_state_statements(
    models: CleanupEntityModels, stylebook_id: int, project_ids: Any
) -> list[tuple[str, str, Any]]:
    substrate = models.substrate
    link = models.column(substrate, models.substrate_canonical_column)
    in_stylebook = col(substrate.project_id).in_(project_ids)
    return [
        (
            "linked_without_canonical",
            "A record is marked linked but points at no canonical.",
            select(substrate.id).where(
                in_stylebook,
                substrate.canonical_link_status == CANONICAL_LINK_LINKED,
                link.is_(None),
            ),
        ),
        (
            "canonical_without_linked_state",
            "A record points at a canonical but is not marked linked.",
            select(substrate.id).where(
                in_stylebook,
                col(link).is_not(None),
                substrate.canonical_link_status != CANONICAL_LINK_LINKED,
            ),
        ),
        (
            "dangling_canonical_reference",
            "A record points at a canonical that does not exist.",
            select(substrate.id).where(
                in_stylebook,
                col(link).is_not(None),
                ~exists().where(models.canonical.id == link),
            ),
        ),
    ]


def _cross_stylebook_statement(
    models: CleanupEntityModels, stylebook_id: int
) -> tuple[str, str, Any]:
    substrate = models.substrate
    link = models.column(substrate, models.substrate_canonical_column)
    canonical = models.canonical
    return (
        "cross_stylebook_reference",
        "A record belongs to a project in one Stylebook but links a canonical in another.",
        select(substrate.id)
        .join(canonical, canonical.id == link)
        .join(BackfieldProject, BackfieldProject.id == substrate.project_id)
        .where(
            BackfieldProject.stylebook_id != canonical.stylebook_id,
            or_(
                canonical.stylebook_id == stylebook_id,
                BackfieldProject.stylebook_id == stylebook_id,
            ),
        ),
    )


def _primary_record_statements(
    models: CleanupEntityModels, stylebook_id: int
) -> list[tuple[str, str, Any]]:
    canonical = models.canonical
    substrate = models.substrate
    primary = getattr(canonical, f"primary_substrate_{models.singular}_id")
    link = models.column(substrate, models.substrate_canonical_column)
    return [
        (
            "dangling_primary_record",
            "A canonical's primary record does not exist.",
            select(canonical.id).where(
                canonical.stylebook_id == stylebook_id,
                col(primary).is_not(None),
                ~exists().where(substrate.id == primary),
            ),
        ),
        (
            "primary_record_linked_elsewhere",
            "A canonical's primary record is not linked to that canonical.",
            select(canonical.id)
            .join(substrate, substrate.id == primary)
            .where(
                canonical.stylebook_id == stylebook_id,
                or_(link.is_(None), link != canonical.id),
            ),
        ),
    ]


def _connection_statement(models: CleanupEntityModels, stylebook_id: int) -> tuple[str, str, Any]:
    canonical = models.canonical

    def missing_or_inactive(entity_type: Any, entity_id: Any) -> Any:
        return and_(
            entity_type == models.singular,
            ~exists().where(canonical.id == entity_id, canonical.status == "active"),
        )

    return (
        "open_connection_on_missing_or_inactive_canonical",
        "An open connection touches a canonical that is missing or no longer active.",
        select(StylebookConnection.id).where(
            StylebookConnection.stylebook_id == stylebook_id,
            StylebookConnection.closed_at.is_(None),
            or_(
                missing_or_inactive(
                    StylebookConnection.from_entity_type, StylebookConnection.from_entity_id
                ),
                missing_or_inactive(
                    StylebookConnection.to_entity_type, StylebookConnection.to_entity_id
                ),
            ),
        ),
    )


def _counts(
    session: Session, models: CleanupEntityModels, stylebook_id: int, project_ids: Any
) -> IntegrityCounts:
    canonical = models.canonical
    substrate = models.substrate
    alias_canonical = models.column(models.alias, models.alias_canonical_column)

    def records(link_status: str) -> int:
        return _count(
            session,
            select(substrate.id).where(
                col(substrate.project_id).in_(project_ids),
                substrate.canonical_link_status == link_status,
            ),
        )

    return IntegrityCounts(
        canonicals=_count(
            session, select(canonical.id).where(canonical.stylebook_id == stylebook_id)
        ),
        active_canonicals=_count(
            session,
            select(canonical.id).where(
                canonical.stylebook_id == stylebook_id, canonical.status == "active"
            ),
        ),
        linked_records=records(CANONICAL_LINK_LINKED),
        pending_records=records(CANONICAL_LINK_PENDING),
        deferred_records=records(CANONICAL_LINK_WAIVED),
        aliases=_count(
            session,
            select(models.alias.id)
            .join(canonical, canonical.id == alias_canonical)
            .where(canonical.stylebook_id == stylebook_id, models.alias.suppressed == False),  # noqa: E712
        ),
        open_connections=_count(
            session,
            select(StylebookConnection.id).where(
                StylebookConnection.stylebook_id == stylebook_id,
                StylebookConnection.closed_at.is_(None),
                or_(
                    StylebookConnection.from_entity_type == models.singular,
                    StylebookConnection.to_entity_type == models.singular,
                ),
            ),
        ),
    )


def build_integrity_report(
    session: Session, models: CleanupEntityModels, *, stylebook_id: int
) -> IntegrityReport:
    """Run every invariant check for one entity kind in a Stylebook."""
    project_ids = _stylebook_project_ids(session, stylebook_id)
    checks = [
        *_link_state_statements(models, stylebook_id, project_ids),
        _cross_stylebook_statement(models, stylebook_id),
        *_primary_record_statements(models, stylebook_id),
        _connection_statement(models, stylebook_id),
    ]
    issues = [
        issue
        for code, description, statement in checks
        if (issue := _issue(session, code=code, description=description, statement=statement))
    ]
    return IntegrityReport(
        entity=models.name,
        healthy=not issues,
        counts=_counts(session, models, stylebook_id, project_ids),
        issues=issues,
    )
