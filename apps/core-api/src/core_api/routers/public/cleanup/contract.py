"""GET .../cleanup/openapi.json: the keyed cleanup contract."""

from __future__ import annotations

from typing import Any

from fastapi import Depends, Request

from core_api.routers.public.cleanup.deps import (
    CleanupContext,
    get_cleanup_context,
    require_cleanup_read,
)
from core_api.routers.public.openapi import build_cleanup_openapi


def get_cleanup_openapi(
    request: Request,
    _auth: dict = Depends(require_cleanup_read),
    _context: CleanupContext = Depends(get_cleanup_context),
) -> dict[str, Any]:
    """The cleanup operations only, for tools that generate a client from the contract."""
    return build_cleanup_openapi(request.app.openapi())
