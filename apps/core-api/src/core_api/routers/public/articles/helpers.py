"""Shared helpers for public article routes."""

from __future__ import annotations

from datetime import date

from backfield_db import BackfieldProject
from backfield_entities.public.article_hub import PublicEntityMentionType
from backfield_entities.public.article_scope import get_public_article_row
from backfield_entities.public.articles import ArticleMetaClause
from fastapi import HTTPException, status
from sqlmodel import Session


def parse_optional_date(value: str | None, *, param_name: str) -> date | None:
    if value is None or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {param_name}. Use YYYY-MM-DD.",
        ) from exc


MAX_META_CLAUSES = 25
MAX_META_CATEGORIES_PER_CLAUSE = 50

META_PARAM_DESCRIPTION = (
    "Repeatable metadata filter clause (AND across clauses). "
    "Forms: type, type:category, type:cat1|cat2 (OR within type), !type or !type:category. "
    "Repeat a type to require all listed categories. Max 25 clauses; max 50 categories per clause."
)

ALLOWED_ARTICLE_LIST_INCLUDES = frozenset({"counts"})
ALLOWED_ARTICLE_DETAIL_INCLUDES = frozenset({"counts", "text"})

INCLUDE_PARAM_DESCRIPTION = (
    "Repeatable include token for optional article extras. "
    "Supported: counts (mention and canonical entity totals, image count, "
    "custom records, embedded flag)."
)

INCLUDE_DETAIL_PARAM_DESCRIPTION = (
    "Repeatable include token for optional article extras. "
    "Supported: counts (mention and canonical entity totals, image count, "
    "custom records, embedded flag); text (full article body in addition to preview)."
)


def parse_article_includes(
    include: list[str],
    *,
    allowed: frozenset[str] = ALLOWED_ARTICLE_LIST_INCLUDES,
) -> set[str]:
    """Validate repeatable ``include`` tokens for article list/detail routes."""
    if not include:
        return set()
    tokens = {token.strip().lower() for token in include if token.strip()}
    if not tokens:
        return set()
    unknown = tokens - allowed
    if unknown:
        allowed_list = ", ".join(sorted(allowed))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Unknown include token(s): {', '.join(sorted(unknown))}. "
                f"Supported: {allowed_list}."
            ),
        )
    return tokens


def parse_meta_clauses(meta: list[str]) -> tuple[ArticleMetaClause, ...]:
    """Parse repeatable ``meta`` query tokens into metadata filter clauses."""
    if not meta:
        return ()
    if len(meta) > MAX_META_CLAUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many meta clauses. Maximum is {MAX_META_CLAUSES}.",
        )

    clauses: list[ArticleMetaClause] = []
    for raw_token in meta:
        token = raw_token.strip()
        if not token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid meta clause: empty token.",
            )
        negate = False
        if token.startswith("!"):
            negate = True
            token = token[1:].strip()
            if not token:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid meta clause: missing type after '!'.",
                )
        if ":" in token:
            meta_type, categories_raw = token.split(":", 1)
            meta_type = meta_type.strip()
            if not meta_type:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid meta clause: empty metadata type.",
                )
            if not categories_raw.strip():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid meta clause for type '{meta_type}': missing category.",
                )
            seen: set[str] = set()
            categories: list[str] = []
            for part in categories_raw.split("|"):
                category = part.strip()
                if not category:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Invalid meta clause for type '{meta_type}': empty category.",
                    )
                if category not in seen:
                    seen.add(category)
                    categories.append(category)
            if len(categories) > MAX_META_CATEGORIES_PER_CLAUSE:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Too many categories in meta clause for type '{meta_type}'. "
                        f"Maximum is {MAX_META_CATEGORIES_PER_CLAUSE}."
                    ),
                )
            clauses.append(
                ArticleMetaClause(
                    meta_type=meta_type,
                    categories=tuple(categories),
                    negate=negate,
                )
            )
        else:
            clauses.append(
                ArticleMetaClause(meta_type=token, categories=(), negate=negate)
            )
    return tuple(clauses)


