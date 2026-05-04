"""Optional catalog (Stylebook) scope for project-based Stylebook API routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import Query

#: Optional query: override the catalog to another org Stylebook (by stable slug).
# Default is set on the function parameter (``= None``), not inside ``Query(…)``,
# per FastAPI's Annotated rules.
StylebookSlugQuery = Annotated[
    str | None,
    Query(
        description=(
            "Optional catalog slug within the project's organization. "
            "Omit to use the workspace catalog for this project."
        ),
    ),
]
