"""Article list/search response envelopes for the public API."""

from __future__ import annotations

from datetime import date
from typing import Literal

from backfield_entities.public.article_geo_search import (
    PublicArticleGeoSearchItemOut,
    PublicGeoBboxOut,
)
from backfield_entities.public.articles import (
    PublicArticleOut,
    PublicArticleSort,
    PublicSortDirection,
)
from pydantic import BaseModel, Field

from core_api.routers.public.schemas import PaginationOut


class PublicArticleSearchOut(BaseModel):
    q: str | None = None
    author: str | None = None
    external_source: str | None = None
    has_mentions: str | None = None
    pub_date_from: date | None = None
    pub_date_to: date | None = None
    sort: PublicArticleSort
    sort_direction: PublicSortDirection
    items: list[PublicArticleOut]
    pagination: PaginationOut


class PublicArticleGeoSearchOut(BaseModel):
    search_mode: Literal["point", "bbox"]
    center_lng: float | None = None
    center_lat: float | None = None
    radius_miles: float | None = None
    bbox: PublicGeoBboxOut | None = None
    location_types: list[str] = Field(default_factory=list)
    nature: str | None = None
    pub_date_from: date | None = None
    pub_date_to: date | None = None
    items: list[PublicArticleGeoSearchItemOut]
    pagination: PaginationOut
