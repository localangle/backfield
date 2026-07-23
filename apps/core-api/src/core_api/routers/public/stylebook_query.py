"""Shared optional Stylebook catalog slug query for public entity routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import Query

StylebookSlugQuery = Annotated[
    str | None,
    Query(
        description=(
            "Optional Stylebook catalog slug within the project's organization. "
            "Omit to use the organization's default Stylebook."
        ),
    ),
]
