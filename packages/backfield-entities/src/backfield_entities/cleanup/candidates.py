"""Candidate queue reads for keyed cleanup clients.

A candidate is a project-level record (a "substrate" row) that is not linked to a canonical yet.
The queue matches what the Stylebook UI lists: open means pending a link decision, deferred means
the editor set it aside. Queues are per project (D41); a Stylebook-wide view covers every project
assigned to the Stylebook.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from backfield_db import BackfieldProject, SubstrateArticle
from pydantic import BaseModel, Field, JsonValue
from sqlalchemy import ColumnElement, and_, exists, func, or_
from sqlmodel import Session, col, select

from backfield_entities.canonical.link import CANONICAL_LINK_PENDING, CANONICAL_LINK_WAIVED
from backfield_entities.catalog.search import substrate_name_ilike_filter
from backfield_entities.cleanup.cursor import decode_cursor, encode_cursor
from backfield_entities.cleanup.entity_models import CleanupEntityModels, SubstrateRow
from backfield_entities.cleanup.evidence import EvidenceSnippet, SnippetControls, fetch_snippets
from backfield_entities.cleanup.export import ExportFilters, mention_article_conditions
from backfield_entities.entities.linking.substrate_actions import (
    rank_canonical_suggestions_for_substrate as rank_location_matches,
)
from backfield_entities.entities.location.types import PLACE_EXTRACT_LOCATION_TYPES
from backfield_entities.entities.organization.persist import (
    rank_canonical_suggestions_for_substrate as rank_organization_matches,
)
from backfield_entities.entities.person.persist import (
    rank_canonical_suggestions_for_substrate as rank_person_matches,
)

CandidateStatus = Literal["open", "deferred"]
CANDIDATES_DEFAULT_LIMIT = 50
CANDIDATES_MAX_LIMIT = 200
MATCH_LIMIT = 24
CANONICAL_LINK_STATUS: dict[CandidateStatus, str] = {
    "open": CANONICAL_LINK_PENDING,
    "deferred": CANONICAL_LINK_WAIVED,
}


class CandidateRecommendation(BaseModel):
    """The ingest pipeline's suggested action for a candidate, when it made one."""

    suggested_action: str | None = None
    canonical_id: str | None = None
    source: str | None = None
    adjudication_confidence: float | None = None
    adjudication_rationale: str | None = None
    adjudication_model: str | None = None
    adjudication_outcome: str | None = None


class CandidateItem(BaseModel):
    id: int = Field(description="Id of the project-level record.")
    entity: str
    project_slug: str
    project_name: str
    name: str
    kind: str | None
    status: CandidateStatus
    created_at: datetime
    note: str | None = None
    recommendation: CandidateRecommendation | None = None
    review_reasons: list[dict[str, JsonValue]] = Field(
        description="Why the record needs a decision, as recorded at ingest."
    )


class CandidatePage(BaseModel):
    entity: str
    queue_scope: Literal["project", "stylebook"]
    status: CandidateStatus
    total: int
    items: list[CandidateItem]
    next_cursor: str | None = None


class CandidateProjectCount(BaseModel):
    project_slug: str
    project_name: str
    count: int


class CandidateCounts(BaseModel):
    total: int
    projects: list[CandidateProjectCount]


class CandidateTypes(BaseModel):
    types: list[str]


class CatalogMatch(BaseModel):
    canonical_id: str
    label: str
    kind: str | None
    formatted_address: str | None = None


class CandidateEvidence(BaseModel):
    candidate: CandidateItem
    snippets: list[EvidenceSnippet]
    matches: list[CatalogMatch] = Field(description="Ranked catalog matches, best first.")


class CandidatesCursor(BaseModel):
    """Position after the last row returned, in the queue's (sort value, id) order."""

    after_sort: str
    after_id: int


class CandidateNotFoundError(LookupError):
    """Raised when a candidate id is not an open or deferred candidate in the requested scope."""


def stylebook_project_ids(
    session: Session, *, stylebook_id: int, organization_id: int
) -> list[int]:
    """Projects assigned to the Stylebook, for the Stylebook-wide queue view."""
    rows = session.exec(
        select(BackfieldProject.id).where(
            BackfieldProject.organization_id == organization_id,
            BackfieldProject.stylebook_id == stylebook_id,
        )
    ).all()
    return [int(row) for row in rows if row is not None]


