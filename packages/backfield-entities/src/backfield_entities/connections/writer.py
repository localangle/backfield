"""Persist validated automatic connections (reinforce: one open edge, many evidence)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from backfield_db import StylebookConnection, StylebookConnectionEvidence
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from backfield_entities.catalog.resolve import resolve_stylebook_id_for_project_id
from backfield_entities.connections.dedupe import (
    connection_nature_coalesced,
    normalize_connection_description,
    normalize_connection_nature,
)
from backfield_entities.connections.evidence import (
    ConnectionCreationEvidence,
    build_connection_creation_evidence,
    evidence_row_from_creation,
    reference_time_is_newer,
)
from backfield_entities.connections.natures import (
    nature_def,
    normalize_preferred_nature_slug,
)
from backfield_entities.connections.taxonomy import AUTO_CONNECTION_PROMPT_VERSION
from backfield_entities.connections.types import AutoConnectionEdgeProposal, LinkedEntitySnapshot

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WrittenAutoConnection:
    from_entity_type: str
    from_entity_id: str
    from_display_name: str
    to_entity_type: str
    to_entity_id: str
    to_display_name: str
    description: str
    nature: str | None
    confidence: float
    reinforced: bool = False


@dataclass
class AutoConnectionWriteResult:
    created: list[WrittenAutoConnection] = field(default_factory=list)
    reinforced: list[WrittenAutoConnection] = field(default_factory=list)
    skipped_existing_count: int = 0


def _entity_maps(
    *,
    from_entities: tuple[LinkedEntitySnapshot, ...],
    to_entities: tuple[LinkedEntitySnapshot, ...],
) -> tuple[dict[str, LinkedEntitySnapshot], dict[str, LinkedEntitySnapshot]]:
    return (
        {entity.canonical_id: entity for entity in from_entities},
        {entity.canonical_id: entity for entity in to_entities},
    )


def _written(
    *,
    from_entity_type: str,
    from_entity: LinkedEntitySnapshot,
    to_entity_type: str,
    to_entity: LinkedEntitySnapshot,
    description: str,
    nature: str | None,
    confidence: float,
    reinforced: bool,
) -> WrittenAutoConnection:
    return WrittenAutoConnection(
        from_entity_type=from_entity_type,
        from_entity_id=from_entity.canonical_id,
        from_display_name=from_entity.label,
        to_entity_type=to_entity_type,
        to_entity_id=to_entity.canonical_id,
        to_display_name=to_entity.label,
        description=description,
        nature=nature,
        confidence=confidence,
        reinforced=reinforced,
    )


def _find_open_edge(
    session: Session,
    *,
    stylebook_id: int | None,
    project_id: int,
    from_entity_type: str,
    from_entity_id: str,
    to_entity_type: str,
    to_entity_id: str,
    nature: str | None,
) -> StylebookConnection | None:
    """Return one open edge for (scope, ends, nature). Prefer stylebook scope."""
    nature_key = nature or ""
    base = [
        StylebookConnection.from_entity_type == from_entity_type,
        StylebookConnection.from_entity_id == from_entity_id,
        StylebookConnection.to_entity_type == to_entity_type,
        StylebookConnection.to_entity_id == to_entity_id,
        connection_nature_coalesced() == nature_key,
        col(StylebookConnection.closed_at).is_(None),
    ]
    if stylebook_id is not None:
        rows = list(
            session.exec(
                select(StylebookConnection)
                .where(
                    StylebookConnection.stylebook_id == int(stylebook_id),
                    *base,
                )
                .order_by(col(StylebookConnection.id).asc())
            ).all()
        )
        if rows:
            return _prefer_survivor(rows)

    rows = list(
        session.exec(
            select(StylebookConnection)
            .where(
                StylebookConnection.project_id == int(project_id),
                *base,
            )
            .order_by(col(StylebookConnection.id).asc())
        ).all()
    )
    return _prefer_survivor(rows) if rows else None


def _prefer_survivor(rows: list[StylebookConnection]) -> StylebookConnection:
    """Among legacy duplicates, prefer the earliest row (stable reinforce target)."""
    return rows[0]


def _evidence_exists_for_article(
    session: Session,
    *,
    connection_id: int,
    article_id: int,
) -> bool:
    existing = session.exec(
        select(StylebookConnectionEvidence.id).where(
            StylebookConnectionEvidence.connection_id == int(connection_id),
            StylebookConnectionEvidence.article_id == int(article_id),
        )
    ).first()
    return existing is not None


def _append_evidence(
    session: Session,
    *,
    connection: StylebookConnection,
    creation: ConnectionCreationEvidence,
    description: str,
    observed_at: datetime,
) -> StylebookConnectionEvidence | None:
    """Insert evidence child, or return None when the citation already exists."""
    connection_id = int(connection.id)  # type: ignore[arg-type]
    if creation.article_id is not None and _evidence_exists_for_article(
        session, connection_id=connection_id, article_id=int(creation.article_id)
    ):
        return None

    row = evidence_row_from_creation(
        connection_id=connection_id,
        evidence=creation,
        description=description,
        observed_at=observed_at,
    )
    try:
        with session.begin_nested():
            session.add(row)
            session.flush()
    except IntegrityError:
        return None

    connection.updated_at = datetime.now(UTC)
    return row


def _apply_currentness_summary(
    connection: StylebookConnection,
    evidence: StylebookConnectionEvidence,
    *,
    is_dynamic: bool,
) -> None:
    if not is_dynamic:
        connection.currentness = "unknown"
        connection.currentness_as_of = None
        connection.currentness_evidence_id = None
        return
    if evidence.asserted_currentness not in {"current", "former"}:
        return
    if evidence.observed_at is None:
        return
    if not reference_time_is_newer(
        evidence.observed_at,
        connection.currentness_as_of,
    ):
        return
    connection.currentness = evidence.asserted_currentness
    connection.currentness_as_of = evidence.observed_at
    connection.currentness_evidence_id = int(evidence.id) if evidence.id is not None else None


def write_auto_connections(
    session: Session,
    *,
    project_id: int,
    from_entity_type: str,
    to_entity_type: str,
    from_entities: tuple[LinkedEntitySnapshot, ...],
    to_entities: tuple[LinkedEntitySnapshot, ...],
    edges: list[AutoConnectionEdgeProposal],
    article_id: int | None,
    run_id: str | None,
    processed_item_id: int | None,
    adjudication_model: str | None,
    adjudication_ai_model_config_id: str | None,
    reference_at: datetime | None = None,
) -> AutoConnectionWriteResult:
    """Create or reinforce open edges; narrative lives on evidence children."""
    from_by_id, to_by_id = _entity_maps(
        from_entities=from_entities,
        to_entities=to_entities,
    )
    result = AutoConnectionWriteResult()
    evidence_observed_at = reference_at or datetime.now(UTC)

    try:
        stylebook_id = resolve_stylebook_id_for_project_id(session, int(project_id))
    except (LookupError, ValueError):
        stylebook_id = None

    for edge in edges:
        if edge.from_entity_id == edge.to_entity_id:
            result.skipped_existing_count += 1
            continue
        nature = normalize_preferred_nature_slug(normalize_connection_nature(edge.nature))
        definition = nature_def(nature, from_entity_type, to_entity_type) if nature else None
        if (
            definition is not None
            and definition.symmetric
            and edge.to_entity_id < edge.from_entity_id
        ):
            edge = edge.model_copy(
                update={
                    "from_entity_id": edge.to_entity_id,
                    "to_entity_id": edge.from_entity_id,
                }
            )
        from_entity = from_by_id.get(edge.from_entity_id)
        to_entity = to_by_id.get(edge.to_entity_id)
        if from_entity is None or to_entity is None:
            continue

        description = normalize_connection_description(edge.description)
        if not description:
            continue

        creation = build_connection_creation_evidence(
            confidence=float(edge.confidence),
            quote=edge.quote,
            reason=edge.reason.strip() or description,
            from_entity_type=from_entity_type,
            from_entity_id=edge.from_entity_id,
            from_display_name=from_entity.label,
            to_entity_type=to_entity_type,
            to_entity_id=edge.to_entity_id,
            to_display_name=to_entity.label,
            article_id=article_id,
            run_id=run_id,
            processed_item_id=processed_item_id,
            adjudication_model=adjudication_model,
            adjudication_ai_model_config_id=(
                int(adjudication_ai_model_config_id)
                if adjudication_ai_model_config_id
                and str(adjudication_ai_model_config_id).isdigit()
                else None
            ),
            prompt_version=edge.prompt_version or AUTO_CONNECTION_PROMPT_VERSION,
            match_basis=edge.match_basis,
            asserted_currentness=edge.asserted_currentness,
            currentness_review_source=edge.currentness_review_source,
        )

        existing = _find_open_edge(
            session,
            stylebook_id=stylebook_id,
            project_id=project_id,
            from_entity_type=from_entity_type,
            from_entity_id=edge.from_entity_id,
            to_entity_type=to_entity_type,
            to_entity_id=edge.to_entity_id,
            nature=nature,
        )
        if existing is not None:
            appended = _append_evidence(
                session,
                connection=existing,
                creation=creation,
                description=description,
                observed_at=evidence_observed_at,
            )
            if appended is None:
                result.skipped_existing_count += 1
                continue
            _apply_currentness_summary(
                existing,
                appended,
                is_dynamic=definition is None or definition.temporal_kind == "dynamic",
            )
            result.reinforced.append(
                _written(
                    from_entity_type=from_entity_type,
                    from_entity=from_entity,
                    to_entity_type=to_entity_type,
                    to_entity=to_entity,
                    description=description,
                    nature=nature,
                    confidence=float(edge.confidence),
                    reinforced=True,
                )
            )
            continue

        # New open edge: identity is ends + nature; narrative on evidence only.
        row = StylebookConnection(
            project_id=int(project_id),
            stylebook_id=int(stylebook_id) if stylebook_id is not None else None,
            from_entity_type=from_entity_type,
            from_entity_id=edge.from_entity_id,
            to_entity_type=to_entity_type,
            to_entity_id=edge.to_entity_id,
            nature=nature,
        )
        try:
            with session.begin_nested():
                session.add(row)
                session.flush()
        except IntegrityError:
            # Race or legacy unique on (…, description) with null description — reinforce.
            existing = _find_open_edge(
                session,
                stylebook_id=stylebook_id,
                project_id=project_id,
                from_entity_type=from_entity_type,
                from_entity_id=edge.from_entity_id,
                to_entity_type=to_entity_type,
                to_entity_id=edge.to_entity_id,
                nature=nature,
            )
            if existing is None:
                result.skipped_existing_count += 1
                logger.info(
                    "Skipped auto-connection after integrity conflict %s:%s -> %s:%s (%s)",
                    from_entity_type,
                    edge.from_entity_id,
                    to_entity_type,
                    edge.to_entity_id,
                    nature,
                )
                continue
            appended = _append_evidence(
                session,
                connection=existing,
                creation=creation,
                description=description,
                observed_at=evidence_observed_at,
            )
            if appended is None:
                result.skipped_existing_count += 1
                continue
            _apply_currentness_summary(
                existing,
                appended,
                is_dynamic=definition is None or definition.temporal_kind == "dynamic",
            )
            result.reinforced.append(
                _written(
                    from_entity_type=from_entity_type,
                    from_entity=from_entity,
                    to_entity_type=to_entity_type,
                    to_entity=to_entity,
                    description=description,
                    nature=nature,
                    confidence=float(edge.confidence),
                    reinforced=True,
                )
            )
            continue

        evidence_row = evidence_row_from_creation(
            connection_id=int(row.id),  # type: ignore[arg-type]
            evidence=creation,
            description=description,
            observed_at=evidence_observed_at,
        )
        session.add(evidence_row)
        try:
            with session.begin_nested():
                session.flush()
        except IntegrityError:
            session.delete(row)
            result.skipped_existing_count += 1
            continue
        _apply_currentness_summary(
            row,
            evidence_row,
            is_dynamic=definition is None or definition.temporal_kind == "dynamic",
        )

        result.created.append(
            _written(
                from_entity_type=from_entity_type,
                from_entity=from_entity,
                to_entity_type=to_entity_type,
                to_entity=to_entity,
                description=description,
                nature=nature,
                confidence=float(edge.confidence),
                reinforced=False,
            )
        )

    return result
