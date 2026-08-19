"""Article + image upserts for substrate persistence."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date
from typing import Any

from backfield_db import AgateProcessedItem, SubstrateArticle, SubstrateImage
from backfield_db.text_sanitize import strip_nul_bytes
from backfield_entities.ingest.article_external_identity import (
    ARTICLE_TEXT_FINGERPRINT_SOURCE,
    S3_INGESTION_EXTERNAL_SOURCE,
    resolve_article_outlet_external_source,
    try_rewrite_article_external_identity,
)
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from worker.substrate.common import _parse_date, _sha256_hex, _utcnow

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ArticleUpsertResult:
    """Outcome of an article upsert, used for article lifecycle events."""

    article: SubstrateArticle
    created: bool
    #: True when a merge changed headline/author/date/text/url (False for creates).
    content_changed: bool


def _text_fingerprint(*, project_id: int, text_str: str) -> str:
    return _sha256_hex(json.dumps({"project_id": project_id, "text": text_str}, sort_keys=True))


def _find_existing_article(
    session: Session,
    *,
    project_id: int,
    url_str: str | None,
    external_source: str | None,
    external_id: str | None,
    text_fingerprint: str,
    legacy_external_source: str | None = None,
) -> SubstrateArticle | None:
    if external_source and external_id:
        article = session.exec(
            select(SubstrateArticle).where(
                col(SubstrateArticle.project_id) == project_id,
                col(SubstrateArticle.external_source) == external_source,
                col(SubstrateArticle.external_id) == external_id,
            )
        ).first()
        if article is not None:
            return article

    if (
        legacy_external_source
        and external_id
        and legacy_external_source != external_source
    ):
        article = session.exec(
            select(SubstrateArticle).where(
                col(SubstrateArticle.project_id) == project_id,
                col(SubstrateArticle.external_source) == legacy_external_source,
                col(SubstrateArticle.external_id) == external_id,
            )
        ).first()
        if article is not None:
            return article

    if url_str:
        article = session.exec(
            select(SubstrateArticle).where(
                col(SubstrateArticle.project_id) == project_id,
                col(SubstrateArticle.url) == url_str,
            )
        ).first()
        if article is not None:
            return article

    return session.exec(
        select(SubstrateArticle).where(
            col(SubstrateArticle.project_id) == project_id,
            col(SubstrateArticle.external_source) == ARTICLE_TEXT_FINGERPRINT_SOURCE,
            col(SubstrateArticle.external_id) == text_fingerprint,
        )
    ).first()


def _fetch_substrate_article_after_unique_violation(
    session: Session,
    *,
    project_id: int,
    url_str: str | None,
    external_source: str | None,
    external_id: str | None,
    text_fingerprint: str,
    legacy_external_source: str | None = None,
) -> SubstrateArticle | None:
    return _find_existing_article(
        session,
        project_id=project_id,
        url_str=url_str,
        external_source=external_source,
        external_id=external_id,
        text_fingerprint=text_fingerprint,
        legacy_external_source=legacy_external_source,
    )


def _apply_article_merge(
    session: Session,
    article: SubstrateArticle,
    *,
    url_str: str | None,
    headline_str: str,
    author_str: str | None,
    pub_date: date | None,
    text_str: str,
    run_id: str,
    processed_item_id: int | None = None,
    external_source: str | None = None,
    external_id: str | None = None,
) -> bool:
    """Merge incoming fields onto the existing row; True when content changed."""
    resolved_url = url_str or article.url
    content_changed = (
        article.headline != headline_str
        or article.author != author_str
        or article.pub_date != pub_date
        or article.text != text_str
        or article.url != resolved_url
    )
    now = _utcnow()
    article.headline = headline_str
    article.author = author_str
    article.pub_date = pub_date
    article.text = text_str
    article.url = resolved_url
    article.source_run_id = run_id
    if processed_item_id is not None:
        article.source_item_id = processed_item_id
    if external_source and external_id:
        rewritten = try_rewrite_article_external_identity(
            session,
            article,
            external_source=external_source,
            external_id=external_id,
        )
        if not rewritten:
            logger.warning(
                "Skipped article external_source rewrite for article_id=%s; "
                "(%s, %s) already exists in project_id=%s",
                article.id,
                external_source,
                external_id,
                article.project_id,
            )
    article.updated_at = now
    article.edited = True
    return content_changed


def _upsert_article(
    session: Session,
    *,
    project_id: int,
    consolidated: dict[str, Any],
    run_id: str,
    processed_item_id: int | None = None,
) -> ArticleUpsertResult:
    url = consolidated.get("url")
    url_str = str(url).strip() if isinstance(url, str) else None
    if url_str == "":
        url_str = None

    text = consolidated.get("text")
    if not isinstance(text, str) or not text.strip():
        text = consolidated.get("article_text")
    if not isinstance(text, str) or not text.strip():
        text = "(empty)"
    text_str = strip_nul_bytes(text if isinstance(text, str) else str(text))

    author = consolidated.get("author")
    author_str = str(author).strip() if isinstance(author, str) else None
    if author_str == "":
        author_str = None

    pub_date = _parse_date(consolidated.get("pub_date"))

    publication = consolidated.get("publication")
    publication_str = str(publication).strip() if isinstance(publication, str) else None
    if publication_str == "":
        publication_str = None

    entry_id = consolidated.get("entry_id")
    external_id = None
    if entry_id is not None and str(entry_id).strip():
        external_id = str(entry_id).strip()

    ledger_id = ""
    if processed_item_id is not None:
        processed_item = session.get(AgateProcessedItem, processed_item_id)
        ledger_id = (
            str(processed_item.ingestion_ledger_id).strip()
            if processed_item is not None and processed_item.ingestion_ledger_id
            else ""
        )
        if ledger_id:
            external_id = ledger_id

    if ledger_id:
        outlet_source = resolve_article_outlet_external_source(
            publication=publication_str,
            url=url_str,
        )
        lookup_source = outlet_source
        lookup_id = ledger_id
        legacy_source = S3_INGESTION_EXTERNAL_SOURCE
        resolved_external_source = outlet_source
        resolved_external_id = ledger_id
    else:
        lookup_source = publication_str
        lookup_id = external_id
        legacy_source = None
        resolved_external_source = publication_str or ARTICLE_TEXT_FINGERPRINT_SOURCE
        resolved_external_id = external_id or _text_fingerprint(
            project_id=project_id, text_str=text_str
        )

    text_fingerprint = _text_fingerprint(project_id=project_id, text_str=text_str)

    article = _find_existing_article(
        session,
        project_id=project_id,
        url_str=url_str,
        external_source=lookup_source,
        external_id=lookup_id,
        text_fingerprint=text_fingerprint,
        legacy_external_source=legacy_source,
    )

    headline = consolidated.get("headline")
    if isinstance(headline, str) and headline.strip():
        headline_str = headline.strip()
    elif article is not None:
        existing = (article.headline or "").strip()
        headline_str = existing if existing else "Article"
    else:
        headline_str = "Article"

    merge_kwargs: dict[str, Any] = {
        "url_str": url_str,
        "headline_str": headline_str,
        "author_str": author_str,
        "pub_date": pub_date,
        "text_str": text_str,
        "run_id": run_id,
        "processed_item_id": processed_item_id,
    }
    if ledger_id:
        merge_kwargs["external_source"] = resolved_external_source
        merge_kwargs["external_id"] = resolved_external_id

    if article is None:
        new_article = SubstrateArticle(
            project_id=project_id,
            external_source=resolved_external_source,
            external_id=resolved_external_id,
            url=url_str,
            headline=headline_str,
            author=author_str,
            pub_date=pub_date,
            text=text_str,
            source_run_id=run_id,
            source_item_id=processed_item_id,
            edited=True,
        )
        try:
            with session.begin_nested():
                session.add(new_article)
                session.flush()
        except IntegrityError as exc:
            article = _fetch_substrate_article_after_unique_violation(
                session,
                project_id=project_id,
                url_str=url_str,
                external_source=lookup_source,
                external_id=lookup_id,
                text_fingerprint=text_fingerprint,
                legacy_external_source=legacy_source,
            )
            if article is None:
                article = _fetch_substrate_article_after_unique_violation(
                    session,
                    project_id=project_id,
                    url_str=url_str,
                    external_source=resolved_external_source,
                    external_id=resolved_external_id,
                    text_fingerprint=text_fingerprint,
                    legacy_external_source=legacy_source,
                )
            if article is None:
                raise RuntimeError(
                    "substrate_article insert collided on unique key but concurrent row "
                    "was not visible; retry the persistence step"
                ) from exc
            content_changed = _apply_article_merge(session, article, **merge_kwargs)
            session.add(article)
            session.flush()
            return ArticleUpsertResult(
                article=article,
                created=False,
                content_changed=content_changed,
            )
        return ArticleUpsertResult(article=new_article, created=True, content_changed=False)

    content_changed = _apply_article_merge(session, article, **merge_kwargs)
    session.add(article)
    session.flush()
    return ArticleUpsertResult(article=article, created=False, content_changed=content_changed)


def _sync_images(session: Session, *, article_id: int, consolidated: dict[str, Any]) -> None:
    images = consolidated.get("images")
    if not isinstance(images, list):
        return

    for raw in images:
        if not isinstance(raw, dict):
            continue
        url = raw.get("url")
        if not isinstance(url, str) or not url.strip():
            continue
        url_str = url.strip()

        image_id = raw.get("id") or raw.get("image_id")
        image_id_str = str(image_id).strip() if image_id is not None else ""
        if not image_id_str:
            image_id_str = _sha256_hex(url_str)[:32]

        caption = raw.get("caption")
        caption_str = str(caption).strip() if isinstance(caption, str) else None
        if caption_str == "":
            caption_str = None

        row = session.exec(
            select(SubstrateImage).where(
                col(SubstrateImage.article_id) == article_id,
                col(SubstrateImage.image_id) == image_id_str,
            )
        ).first()
        if row is None:
            session.add(
                SubstrateImage(
                    article_id=article_id,
                    image_id=image_id_str,
                    url=url_str,
                    caption=caption_str,
                )
            )
        else:
            row.url = url_str
            row.caption = caption_str
            session.add(row)

    session.flush()
