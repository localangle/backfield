"""Article ``external_source`` / ``external_id`` helpers shared by persist and repair."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from backfield_db import AgateProcessedItem, BackfieldProject, SubstrateArticle
from sqlmodel import Session, col, select

# Legacy persist key for S3 ledger-backed articles. Do not write this going forward.
S3_INGESTION_EXTERNAL_SOURCE = "backfield_s3_ingestion"
ARTICLE_TEXT_FINGERPRINT_SOURCE = "backfield_text_fingerprint"


def outlet_host_from_url(url: str | None) -> str | None:
    """Hostname used as a public outlet fallback (``www.`` stripped)."""
    if not url or not url.strip():
        return None
    hostname = urlparse(url.strip()).hostname or ""
    if not hostname:
        return None
    return hostname.removeprefix("www.") or None


def resolve_article_outlet_external_source(
    *,
    publication: str | None,
    url: str | None,
) -> str:
    """Outlet name for ``substrate_article.external_source``.

    Prefer stripped publication, then URL host, then the text-fingerprint source.
    """
    if isinstance(publication, str) and publication.strip():
        return publication.strip()
    host = outlet_host_from_url(url)
    if host:
        return host
    return ARTICLE_TEXT_FINGERPRINT_SOURCE


def _string_field(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def publication_and_url_from_payload(payload: object) -> tuple[str | None, str | None]:
    """Read top-level ``publication`` / ``url``, then one level of nested dicts."""
    if not isinstance(payload, dict):
        return None, None
    publication = _string_field(payload, "publication")
    url = _string_field(payload, "url")
    if publication or url:
        return publication, url
    for nested in payload.values():
        if not isinstance(nested, dict):
            continue
        publication = publication or _string_field(nested, "publication")
        url = url or _string_field(nested, "url")
        if publication and url:
            return publication, url
    return publication, url


def publication_and_url_from_json(raw: str | None) -> tuple[str | None, str | None]:
    if not raw or not raw.strip():
        return None, None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None, None
    return publication_and_url_from_payload(payload)


def publication_and_url_from_processed_item(
    item: AgateProcessedItem,
) -> tuple[str | None, str | None]:
    """Prefer reviewed export JSON, then graph result, then S3 input JSON."""
    for raw in (item.reviewed_output_json, item.result_json, item.input_json):
        publication, url = publication_and_url_from_json(raw)
        if publication or url:
            return publication, url
    return None, None


def article_external_identity_taken(
    session: Session,
    *,
    project_id: int,
    external_source: str,
    external_id: str,
    exclude_article_id: int | None,
) -> bool:
    stmt = select(SubstrateArticle.id).where(
        col(SubstrateArticle.project_id) == project_id,
        col(SubstrateArticle.external_source) == external_source,
        col(SubstrateArticle.external_id) == external_id,
    )
    if exclude_article_id is not None:
        stmt = stmt.where(col(SubstrateArticle.id) != exclude_article_id)
    return session.exec(stmt.limit(1)).first() is not None


def try_rewrite_article_external_identity(
    session: Session,
    article: SubstrateArticle,
    *,
    external_source: str,
    external_id: str,
) -> bool:
    """Set outlet identity when it changed and the unique key is free.

    Returns False when a colliding row already owns the target pair (caller should
    leave the existing source in place).
    """
    if article.external_source == external_source and article.external_id == external_id:
        return True
    project_id = int(article.project_id)
    article_id = int(article.id) if article.id is not None else None
    if article_external_identity_taken(
        session,
        project_id=project_id,
        external_source=external_source,
        external_id=external_id,
        exclude_article_id=article_id,
    ):
        return False
    article.external_source = external_source
    article.external_id = external_id
    return True


def _processed_item_for_article(
    session: Session,
    article: SubstrateArticle,
) -> AgateProcessedItem | None:
    if article.source_item_id is not None:
        item = session.get(AgateProcessedItem, article.source_item_id)
        if item is not None:
            return item
    ledger_id = (article.external_id or "").strip()
    if not ledger_id:
        return None
    return session.exec(
        select(AgateProcessedItem)
        .where(col(AgateProcessedItem.ingestion_ledger_id) == ledger_id)
        .order_by(col(AgateProcessedItem.id).desc())
    ).first()


@dataclass
class S3ArticleSourceRepairReport:
    scanned: int = 0
    updated: int = 0
    unchanged: int = 0
    collision_skipped: int = 0
    unresolved: int = 0
    collisions: list[dict[str, Any]] = field(default_factory=list)
    unresolved_ids: list[int] = field(default_factory=list)


def repair_s3_article_external_sources(
    session: Session,
    *,
    apply: bool = False,
    project_id: int | None = None,
    project_slug: str | None = None,
) -> S3ArticleSourceRepairReport:
    """Rewrite legacy ``backfield_s3_ingestion`` article sources to outlet names."""
    report = S3ArticleSourceRepairReport()
    stmt = select(SubstrateArticle).where(
        col(SubstrateArticle.external_source) == S3_INGESTION_EXTERNAL_SOURCE
    )
    slug = (project_slug or "").strip()
    if project_id is not None and slug:
        raise ValueError("Pass only one of project_id or project_slug.")
    if project_id is not None:
        stmt = stmt.where(col(SubstrateArticle.project_id) == project_id)
    elif slug:
        projects = list(session.exec(select(BackfieldProject).where(BackfieldProject.slug == slug)))
        if not projects:
            raise ValueError(f"No project found for slug {slug!r}.")
        if len(projects) > 1:
            raise ValueError(
                f"Slug {slug!r} matches {len(projects)} projects; pass --project-id instead."
            )
        stmt = stmt.where(col(SubstrateArticle.project_id) == int(projects[0].id))  # type: ignore[arg-type]
    stmt = stmt.order_by(col(SubstrateArticle.id).asc())
    articles = list(session.exec(stmt).all())
    report.scanned = len(articles)

    for article in articles:
        article_id = int(article.id)  # type: ignore[arg-type]
        item = _processed_item_for_article(session, article)
        publication = None
        url = article.url
        if item is not None:
            publication, item_url = publication_and_url_from_processed_item(item)
            url = item_url or url
        target_source = resolve_article_outlet_external_source(publication=publication, url=url)
        target_id = (article.external_id or "").strip()
        if not target_id:
            report.unresolved += 1
            report.unresolved_ids.append(article_id)
            continue
        if article.external_source == target_source:
            report.unchanged += 1
            continue
        if article_external_identity_taken(
            session,
            project_id=int(article.project_id),
            external_source=target_source,
            external_id=target_id,
            exclude_article_id=article_id,
        ):
            report.collision_skipped += 1
            report.collisions.append(
                {
                    "article_id": article_id,
                    "external_id": target_id,
                    "target_source": target_source,
                }
            )
            continue
        report.updated += 1
        if apply:
            article.external_source = target_source
            session.add(article)

    if apply:
        session.commit()
    return report
