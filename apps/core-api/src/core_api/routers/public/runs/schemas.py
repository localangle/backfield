"""Public run response models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class PublicRunCountsOut(BaseModel):
    total: int = 0
    pending: int = 0
    running: int = 0
    succeeded: int = 0
    failed: int = 0


class PublicRunCreateIn(BaseModel):
    graph_id: str
    inputs: dict[str, object] | None = None


class PublicRunOut(BaseModel):
    run_id: str = Field(description="Agate run id (UUID).")
    status: str
    counts: PublicRunCountsOut
    created_at: datetime
    updated_at: datetime
    error_message: str | None = None
