"""Internal importer registry.

This is a minimal seam that lets us add new importers (e.g. CSV people/orgs) without
reworking routers. External API routes can stay stable while mapping to different importers.
"""

from __future__ import annotations

from typing import Any, Literal, Protocol

from fastapi import HTTPException

ImportFormat = Literal["geojson", "csv"]
ImportEntity = Literal["locations", "people", "organizations", "works"]


class Importer(Protocol):
    format: ImportFormat
    entity: ImportEntity

    def analyze(self, *, project_slug: str, payload: object, **kwargs: Any) -> object: ...

    def run(self, *, project_slug: str, payload: object, **kwargs: Any) -> object: ...


_REGISTRY: dict[tuple[ImportFormat, ImportEntity], Importer] = {}


def register_importer(importer: Importer) -> None:
    key = (importer.format, importer.entity)
    if key in _REGISTRY:
        raise RuntimeError(f"Importer already registered for {key!r}")
    _REGISTRY[key] = importer


def get_importer(fmt: ImportFormat, entity: ImportEntity) -> Importer:
    imp = _REGISTRY.get((fmt, entity))
    if imp is None:
        raise HTTPException(status_code=404, detail="Importer not found")
    return imp

