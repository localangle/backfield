"""Persist validated automatic connections."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from backfield_db import StylebookConnection
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from backfield_entities.connections.evidence import build_connection_creation_evidence
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
    nature: str
    confidence: float


@dataclass
class AutoConnectionWriteResult:
    created: list[WrittenAutoConnection]
    skipped_existing_count: int


def _entity_maps(
    *,
    from_type: str,
    to_type: str,
    from_entities: tuple[LinkedEntitySnapshot, ...],
    to_entities: tuple[LinkedEntitySnapshot, ...],
) -> tuple[dict[str, LinkedEntitySnapshot], dict[str, LinkedEntitySnapshot]]:
    return (
        {entity.canonical_id: entity for entity in from_entities},
        {entity.canonical_id: entity for entity in to_entities},
    )


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
) -> AutoConnectionWriteResult:
    from_by_id, to_by_id = _entity_maps(
        from_type=from_entity_type,
        to_type=to_entity_type,
        from_entities=from_entities,
        to_entities=to_entities,
    )
    created: list[WrittenAutoConnection] = []
    skipped_existing = 0

    for edge in edges:
        from_entity = from_by_id.get(edge.from_entity_id)
        to_entity = to_by_id.get(edge.to_entity_id)
        if from_entity is None or to_entity is None:
            continue

        existing = session.exec(
            select(StylebookConnection).where(
                StylebookConnection.project_id == int(project_id),
                StylebookConnection.from_entity_type == from_entity_type,
                StylebookConnection.from_entity_id == edge.from_entity_id,
                StylebookConnection.to_entity_type == to_entity_type,
                StylebookConnection.to_entity_id == edge.to_entity_id,
                StylebookConnection.nature == edge.nature.strip().lower(),
            )
        ).first()
        if existing is not None:
            skipped_existing += 1
            continue

        evidence = build_connection_creation_evidence(
            confidence=float(edge.confidence),
            quote=edge.quote,
            reason=edge.reason.strip() or edge.nature,
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
        )
        row = StylebookConnection(
            project_id=int(project_id),
            from_entity_type=from_entity_type,
            from_entity_id=edge.from_entity_id,
            to_entity_type=to_entity_type,
            to_entity_id=edge.to_entity_id,
            nature=edge.nature.strip().lower(),
            evidence_json=evidence.to_storage_dict(),
        )
        try:
            with session.begin_nested():
                session.add(row)
                session.flush()
        except IntegrityError:
            skipped_existing += 1
            logger.info(
                "Skipped duplicate auto-connection %s:%s -> %s:%s (%s)",
                from_entity_type,
                edge.from_entity_id,
                to_entity_type,
                edge.to_entity_id,
                edge.nature,
            )
            continue

        created.append(
            WrittenAutoConnection(
                from_entity_type=from_entity_type,
                from_entity_id=edge.from_entity_id,
                from_display_name=from_entity.label,
                to_entity_type=to_entity_type,
                to_entity_id=edge.to_entity_id,
                to_display_name=to_entity.label,
                nature=edge.nature.strip().lower(),
                confidence=float(edge.confidence),
            )
        )

    return AutoConnectionWriteResult(created=created, skipped_existing_count=skipped_existing)