def require_article(
    session: Session,
    project: BackfieldProject,
    article_id: int,
):
    article = get_public_article_row(
        session,
        project_id=int(project.id),  # type: ignore[arg-type]
        article_id=article_id,
    )
    if article is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
    return article


def parse_entity_type(value: str | None) -> PublicEntityMentionType | None:
    if value is None or not value.strip():
        return None
    normalized = value.strip().lower()
    if normalized not in ("location", "person", "organization"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid entity_type. Use location, person, or organization.",
        )
    return normalized  # type: ignore[return-value]


def parse_has_mentions(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    normalized = value.strip().lower()
    if normalized == "place":
        normalized = "location"
    if normalized not in ("location", "person", "organization"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid has_mentions. Use location, person, or organization.",
        )
    return normalized


def resolve_public_article_metadata_query_filters(
    *,
    section: str | None = None,
    meta_type: str | None = None,
    meta_category: str | None = None,
    exclude_meta_type: str | None = None,
    exclude_meta_category: str | None = None,
) -> tuple[str | None, str | None, str | None, str | None]:
    """Apply ``section`` sugar and return normalized metadata filter fields."""
    from backfield_entities.public.articles import (
        PublicArticleSearchParams,
        resolve_public_article_search_params,
    )

    resolved = resolve_public_article_search_params(
        PublicArticleSearchParams(
            section=section,
            meta_type=meta_type,
            meta_category=meta_category,
            exclude_meta_type=exclude_meta_type,
            exclude_meta_category=exclude_meta_category,
        )
    )
    return (
        resolved.meta_type,
        resolved.meta_category,
        resolved.exclude_meta_type,
        resolved.exclude_meta_category,
    )


def resolve_article_metadata_filters(
    *,
    section: str | None = None,
    meta_type: str | None = None,
    meta_category: str | None = None,
    exclude_meta_type: str | None = None,
    exclude_meta_category: str | None = None,
    meta: list[str] | None = None,
) -> tuple[str | None, str | None, str | None, str | None, tuple[ArticleMetaClause, ...]]:
    """Apply ``section`` sugar, parse ``meta`` clauses, and return normalized metadata filters."""
    (
        resolved_meta_type,
        resolved_meta_category,
        resolved_exclude_meta_type,
        resolved_exclude_meta_category,
    ) = resolve_public_article_metadata_query_filters(
        section=section,
        meta_type=meta_type,
        meta_category=meta_category,
        exclude_meta_type=exclude_meta_type,
        exclude_meta_category=exclude_meta_category,
    )
    meta_clauses = parse_meta_clauses(meta or [])
    return (
        resolved_meta_type,
        resolved_meta_category,
        resolved_exclude_meta_type,
        resolved_exclude_meta_category,
        meta_clauses,
    )


MAX_LOCATION_TYPES = 25


def parse_location_types(values: list[str]) -> tuple[str, ...]:
    """Parse repeatable ``location_type`` tokens (OR semantics)."""
    if not values:
        return ()
    seen: set[str] = set()
    out: list[str] = []
    for raw in values:
        token = raw.strip()
        if not token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid location_type: empty token.",
            )
        if token not in seen:
            seen.add(token)
            out.append(token)
    if len(out) > MAX_LOCATION_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many location_type values. Maximum is {MAX_LOCATION_TYPES}.",
        )
    return tuple(out)


def parse_bbox(value: str | None) -> tuple[float, float, float, float]:
    if value is None or not value.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="bbox is required in format min_lng,min_lat,max_lng,max_lat.",
        )
    parts = value.split(",")
    if len(parts) != 4:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="bbox must be in format min_lng,min_lat,max_lng,max_lat.",
        )
    try:
        min_lng, min_lat, max_lng, max_lat = (float(part.strip()) for part in parts)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="bbox values must be valid numbers.",
        ) from exc
    return min_lng, min_lat, max_lng, max_lat
