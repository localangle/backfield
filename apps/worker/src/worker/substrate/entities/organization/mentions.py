"""Organization mention aggregates, occurrences, and suppression for substrate persistence."""

from __future__ import annotations

from typing import Any

from backfield_db import (
    SubstrateOrganization,
    SubstrateOrganizationMention,
    SubstrateOrganizationMentionOccurrence,
)
from backfield_db.text_sanitize import strip_nul_bytes
from backfield_entities.canonical.link import (
    CANONICAL_LINK_LINKED,
    CANONICAL_LINK_PENDING,
    CANONICAL_LINK_UNLINKED,
)
from backfield_entities.catalog.resolve import resolve_stylebook_id_for_project_id
from backfield_entities.editorial_text import normalize_editorial_prose
from backfield_entities.entities.organization.persist import unlink_substrate_from_canonical
from backfield_entities.entities.organization.review import (
    boundary_review_data_json,
    parse_organization_boundary_from_entry,
)
from backfield_entities.entities.organization.types import ORGANIZATION_NATURE_VALUES
from backfield_entities.ingest.semantic_indexing.cleanup import (
    delete_semantic_documents_for_organization,
)
from sqlalchemy import func
from sqlmodel import Session, col, select

from worker.substrate.common import _WS_RE, _utcnow
from worker.substrate.entities.location.span import _find_mention_span
from worker.substrate.entities.organization.upsert import _display_name_for_organization_entry

_ORGANIZATION_EXTRACT_SOURCE_KIND = "organization_extract"


def _normalize_organization_nature(entry: dict[str, Any]) -> str | None:
    raw = entry.get("nature")
    if not isinstance(raw, str):
        return None
    s = raw.strip().lower()
    if not s:
        return None
    if s in ORGANIZATION_NATURE_VALUES:
        return s
    return "other"


def _parse_nature_secondary_tags(entry: dict[str, Any]) -> list[str]:
    raw = entry.get("nature_secondary_tags")
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        if isinstance(item, str):
            tag = _WS_RE.sub(" ", item.strip()).lower()
            if tag and tag in ORGANIZATION_NATURE_VALUES:
                out.append(tag)
    seen: set[str] = set()
    uniq: list[str] = []
    for tag in out:
        if tag not in seen:
            seen.add(tag)
            uniq.append(tag)
    return uniq


def _mention_texts_from_entry(entry: dict[str, Any]) -> list[str]:
    mentions = entry.get("mentions")
    texts: list[str] = []
    if isinstance(mentions, list):
        for item in mentions:
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            if isinstance(text, str) and text.strip():
                texts.append(text.strip())
    if texts:
        return texts
    fallback = _display_name_for_organization_entry(entry)
    return [fallback] if fallback else []


def _spans_for_entry_mentions(
    *,
    article_text: str,
    entry: dict[str, Any],
) -> list[tuple[str, tuple[int, int] | None, bool]]:
    results: list[tuple[str, tuple[int, int] | None, bool]] = []
    search_from = 0
    mentions = entry.get("mentions")
    if isinstance(mentions, list) and mentions:
        for item in mentions:
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            if not isinstance(text, str) or not text.strip():
                continue
            mention_text = text.strip()
            span = _find_mention_span(
                haystack=article_text,
                needle=mention_text,
                search_from=search_from,
            )
            is_quote = bool(item.get("quote"))
            results.append((mention_text, span, is_quote))
            if span is not None:
                search_from = max(search_from, span[1])
        return results

    for mention_text in _mention_texts_from_entry(entry):
        span = _find_mention_span(
            haystack=article_text,
            needle=mention_text,
            search_from=search_from,
        )
        results.append((mention_text, span, False))
        if span is not None:
            search_from = max(search_from, span[1])
    return results


def retire_stale_article_mentions_for_rerun(
    session: Session,
    *,
    article_id: int,
    touched_organization_ids: set[int],
) -> tuple[int, set[int]]:
    mentions = session.exec(
        select(SubstrateOrganizationMention).where(
            col(SubstrateOrganizationMention.article_id) == article_id,
            col(SubstrateOrganizationMention.deleted).is_(False),
        )
    ).all()
    retired = 0
    retired_organization_ids: set[int] = set()
    now = _utcnow()
    for mention in mentions:
        oid = int(mention.organization_id)
        if oid in touched_organization_ids:
            continue
        if mention.edited or mention.added:
            continue
        sk = str(mention.source_kind or "").strip()
        if sk and sk != _ORGANIZATION_EXTRACT_SOURCE_KIND:
            continue
        mention.deleted = True
        mention.updated_at = now
        session.add(mention)
        retired += 1
        retired_organization_ids.add(oid)
    if retired:
        session.flush()
    return retired, retired_organization_ids


def dispose_orphan_substrates_after_retired_mentions(
    session: Session,
    *,
    project_id: int,
    organization_ids: set[int],
    provenance: str = "agate_superseded_ingest",
) -> int:
    if not organization_ids:
        return 0
    disposed = 0
    for oid in organization_ids:
        remaining = int(
            session.scalar(
                select(func.count())
                .select_from(SubstrateOrganizationMention)
                .where(
                    SubstrateOrganizationMention.organization_id == int(oid),
                    SubstrateOrganizationMention.deleted == False,  # noqa: E712
                )
            )
            or 0
        )
        if remaining > 0:
            continue
        organization = session.get(SubstrateOrganization, int(oid))
        if organization is None or int(organization.project_id) != int(project_id):
            continue
        _dispose_orphan_substrate_without_requeue(
            session,
            organization=organization,
            provenance=provenance,
        )
        disposed += 1
    return disposed


