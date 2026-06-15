"""Canonical entity read routes (people, organizations, locations)."""

from __future__ import annotations

from fastapi import APIRouter

from core_api.routers.public.entities import locations, organizations, people

router = APIRouter()

router.include_router(people.router)
router.include_router(organizations.router)
router.include_router(locations.router)

__all__ = ["router"]
