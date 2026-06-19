"""Shared response models for `/public/v1`."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

ItemT = TypeVar("ItemT")


class PaginationOut(BaseModel):
    limit: int = Field(ge=0)
    offset: int = Field(ge=0)
    total: int = Field(ge=0)


class PaginatedResponse(BaseModel, Generic[ItemT]):
    items: list[ItemT]
    pagination: PaginationOut
