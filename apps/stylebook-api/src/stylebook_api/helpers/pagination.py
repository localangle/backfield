"""Shared pagination helpers for stylebook-api list endpoints."""

from __future__ import annotations


def pagination_flags(*, total: int, limit: int, offset: int, page_len: int) -> tuple[bool, bool]:
    """Return ``(has_next, has_prev)`` for offset/limit pagination."""

    has_prev = offset > 0
    has_next = offset + page_len < total
    return has_next, has_prev


def empty_page_metadata(*, limit: int, offset: int) -> tuple[int, int, bool, bool]:
    """Return ``(page, per_page, has_next, has_prev)`` for an empty result page."""

    page = (offset // limit) + 1 if limit > 0 else 1
    return page, limit, False, offset > 0
