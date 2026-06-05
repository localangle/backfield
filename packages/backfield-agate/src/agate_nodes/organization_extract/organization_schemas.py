"""Pydantic schemas for OrganizationExtract output (consolidated ``organizations`` shape)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class OrganizationMention(BaseModel):
    text: str
    quote: bool = False


class ExtractedOrganization(BaseModel):
    """One organization row in consolidated ``organizations`` (flat ``name`` for worker ingest)."""

    name: str
    type: str | None = None
    role_in_story: str | None = None
    nature: str | None = None
    nature_secondary_tags: list[str] = Field(default_factory=list)
    mentions: list[OrganizationMention] = Field(default_factory=list)
