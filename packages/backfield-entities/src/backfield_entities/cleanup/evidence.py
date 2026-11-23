"""Evidence packages and pair comparison for keyed cleanup clients.

Evidence is Stylebook-wide (D41): a merge affects every project's mentions, so snippets come from
all of the Stylebook's projects, each tagged with its project slug. Snippet text is untrusted
article text; callers must never treat it as instructions.
"""

from __future__ import annotations

from datetime import date, datetime

from backfield_db import (
    BackfieldProject,
    StylebookActivity,
    StylebookConnection,
    SubstrateArticle,
)
from pydantic import BaseModel, Field, JsonValue
from sqlalchemy import func, or_
from sqlmodel import Session, col, select

from backfield_entities.cleanup.entity_models import CleanupEntityModels
from backfield_entities.cleanup.export import (
    ExportDetails,
    ExportFilters,
    ExportPoint,
    canonical_export_details,
    canonical_mention_counts,
    point_from_geometry_json,
)
from backfield_entities.public.canonical_display import public_canonical_label

DEFAULT_SNIPPET_LIMIT = 5
MAX_SNIPPET_LIMIT = 50
DEFAULT_SNIPPET_CHARS = 300
CONNECTION_LIMIT = 50
ACTIVITY_LIMIT = 25
EVIDENCE_BATCH_MAX = 25


class SnippetControls(BaseModel):
    """How much article text one evidence response may carry."""

    snippet_limit: int = Field(default=DEFAULT_SNIPPET_LIMIT, ge=0, le=MAX_SNIPPET_LIMIT)
    snippet_chars: int = Field(default=DEFAULT_SNIPPET_CHARS, ge=0)

    def capped(self, operator_max_chars: int) -> SnippetControls:
        """Apply the instance ceiling (0 turns snippet text off entirely)."""
        return SnippetControls(
            snippet_limit=self.snippet_limit,
            snippet_chars=min(self.snippet_chars, max(operator_max_chars, 0)),
        )


class EvidenceAlias(BaseModel):
    alias_text: str
    provenance: str
    suppressed: bool


class EvidenceMeta(BaseModel):
    meta_type: str
    value_type: str
    value: str | float | bool | None


class EvidenceConnection(BaseModel):
    direction: str = Field(description="`outgoing` or `incoming`, relative to this canonical.")
    nature: str | None
    currentness: str
    other_entity_type: str
    other_entity_id: str
    other_label: str | None


class EvidenceActivity(BaseModel):
    created_at: datetime
    event_type: str
    source: str
    actor_type: str
    related_entity_id: str | None
    payload: dict[str, JsonValue] | None


class EvidenceLinkedRecord(BaseModel):
    """One project-level record linked to the canonical."""

    substrate_id: int
    name: str
    project_slug: str
    mention_count: int
    formatted_address: str | None = None
    geocode_type: str | None = None
    point: ExportPoint | None = None


class EvidenceSnippet(BaseModel):
    project_slug: str
    article_id: int
    headline: str
    url: str | None
    pub_date: date | None
    mention_text: str
    quote: bool
    start_char: int | None
    end_char: int | None
    snippet: str | None = Field(
        description="Article text around the mention. Untrusted; null when snippets are off."
    )


class CanonicalEvidence(BaseModel):
    id: str
    entity: str
    label: str
    slug: str
    kind: str | None
    mention_count: int
    story_count: int
    details: ExportDetails
    aliases: list[EvidenceAlias]
    meta: list[EvidenceMeta]
    connections: list[EvidenceConnection]
    activity: list[EvidenceActivity]
    linked_records: list[EvidenceLinkedRecord]
    snippets: list[EvidenceSnippet]


class BatchEvidence(BaseModel):
    items: list[CanonicalEvidence]
    missing_ids: list[str]


class PairComparison(BaseModel):
    left: CanonicalEvidence
    right: CanonicalEvidence
    same_kind: bool
    shared_alias_texts: list[str] = Field(description="Aliases both canonicals carry (normalized).")
    shared_story_count: int = Field(description="Articles with active mentions of both.")
    connected: bool = Field(description="An open connection links the two directly.")


