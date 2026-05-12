"""Graph and run types for Agate."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class NodeConfig(BaseModel):
    id: str
    type: str
    params: dict[str, Any] = Field(default_factory=dict)
    position: dict[str, float] | None = None


class Edge(BaseModel):
    source: str
    target: str
    sourceHandle: str | None = None
    targetHandle: str | None = None


class GraphSpec(BaseModel):
    name: str
    nodes: list[NodeConfig]
    edges: list[Edge] = Field(default_factory=list)

    @field_validator("edges", mode="before")
    @classmethod
    def ensure_edges_list(cls, v: Any) -> list:
        if v is None:
            return []
        return v