LIKE_ESCAPE = "\\"


def _escape_like(text: str) -> str:
    """Make `%` and `_` in a search term match themselves."""
    return (
        text.replace(LIKE_ESCAPE, LIKE_ESCAPE * 2)
        .replace("%", f"{LIKE_ESCAPE}%")
        .replace("_", f"{LIKE_ESCAPE}_")
    )


def _name_filter(models: CleanupEntityModels, q: str) -> ColumnElement[bool]:
    substrate = models.substrate
    if models.name == "locations":
        return substrate_name_ilike_filter(
            q,
            name_column=col(substrate.name),
            normalized_name_column=col(substrate.normalized_name),
        )
    term = f"%{_escape_like(q.strip())}%"
    return or_(
        col(substrate.name).ilike(term, escape=LIKE_ESCAPE),
        col(substrate.normalized_name).ilike(term, escape=LIKE_ESCAPE),
    )


def _sort_column(models: CleanupEntityModels) -> ColumnElement[str]:
    substrate = models.substrate
    if models.name == "people":
        return func.coalesce(col(substrate.sort_key), col(substrate.normalized_name))
    if models.name == "organizations":
        return func.lower(col(substrate.normalized_name))
    return col(substrate.normalized_name)


def _queue_filters(
    models: CleanupEntityModels,
    *,
    project_ids: list[int],
    status: CandidateStatus,
    q: str | None,
    kind: str | None,
    needs_review: bool | None,
    date_filters: ExportFilters,
) -> list[ColumnElement[bool]]:
    substrate = models.substrate
    link_column = models.column(substrate, models.substrate_canonical_column)
    kind_column = models.column(substrate, models.kind_column)
    filters: list[ColumnElement[bool]] = [
        col(substrate.project_id).in_(project_ids),
        col(link_column).is_(None),
        substrate.canonical_link_status == CANONICAL_LINK_STATUS[status],
    ]
    if q and q.strip():
        filters.append(_name_filter(models, q))
    if kind and kind.strip():
        filters.append(kind_column == kind.strip())
    if needs_review is True and status == "open":
        mention_substrate = models.column(models.mention, models.mention_substrate_column)
        filters.append(
            exists().where(
                mention_substrate == substrate.id,
                models.mention.deleted == False,  # noqa: E712
                models.mention.needs_review == True,  # noqa: E712
            )
        )
    if date_filters.mentioned_from is not None or date_filters.mentioned_to is not None:
        mention_substrate = models.column(models.mention, models.mention_substrate_column)
        filters.append(
            exists().where(
                mention_substrate == substrate.id,
                SubstrateArticle.id == models.mention.article_id,
                *mention_article_conditions(models, date_filters),
            )
        )
    return filters


def _review_items(raw: JsonValue) -> list[dict[str, JsonValue]]:
    if isinstance(raw, list):
        return [dict(item) for item in raw if isinstance(item, dict)]
    if isinstance(raw, dict):
        return [dict(raw)]
    return []


def _review_note(items: list[dict[str, JsonValue]]) -> str | None:
    for item in reversed(items):
        if str(item.get("code") or "") == "review_note":
            note = str(item.get("note") or "").strip()
            return note or None
    return None


def _recommendation(
    models: CleanupEntityModels, items: list[dict[str, JsonValue]]
) -> CandidateRecommendation | None:
    suggestion = next((i for i in items if i.get("code") == "canonical_suggestion"), None)
    adjudication = next((i for i in items if i.get("code") == "canonical_adjudication"), None)
    if suggestion is None and adjudication is None:
        return None
    link_key = f"stylebook_{models.singular}_canonical_id"
    rec = CandidateRecommendation()
    if suggestion is not None:
        rec.suggested_action = _text(suggestion.get("suggested_action"))
        rec.canonical_id = _text(suggestion.get(link_key))
        rec.source = _text(suggestion.get("source"))
    if adjudication is not None:
        confidence = adjudication.get("confidence")
        rec.adjudication_confidence = (
            float(confidence) if isinstance(confidence, int | float) else None
        )
        rec.adjudication_rationale = _text(adjudication.get("rationale"))
        rec.adjudication_model = _text(adjudication.get("model"))
        rec.adjudication_outcome = _text(adjudication.get("outcome"))
        rec.canonical_id = rec.canonical_id or _text(adjudication.get("canonical_id"))
        if rec.suggested_action is None:
            if rec.adjudication_outcome == "link_existing" and rec.canonical_id:
                rec.suggested_action = "link_existing"
            elif rec.adjudication_outcome == "no_high_confidence_link":
                rec.suggested_action = "materialize_new"
    return rec


