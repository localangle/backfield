"""Keyword query compilation for public article search."""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.sql.elements import ColumnElement


def article_keyword_tsquery(q: str) -> ColumnElement:
    """Build a PostgreSQL ``tsquery`` from user keyword input.

    Uses ``websearch_to_tsquery`` so ``q`` supports web-style syntax:

    - ``"exact phrase"`` — adjacent tokens
    - ``term1 OR term2`` — either term
    - ``term -exclude`` — exclude articles matching ``exclude``
    - ``word1 word2`` — implicit AND (default)
    """
    return func.websearch_to_tsquery("english", q.strip())
