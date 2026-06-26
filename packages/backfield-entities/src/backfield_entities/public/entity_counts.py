"""Shared count shapes for public canonical entity responses."""

from __future__ import annotations

from pydantic import BaseModel


class PublicEntityCountsOut(BaseModel):
    mentions: int = 0
    stories: int = 0
