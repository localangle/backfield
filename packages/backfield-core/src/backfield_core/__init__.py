"""Backfield Agate core: graph spec and node execution."""

from backfield_core.executor import execute_graph
from backfield_core.types import Edge, GraphSpec, NodeConfig, RunStatus

__all__ = [
    "Edge",
    "GraphSpec",
    "NodeConfig",
    "RunStatus",
    "execute_graph",
]
