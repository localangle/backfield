"""Merge article metadata substrate rows with review overlay patches."""

from __future__ import annotations

from typing import Any

from backfield_entities.ingest.article_metadata.processed_item import (
    build_processed_item_article_meta_rows,
    normalize_article_meta_overlay,
)
from sqlmodel import Session


def build_merged_article_meta_lane(
    session: Session | None,
    *,
    article_id: int | None,
    overlay: dict[str, Any] | None,
    output: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    return build_processed_item_article_meta_rows(
        session,
        article_id=article_id,
        overlay=overlay,
        output=output,
    )


__all__ = [
    "build_merged_article_meta_lane",
    "normalize_article_meta_overlay",
]