def _text(value: JsonValue) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _candidate_item(
    models: CleanupEntityModels, row: SubstrateRow, project: BackfieldProject
) -> CandidateItem:
    items = _review_items(row.canonical_review_reasons_json)
    return CandidateItem(
        id=int(row.id),
        entity=models.name,
        project_slug=str(project.slug),
        project_name=str(project.name),
        name=str(row.name),
        kind=getattr(row, models.kind_column),
        status="deferred" if row.canonical_link_status == CANONICAL_LINK_WAIVED else "open",
        created_at=row.created_at,
        note=_review_note(items),
        recommendation=_recommendation(models, items),
        review_reasons=items,
    )


def _projects_by_id(session: Session, project_ids: list[int]) -> dict[int, BackfieldProject]:
    if not project_ids:
        return {}
    rows = session.exec(
        select(BackfieldProject).where(col(BackfieldProject.id).in_(project_ids))
    ).all()
    return {int(p.id): p for p in rows if p.id is not None}


def list_candidates(
    session: Session,
    models: CleanupEntityModels,
    *,
    project_ids: list[int],
    queue_scope: Literal["project", "stylebook"],
    status: CandidateStatus,
    q: str | None,
    kind: str | None,
    needs_review: bool | None,
    date_filters: ExportFilters,
    cursor: str | None,
    limit: int,
) -> CandidatePage:
    """One page of the candidate queue.

    Raises ``InvalidCursorError`` when ``cursor`` cannot be decoded.
    """
    filters = _queue_filters(
        models,
        project_ids=project_ids,
        status=status,
        q=q,
        kind=kind,
        needs_review=needs_review,
        date_filters=date_filters,
    )
    total = int(
        session.scalar(select(func.count()).select_from(models.substrate).where(*filters)) or 0
    )
    sort_value = _sort_column(models)
    page_filters = list(filters)
    if cursor:
        position = decode_cursor(cursor, CandidatesCursor)
        page_filters.append(
            or_(
                sort_value > position.after_sort,
                and_(
                    sort_value == position.after_sort,
                    col(models.substrate.id) > position.after_id,
                ),
            )
        )
    rows = session.exec(
        select(models.substrate, sort_value.label("sort_value"))
        .where(*page_filters)
        .order_by(sort_value.asc(), col(models.substrate.id).asc())
        .limit(limit + 1)
    ).all()
    has_more = len(rows) > limit
    page_rows = rows[:limit]
    projects = _projects_by_id(session, [int(row.project_id) for row, _ in page_rows])
    items = [_candidate_item(models, row, projects[int(row.project_id)]) for row, _ in page_rows]
    next_cursor = None
    if has_more:
        last_row, last_sort = page_rows[-1]
        next_cursor = encode_cursor(
            CandidatesCursor(after_sort=str(last_sort), after_id=int(last_row.id))
        )
    return CandidatePage(
        entity=models.name,
        queue_scope=queue_scope,
        status=status,
        total=total,
        items=items,
        next_cursor=next_cursor,
    )


