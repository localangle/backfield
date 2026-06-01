"""Pydantic schemas for PersonExtract output (Backfield consolidated ``people`` shape)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

PersonReviewHandling = Literal["none", "flag_review", "auto_defer"]


class PersonMention(BaseModel):
    text: str
    quote: bool = False


class ExtractedPerson(BaseModel):
    """One person row in consolidated ``people`` (flat ``name`` for worker ingest)."""

    name: str
    title: str | None = None
    affiliation: str | None = None
    public_figure: bool = False
    type: str | None = None
    sort_key: str | None = None
    role_in_story: str | None = None
    nature: str | None = None
    nature_secondary_tags: list[str] = Field(default_factory=list)
    mentions: list[PersonMention] = Field(default_factory=list)
    review_handling: PersonReviewHandling = "none"
    review_reason_code: str | None = None
    review_message: str | None = None
    needs_review: bool = False