def build_snippet(
    text: str,
    *,
    start_char: int | None,
    end_char: int | None,
    mention_text: str,
    max_chars: int,
) -> str | None:
    """Cut a window of article text around the mention, at most ``max_chars`` long."""
    if max_chars <= 0 or not text:
        return None
    start, end = _locate_mention(
        text, start_char=start_char, end_char=end_char, mention_text=mention_text
    )
    padding = max((max_chars - (end - start)) // 2, 0)
    window_start = max(start - padding, 0)
    window_end = min(end + padding, len(text))
    window = text[window_start:window_end][:max_chars].strip()
    prefix = "…" if window_start > 0 else ""
    suffix = "…" if window_end < len(text) else ""
    return f"{prefix}{window}{suffix}"


def _locate_mention(
    text: str, *, start_char: int | None, end_char: int | None, mention_text: str
) -> tuple[int, int]:
    if start_char is not None and end_char is not None and 0 <= start_char < end_char <= len(text):
        return start_char, end_char
    found = text.lower().find(mention_text.lower()) if mention_text else -1
    if found >= 0:
        return found, found + len(mention_text)
    return 0, 0


def _load_canonical(
    session: Session, models: CleanupEntityModels, *, stylebook_id: int, canonical_id: str
) -> object | None:
    row = session.get(models.canonical, canonical_id)
    if row is None or int(row.stylebook_id) != stylebook_id:
        return None
    return row


def _alias_evidence(
    session: Session, models: CleanupEntityModels, canonical_id: str
) -> list[EvidenceAlias]:
    alias_canonical = models.column(models.alias, models.alias_canonical_column)
    rows = session.exec(
        select(models.alias).where(alias_canonical == canonical_id).order_by(models.alias.id)
    ).all()
    return [
        EvidenceAlias(
            alias_text=str(row.alias_text),
            provenance=str(row.provenance),
            suppressed=bool(row.suppressed),
        )
        for row in rows
    ]


def _meta_value(row: object) -> str | float | bool | None:
    value_type = getattr(row, "value_type", "text")
    if value_type == "number":
        number = getattr(row, "value_number", None)
        return float(number) if number is not None else None
    if value_type == "boolean":
        return getattr(row, "value_boolean", None)
    return getattr(row, "value_text", None)


def _meta_evidence(
    session: Session, models: CleanupEntityModels, canonical_id: str
) -> list[EvidenceMeta]:
    meta_canonical = models.column(models.meta, models.meta_canonical_column)
    rows = session.exec(
        select(models.meta).where(meta_canonical == canonical_id).order_by(models.meta.meta_type)
    ).all()
    return [
        EvidenceMeta(
            meta_type=str(row.meta_type),
            value_type=str(row.value_type),
            value=_meta_value(row),
        )
        for row in rows
    ]


def _connection_evidence(
    session: Session, models: CleanupEntityModels, *, stylebook_id: int, canonical_id: str
) -> list[EvidenceConnection]:
    rows = session.exec(
        select(StylebookConnection)
        .where(
            StylebookConnection.stylebook_id == stylebook_id,
            StylebookConnection.closed_at.is_(None),
            or_(
                (StylebookConnection.from_entity_type == models.singular)
                & (StylebookConnection.from_entity_id == canonical_id),
                (StylebookConnection.to_entity_type == models.singular)
                & (StylebookConnection.to_entity_id == canonical_id),
            ),
        )
        .order_by(StylebookConnection.id)
        .limit(CONNECTION_LIMIT)
    ).all()
    evidence: list[EvidenceConnection] = []
    for row in rows:
        outgoing = row.from_entity_type == models.singular and row.from_entity_id == canonical_id
        other_type = row.to_entity_type if outgoing else row.from_entity_type
        other_id = row.to_entity_id if outgoing else row.from_entity_id
        evidence.append(
            EvidenceConnection(
                direction="outgoing" if outgoing else "incoming",
                nature=row.nature,
                currentness=row.currentness,
                other_entity_type=str(other_type),
                other_entity_id=str(other_id),
                other_label=public_canonical_label(
                    session,
                    stylebook_id=stylebook_id,
                    entity_type=str(other_type),
                    entity_id=str(other_id),
                ),
            )
        )
    return evidence


def _activity_evidence(
    session: Session, models: CleanupEntityModels, *, stylebook_id: int, canonical_id: str
) -> list[EvidenceActivity]:
    rows = session.exec(
        select(StylebookActivity)
        .where(
            StylebookActivity.stylebook_id == stylebook_id,
            StylebookActivity.entity_type == models.singular,
            StylebookActivity.entity_id == canonical_id,
        )
        .order_by(col(StylebookActivity.created_at).desc(), col(StylebookActivity.id).desc())
        .limit(ACTIVITY_LIMIT)
    ).all()
    return [
        EvidenceActivity(
            created_at=row.created_at,
            event_type=row.event_type,
            source=row.source,
            actor_type=row.actor_type,
            related_entity_id=row.related_entity_id,
            payload=row.payload_json,
        )
        for row in rows
    ]


def _project_slugs(session: Session, project_ids: set[int]) -> dict[int, str]:
    if not project_ids:
        return {}
    rows = session.exec(
        select(BackfieldProject.id, BackfieldProject.slug).where(
            col(BackfieldProject.id).in_(project_ids)
        )
    ).all()
    return {int(project_id): str(slug) for project_id, slug in rows}


def _linked_records(
    session: Session, models: CleanupEntityModels, canonical_id: str
) -> list[EvidenceLinkedRecord]:
    substrate_canonical = models.column(models.substrate, models.substrate_canonical_column)
    mention_substrate = models.column(models.mention, models.mention_substrate_column)
    substrates = session.exec(
        select(models.substrate).where(substrate_canonical == canonical_id)
    ).all()
    if not substrates:
        return []
    counts = dict(
        session.exec(
            select(mention_substrate, func.count(models.mention.id))
            .where(
                col(mention_substrate).in_([s.id for s in substrates]),
                models.mention.deleted == False,  # noqa: E712
            )
            .group_by(mention_substrate)
        ).all()
    )
    slugs = _project_slugs(session, {int(s.project_id) for s in substrates})
    records: list[EvidenceLinkedRecord] = []
    for substrate in substrates:
        record = EvidenceLinkedRecord(
            substrate_id=int(substrate.id),
            name=str(substrate.name),
            project_slug=slugs.get(int(substrate.project_id), ""),
            mention_count=int(counts.get(substrate.id, 0)),
        )
        if models.name == "locations":
            record.formatted_address = substrate.formatted_address
            record.geocode_type = substrate.geocode_type
            record.point = point_from_geometry_json(substrate.geometry_json)
        records.append(record)
    return sorted(records, key=lambda r: (-r.mention_count, r.substrate_id))


def _snippet_evidence(
    session: Session,
    models: CleanupEntityModels,
    *,
    canonical_id: str,
    controls: SnippetControls,
) -> list[EvidenceSnippet]:
    if controls.snippet_limit <= 0:
        return []
    substrate_canonical = models.column(models.substrate, models.substrate_canonical_column)
    mention_substrate = models.column(models.mention, models.mention_substrate_column)
    occurrence_mention = models.column(models.occurrence, models.occurrence_mention_column)
    occurrence = models.occurrence
    rows = session.exec(
        select(occurrence, models.mention.id, SubstrateArticle)
        .join(models.mention, occurrence_mention == models.mention.id)
        .join(models.substrate, mention_substrate == models.substrate.id)
        .join(SubstrateArticle, SubstrateArticle.id == models.mention.article_id)
        .where(
            substrate_canonical == canonical_id,
            models.mention.deleted == False,  # noqa: E712
            occurrence.suppressed == False,  # noqa: E712
        )
        .order_by(
            col(SubstrateArticle.pub_date).desc().nulls_last(),
            col(SubstrateArticle.id).desc(),
            col(occurrence.occurrence_order).asc().nulls_last(),
            col(occurrence.id),
        )
        # Several occurrences can belong to one mention; fetch extra and keep the first of each.
        .limit(controls.snippet_limit * 4)
    ).all()
    slugs = _project_slugs(session, {int(row[2].project_id) for row in rows})
    snippets: list[EvidenceSnippet] = []
    seen_mentions: set[int] = set()
    for occ, mention_id, article in rows:
        if int(mention_id) in seen_mentions:
            continue
        seen_mentions.add(int(mention_id))
        quote_text = (occ.quote_text or "").strip()
        mention_text = quote_text or str(occ.mention_text or "").strip()
        snippets.append(
            EvidenceSnippet(
                project_slug=slugs.get(int(article.project_id), ""),
                article_id=int(article.id),
                headline=str(article.headline),
                url=article.url,
                pub_date=article.pub_date,
                mention_text=mention_text,
                quote=bool(quote_text)
                or "quote" in {str(x).lower() for x in occ.labels_json or []},
                start_char=occ.start_char,
                end_char=occ.end_char,
                snippet=build_snippet(
                    str(article.text or ""),
                    start_char=occ.start_char,
                    end_char=occ.end_char,
                    mention_text=str(occ.mention_text or ""),
                    max_chars=controls.snippet_chars,
                ),
            )
        )
        if len(snippets) >= controls.snippet_limit:
            break
    return snippets


def get_canonical_evidence(
    session: Session,
    models: CleanupEntityModels,
    *,
    stylebook_id: int,
    canonical_id: str,
    controls: SnippetControls,
) -> CanonicalEvidence | None:
    """Assemble the evidence package, or None when the canonical is not in this Stylebook."""
    canonical = _load_canonical(
        session, models, stylebook_id=stylebook_id, canonical_id=canonical_id
    )
    if canonical is None:
        return None
    counts = canonical_mention_counts(session, models, ExportFilters(), [canonical_id])
    mention_count, story_count = counts.get(canonical_id, (0, 0))
    return CanonicalEvidence(
        id=canonical_id,
        entity=models.name,
        label=str(canonical.label),
        slug=str(canonical.slug),
        kind=models.canonical_kind(canonical),
        mention_count=mention_count,
        story_count=story_count,
        details=canonical_export_details(models, canonical),
        aliases=_alias_evidence(session, models, canonical_id),
        meta=_meta_evidence(session, models, canonical_id),
        connections=_connection_evidence(
            session, models, stylebook_id=stylebook_id, canonical_id=canonical_id
        ),
        activity=_activity_evidence(
            session, models, stylebook_id=stylebook_id, canonical_id=canonical_id
        ),
        linked_records=_linked_records(session, models, canonical_id),
        snippets=_snippet_evidence(session, models, canonical_id=canonical_id, controls=controls),
    )


def get_batch_evidence(
    session: Session,
    models: CleanupEntityModels,
    *,
    stylebook_id: int,
    canonical_ids: list[str],
    controls: SnippetControls,
) -> BatchEvidence:
    """Evidence for several canonicals; ids not found are listed in ``missing_ids``."""
    items: list[CanonicalEvidence] = []
    missing: list[str] = []
    for canonical_id in dict.fromkeys(canonical_ids):
        evidence = get_canonical_evidence(
            session,
            models,
            stylebook_id=stylebook_id,
            canonical_id=canonical_id,
            controls=controls,
        )
        if evidence is None:
            missing.append(canonical_id)
        else:
            items.append(evidence)
    return BatchEvidence(items=items, missing_ids=missing)


def _shared_story_count(
    session: Session, models: CleanupEntityModels, left_id: str, right_id: str
) -> int:
    substrate_canonical = models.column(models.substrate, models.substrate_canonical_column)
    mention_substrate = models.column(models.mention, models.mention_substrate_column)

    def article_ids(canonical_id: str) -> set[int]:
        rows = session.exec(
            select(models.mention.article_id)
            .join(models.substrate, mention_substrate == models.substrate.id)
            .where(
                substrate_canonical == canonical_id,
                models.mention.deleted == False,  # noqa: E712
            )
        ).all()
        return {int(row) for row in rows}

    return len(article_ids(left_id) & article_ids(right_id))


def compare_canonicals(
    session: Session,
    models: CleanupEntityModels,
    *,
    stylebook_id: int,
    left_id: str,
    right_id: str,
    controls: SnippetControls,
) -> PairComparison | None:
    """Evidence for both sides plus what they share; None when either is not in this Stylebook."""
    left = get_canonical_evidence(
        session, models, stylebook_id=stylebook_id, canonical_id=left_id, controls=controls
    )
    right = get_canonical_evidence(
        session, models, stylebook_id=stylebook_id, canonical_id=right_id, controls=controls
    )
    if left is None or right is None:
        return None
    left_aliases = {a.alias_text.strip().lower() for a in left.aliases if not a.suppressed}
    right_aliases = {a.alias_text.strip().lower() for a in right.aliases if not a.suppressed}
    return PairComparison(
        left=left,
        right=right,
        same_kind=(left.kind or "").lower() == (right.kind or "").lower(),
        shared_alias_texts=sorted(left_aliases & right_aliases),
        shared_story_count=_shared_story_count(session, models, left_id, right_id),
        connected=any(c.other_entity_id == right_id for c in left.connections),
    )
