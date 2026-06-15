"""Article + image upserts for substrate persistence."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from backfield_db import SubstrateArticle, SubstrateImage
from backfield_db.text_sanitize import strip_nul_bytes
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from worker.substrate.common import _parse_date, _sha256_hex, _utcnow


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
            col(SubstrateArticle.external_source) == "backfield_text_fingerprint",
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
) -> SubstrateArticle | None:
    return _find_existing_article(
        session,
        project_id=project_id,
        url_str=url_str,
        external_source=external_source,
        external_id=external_id,
        text_fingerprint=text_fingerprint,
    )


def _apply_article_merge(
    article: SubstrateArticle,
    *,
    url_str: str | None,
    headline_str: str,
    author_str: str | None,
    pub_date: date | None,
    text_str: str,
    run_id: str,
    processed_item_id: int | None = None,
) -> None:
    now = _utcnow()
    article.headline = headline_str
    article.author = author_str
    article.pub_date = pub_date
    article.text = text_str
    article.url = url_str or article.url
    article.source_run_id = run_id
    if processed_item_id is not None:
        article.source_item_id = processed_item_id
    article.updated_at = now
    article.edited = True


def _upsert_article(
    session: Session,
    *,
    project_id: int,
    consolidated: dict[str, Any],
    run_id: str,
    processed_item_id: int | None = None,
) -> SubstrateArticle:
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
    external_source = None
    if isinstance(publication, str) and publication.strip():
        external_source = str(publication).strip()

    entry_id = consolidated.get("entry_id")
    external_id = None
    if entry_id is not None and str(entry_id).strip():
        external_id = str(entry_id).strip()

    text_fingerprint = _text_fingerprint(project_id=project_id, text_str=text_str)
    resolved_external_source = external_source or "backfield_text_fingerprint"
    resolved_external_id = external_id or text_fingerprint

    article = _find_existing_article(
        session,
        project_id=project_id,
        url_str=url_str,
        external_source=external_source,
        external_id=external_id,
        text_fingerprint=text_fingerprint,
    )

    headline = consolidated.get("headline")
    if isinstance(headline, str) and headline.strip():
        headline_str = headline.strip()
    elif article is not None:
        existing = (article.headline or "").strip()
        headline_str = existing if existing else "Article"
    else:
        headline_str = "Article"

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
                external_source=external_source,
                external_id=external_id,
                text_fingerprint=text_fingerprint,
            )
            if article is None:
                article = _fetch_substrate_article_after_unique_violation(
                    session,
                    project_id=project_id,
                    url_str=url_str,
                    external_source=resolved_external_source,
                    external_id=resolved_external_id,
                    text_fingerprint=text_fingerprint,
                )
            if article is None:
                raise RuntimeError(
                    "substrate_article insert collided on unique key but concurrent row "
                    "was not visible; retry the persistence step"
                ) from exc
            _apply_article_merge(
                article,
                url_str=url_str,
                headline_str=headline_str,
                author_str=author_str,
                pub_date=pub_date,
                text_str=text_str,
                run_id=run_id,
                processed_item_id=processed_item_id,
            )
            session.add(article)
            session.flush()
            return article
        return new_article

    _apply_article_merge(
        article,
        url_str=url_str,
        headline_str=headline_str,
        author_str=author_str,
        pub_date=pub_date,
        text_str=text_str,
        run_id=run_id,
        processed_item_id=processed_item_id,
    )
    session.add(article)
    session.flush()
    return article


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
