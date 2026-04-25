"""Shared helpers for Stylebook mention payloads (headline + URL)."""

from __future__ import annotations

from backfield_db import SubstrateArticle


def article_fields_for_linked_mention(article: SubstrateArticle) -> tuple[str | None, str | None]:
    """Return stripped headline and URL, or ``None`` when missing or blank."""
    headline_raw = article.headline
    if headline_raw is None:
        headline: str | None = None
    else:
        hs = str(headline_raw).strip()
        headline = hs or None
    url_raw = article.url
    if url_raw is None:
        url: str | None = None
    else:
        us = str(url_raw).strip()
        url = us or None
    return headline, url
