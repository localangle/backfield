"""Before-state of an operation: a pre-image of every row it can touch (see the ledger design note).

Captured from the database before the operation runs, so undo (and a person with SQL) can rebuild
what was there. Rows are stored by column name; the binary geometry column is skipped because it
is rebuilt from ``geometry_json``.
"""

from __future__ import annotations

from typing import Any

from backfield_db import (
    BackfieldProject,
    StylebookConnection,
    StylebookConnectionEvidence,
)
from pydantic import BaseModel, Field, JsonValue
from pydantic_core import to_jsonable_python
from sqlalchemy import inspect as sqlalchemy_inspect
from sqlalchemy import or_
from sqlmodel import Session, col, select

from backfield_entities.cleanup.entity_models import CleanupEntityModels

BEFORE_STATE_SCHEMA_VERSION = 1
_SKIPPED_COLUMNS = frozenset({"geometry"})

RowJson = dict[str, JsonValue]


class SourceBeforeState(BaseModel):
    """The canonical a merge removes, and everything that moves off it."""

    canonical: RowJson
    aliases: list[RowJson]
    meta: list[RowJson]
    linked_records: list[tuple[int, int]] = Field(
        description="(project_id, record_id) pairs linked to the source."
    )
    connections: list[RowJson] = Field(
        description="Every connection touching the source, with its evidence ids."
    )


class TargetBeforeState(BaseModel):
    """The survivor, as it was before the merge could overwrite its geography or kind."""

    canonical: RowJson
    alias_norms: list[str]
    meta_types: list[str]


class MergeBeforeState(BaseModel):
    schema_version: int = BEFORE_STATE_SCHEMA_VERSION
    operation: str = "merge"
    entity_type: str
    source: SourceBeforeState
    target: TargetBeforeState


def row_to_json(row: object) -> RowJson:
    """Every column of a mapped row as JSON-safe values, minus binary geometry."""
    mapper = sqlalchemy_inspect(row).mapper
    values: RowJson = {}
    for attribute in mapper.column_attrs:
        if attribute.key in _SKIPPED_COLUMNS:
            continue
        values[attribute.key] = to_jsonable_python(getattr(row, attribute.key), fallback=str)
    return values


def _organization_project_ids(session: Session, organization_id: int) -> list[int]:
    rows = session.exec(
        select(BackfieldProject.id).where(BackfieldProject.organization_id == organization_id)
    ).all()
    return [int(row) for row in rows if row is not None]


def _linked_records(
    session: Session, models: CleanupEntityModels, *, project_ids: list[int], canonical_id: str
) -> list[tuple[int, int]]:
    if not project_ids:
        return []
    link = models.column(models.substrate, models.substrate_canonical_column)
    rows = session.exec(
        select(models.substrate.project_id, models.substrate.id)
        .where(col(models.substrate.project_id).in_(project_ids), link == canonical_id)
        .order_by(models.substrate.id)
    ).all()
    return [(int(project_id), int(record_id)) for project_id, record_id in rows]


def _connections_with_evidence(
    session: Session, models: CleanupEntityModels, *, stylebook_id: int, canonical_id: str
) -> list[RowJson]:
    kind = models.singular
    connections = session.exec(
        select(StylebookConnection)
        .where(
            StylebookConnection.stylebook_id == stylebook_id,
            or_(
                (StylebookConnection.from_entity_type == kind)
                & (StylebookConnection.from_entity_id == canonical_id),
                (StylebookConnection.to_entity_type == kind)
                & (StylebookConnection.to_entity_id == canonical_id),
            ),
        )
        .order_by(StylebookConnection.id)
    ).all()
    evidence_by_connection: dict[int, list[int]] = {}
    connection_ids = [int(c.id) for c in connections if c.id is not None]
    if connection_ids:
        evidence_rows = session.exec(
            select(StylebookConnectionEvidence.connection_id, StylebookConnectionEvidence.id)
            .where(col(StylebookConnectionEvidence.connection_id).in_(connection_ids))
            .order_by(StylebookConnectionEvidence.id)
        ).all()
        for connection_id, evidence_id in evidence_rows:
            evidence_by_connection.setdefault(int(connection_id), []).append(int(evidence_id))
    rows: list[RowJson] = []
    for connection in connections:
        row = row_to_json(connection)
        row["evidence_ids"] = list(evidence_by_connection.get(int(connection.id), []))
        rows.append(row)
    return rows


def _child_rows(session: Session, model: type[Any], column: Any, canonical_id: str) -> list[Any]:
    return list(session.exec(select(model).where(column == canonical_id).order_by(model.id)).all())


def capture_merge_before_state(
    session: Session,
    models: CleanupEntityModels,
    *,
    stylebook_id: int,
    organization_id: int,
    source_canonical_id: str,
    target_canonical_id: str,
) -> MergeBeforeState:
    """Pre-image of a merge. Both canonicals must exist in the Stylebook (the caller checks)."""
    source = session.get(models.canonical, source_canonical_id)
    target = session.get(models.canonical, target_canonical_id)
    if source is None or target is None:
        raise LookupError("canonical not found")
    alias_column = models.column(models.alias, models.alias_canonical_column)
    meta_column = models.column(models.meta, models.meta_canonical_column)
    project_ids = _organization_project_ids(session, organization_id)
    target_aliases = _child_rows(session, models.alias, alias_column, target_canonical_id)
    target_meta = _child_rows(session, models.meta, meta_column, target_canonical_id)
    return MergeBeforeState(
        entity_type=models.singular,
        source=SourceBeforeState(
            canonical=row_to_json(source),
            aliases=[
                row_to_json(r)
                for r in _child_rows(session, models.alias, alias_column, source_canonical_id)
            ],
            meta=[
                row_to_json(r)
                for r in _child_rows(session, models.meta, meta_column, source_canonical_id)
            ],
            linked_records=_linked_records(
                session, models, project_ids=project_ids, canonical_id=source_canonical_id
            ),
            connections=_connections_with_evidence(
                session, models, stylebook_id=stylebook_id, canonical_id=source_canonical_id
            ),
        ),
        target=TargetBeforeState(
            canonical=row_to_json(target),
            alias_norms=sorted(str(a.normalized_alias) for a in target_aliases),
            meta_types=sorted(str(m.meta_type) for m in target_meta),
        ),
    )