def count_candidates(
    session: Session,
    models: CleanupEntityModels,
    *,
    project_ids: list[int],
    status: CandidateStatus,
    q: str | None,
    kind: str | None,
    needs_review: bool | None,
    date_filters: ExportFilters,
) -> CandidateCounts:
    """Queue size per project."""
    filters = _queue_filters(
        models,
        project_ids=project_ids,
        status=status,
        q=q,
        kind=kind,
        needs_review=needs_review,
        date_filters=date_filters,
    )
    rows = session.exec(
        select(models.substrate.project_id, func.count())
        .where(*filters)
        .group_by(models.substrate.project_id)
    ).all()
    counts = {int(project_id): int(count) for project_id, count in rows}
    projects = _projects_by_id(session, project_ids)
    per_project = [
        CandidateProjectCount(
            project_slug=str(project.slug),
            project_name=str(project.name),
            count=counts.get(project_id, 0),
        )
        for project_id, project in sorted(projects.items(), key=lambda p: p[1].name.lower())
    ]
    return CandidateCounts(total=sum(p.count for p in per_project), projects=per_project)


def list_candidate_kinds(
    session: Session,
    models: CleanupEntityModels,
    *,
    project_ids: list[int],
    status: CandidateStatus,
) -> CandidateTypes:
    """Kinds usable as a filter: the fixed place taxonomy, or the kinds present in the queue."""
    if models.name == "locations":
        return CandidateTypes(types=list(PLACE_EXTRACT_LOCATION_TYPES))
    filters = _queue_filters(
        models,
        project_ids=project_ids,
        status=status,
        q=None,
        kind=None,
        needs_review=None,
        date_filters=ExportFilters(),
    )
    kind_column = models.column(models.substrate, models.kind_column)
    rows = session.exec(
        select(func.distinct(kind_column)).where(
            *filters, col(kind_column).is_not(None), func.length(func.trim(kind_column)) > 0
        )
    ).all()
    return CandidateTypes(types=sorted({str(value).strip() for value in rows if value is not None}))


def _ranked_matches(
    session: Session, models: CleanupEntityModels, *, stylebook_id: int, row: SubstrateRow
) -> list[tuple[str, str]]:
    if models.name == "locations":
        return rank_location_matches(
            session, stylebook_id=stylebook_id, location=row, limit=MATCH_LIMIT
        )
    if models.name == "people":
        return rank_person_matches(
            session, stylebook_id=stylebook_id, person=row, limit=MATCH_LIMIT
        )
    return rank_organization_matches(
        session, stylebook_id=stylebook_id, organization=row, limit=MATCH_LIMIT
    )


def _catalog_matches(
    session: Session, models: CleanupEntityModels, ranked: list[tuple[str, str]]
) -> list[CatalogMatch]:
    ids = [canonical_id for canonical_id, _ in ranked]
    canonicals = (
        {
            str(row.id): row
            for row in session.exec(
                select(models.canonical).where(col(models.canonical.id).in_(ids))
            ).all()
        }
        if ids
        else {}
    )
    matches: list[CatalogMatch] = []
    for canonical_id, label in ranked:
        canonical = canonicals.get(str(canonical_id))
        matches.append(
            CatalogMatch(
                canonical_id=str(canonical_id),
                label=label,
                kind=models.canonical_kind(canonical) if canonical is not None else None,
                formatted_address=(
                    getattr(canonical, "formatted_address", None) if canonical is not None else None
                ),
            )
        )
    return matches


def get_candidate_evidence(
    session: Session,
    models: CleanupEntityModels,
    *,
    stylebook_id: int,
    project_ids: list[int],
    candidate_id: int,
    controls: SnippetControls,
) -> CandidateEvidence:
    """Article context and ranked catalog matches for one open or deferred candidate.

    Raises ``CandidateNotFoundError`` when the id is not in the queue for ``project_ids``.
    """
    row = session.get(models.substrate, candidate_id)
    if (
        row is None
        or int(row.project_id) not in project_ids
        or getattr(row, models.substrate_canonical_column) is not None
        or row.canonical_link_status not in CANONICAL_LINK_STATUS.values()
    ):
        raise CandidateNotFoundError(f"Candidate {candidate_id} not found")
    projects = _projects_by_id(session, [int(row.project_id)])
    return CandidateEvidence(
        candidate=_candidate_item(models, row, projects[int(row.project_id)]),
        snippets=fetch_snippets(
            session, models, condition=models.substrate.id == candidate_id, controls=controls
        ),
        matches=_catalog_matches(
            session,
            models,
            _ranked_matches(session, models, stylebook_id=stylebook_id, row=row),
        ),
    )