def _dispose_orphan_substrate_without_requeue(
    session: Session,
    *,
    organization: SubstrateOrganization,
    provenance: str,
) -> None:
    if organization.id is None:
        raise ValueError("organization must be persisted")

    st = str(organization.canonical_link_status or "")
    if (
        st == CANONICAL_LINK_LINKED
        and organization.stylebook_organization_canonical_id is not None
    ):
        cid = organization.stylebook_organization_canonical_id
        try:
            stylebook_id = resolve_stylebook_id_for_project_id(
                session, int(organization.project_id)
            )
        except LookupError:
            stylebook_id = None
        if stylebook_id is not None:
            unlink_substrate_from_canonical(
                session,
                stylebook_id=int(stylebook_id),
                organization=organization,
                provenance=provenance,
                requeue_after_unlink=False,
            )
        else:
            organization.stylebook_organization_canonical_id = None
            organization.canonical_link_status = CANONICAL_LINK_UNLINKED
            organization.canonical_review_reasons_json = [
                {
                    "code": "removed_from_story",
                    "previous_canonical_id": str(cid),
                    "provenance": provenance,
                    "note": "stylebook_missing",
                }
            ]
            session.add(organization)
    elif (
        st == CANONICAL_LINK_PENDING
        and organization.stylebook_organization_canonical_id is not None
    ):
        organization.stylebook_organization_canonical_id = None
        session.add(organization)

    delete_semantic_documents_for_organization(
        session,
        organization_id=int(organization.id),
        project_id=int(organization.project_id),
    )
    session.delete(organization)


def _suppress_prior_system_occurrences_for_mention(
    session: Session,
    *,
    mention_id: int,
) -> None:
    rows = session.exec(
        select(SubstrateOrganizationMentionOccurrence).where(
            col(SubstrateOrganizationMentionOccurrence.organization_mention_id) == mention_id,
            col(SubstrateOrganizationMentionOccurrence.suppressed).is_(False),
            col(SubstrateOrganizationMentionOccurrence.source_kind) == "system_extraction",
        )
    ).all()
    now = _utcnow()
    for row in rows:
        row.suppressed = True
        row.updated_at = now
        session.add(row)
    session.flush()


def _upsert_mention_and_occurrence(
    session: Session,
    *,
    article_id: int,
    organization_id: int,
    article_text: str,
    entry: dict[str, Any],
    run_id: str,
    graph_id: str,
    bucket: str,
    preserve_editor_changes: bool = False,
) -> None:
    raw_role = entry.get("role_in_story")
    role_str = normalize_editorial_prose(raw_role if isinstance(raw_role, str) else None)
    raw_entry_id = entry.get("id") or entry.get("mention_id")
    mention_source_details: dict[str, Any] = {"run_id": run_id, "graph_id": graph_id}
    if raw_entry_id is not None and str(raw_entry_id).strip():
        mention_source_details["raw_entry_id"] = str(raw_entry_id).strip()

    nature_str = _normalize_organization_nature(entry)
    secondary_tags = _parse_nature_secondary_tags(entry)
    boundary = parse_organization_boundary_from_entry(entry)
    needs_review = boundary is not None
    review_data = boundary_review_data_json(boundary) if boundary is not None else None

    mention = session.exec(
        select(SubstrateOrganizationMention).where(
            col(SubstrateOrganizationMention.article_id) == article_id,
            col(SubstrateOrganizationMention.organization_id) == organization_id,
        )
    ).first()

    now = _utcnow()
    if mention is None:
        mention = SubstrateOrganizationMention(
            article_id=article_id,
            organization_id=organization_id,
            role_in_story=role_str,
            nature=nature_str,
            nature_secondary_tags_json=secondary_tags,
            needs_review=needs_review,
            review_data_json=review_data,
            source_kind=_ORGANIZATION_EXTRACT_SOURCE_KIND,
            source_details_json=mention_source_details,
            edited=False,
        )
        session.add(mention)
        session.flush()
    else:
        if preserve_editor_changes and not bool(mention.deleted) and (
            bool(mention.edited) or bool(mention.added)
        ):
            mention.source_details_json = mention_source_details
            mention.updated_at = now
            session.add(mention)
            session.flush()
            return
        mention.deleted = False
        mention.role_in_story = role_str or mention.role_in_story
        mention.nature = nature_str or mention.nature
        mention.nature_secondary_tags_json = secondary_tags
        if boundary is not None:
            mention.needs_review = True
            mention.review_data_json = review_data
        mention.source_kind = _ORGANIZATION_EXTRACT_SOURCE_KIND
        mention.source_details_json = mention_source_details
        mention.updated_at = now
        session.add(mention)
        session.flush()

    _suppress_prior_system_occurrences_for_mention(
        session,
        mention_id=int(mention.id),  # type: ignore[arg-type]
    )

    source_details = {"run_id": run_id, "graph_id": graph_id, "organizations_bucket": bucket}
    for order, (mention_text, span, is_quote) in enumerate(
        _spans_for_entry_mentions(article_text=article_text, entry=entry)
    ):
        labels: list[str] = ["quote"] if is_quote else []
        clean_text = strip_nul_bytes(mention_text)
        occurrence = SubstrateOrganizationMentionOccurrence(
            organization_mention_id=int(mention.id),  # type: ignore[arg-type]
            source_kind="system_extraction",
            source_details_json=source_details,
            mention_text=clean_text,
            quote_text=clean_text if is_quote else None,
            start_char=span[0] if span else None,
            end_char=span[1] if span else None,
            occurrence_order=order,
            labels_json=labels,
            suppressed=False,
        )
        session.add(occurrence)
    session.flush()
