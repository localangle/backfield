"""Node metadata for Agate UI (sync script also reads filesystem)."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter

router = APIRouter(prefix="/nodes", tags=["nodes"])


def _metadata_dir() -> Path:
    import agate_nodes

    return Path(agate_nodes.__file__).resolve().parent


@router.get("/metadata")
def list_node_metadata():
    """Return all node metadata.json payloads for dynamic UI use."""
    out: list[dict] = []
    for d in sorted(_metadata_dir().iterdir()):
        if not d.is_dir():
            continue
        meta = d / "metadata.json"
        if meta.exists():
            out.append(json.loads(meta.read_text()))
    return out
