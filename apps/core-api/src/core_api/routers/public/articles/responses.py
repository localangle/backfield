"""Article list/search response envelopes for the public API."""

from __future__ import annotations

from backfield_entities.public.article_geo_search import (
    PublicArticleGeoSearchItemOut,
    PublicArticleGeoSearchQueryOut,
)
from backfield_entities.public.articles import PublicArticleOut, PublicArticleSearchQueryOut

from core_api.routers.public.schemas import PaginationOut


class PublicArticleSearchOut(PublicArticleSearchQueryOut):
    items: list[PublicArticleOut]
    pagination: PaginationOut


class PublicArticleGeoSearchOut(PublicArticleGeoSearchQueryOut):
    items: list[PublicArticleGeoSearchItemOut]
    pagination: PaginationOut
