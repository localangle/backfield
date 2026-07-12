"""Strip a URL path prefix before routing (CloudFront / reverse-proxy friendly)."""

from __future__ import annotations

import os
from collections.abc import Callable


def http_path_prefix_from_env(env_var: str = "BACKFIELD_HTTP_PATH_PREFIX") -> str:
    """Return a normalized path prefix from the environment (no trailing slash)."""
    raw = (os.getenv(env_var) or "").strip()
    if not raw or raw == "/":
        return ""
    if not raw.startswith("/"):
        raw = f"/{raw}"
    return raw.rstrip("/")


class PathPrefixMiddleware:
    """ASGI middleware that removes a fixed path prefix from HTTP requests."""

    def __init__(self, app: Callable, prefix: str) -> None:
        self.app = app
        self.prefix = prefix.rstrip("/") if prefix else ""

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and self.prefix:
            path = scope.get("path") or ""
            if path == self.prefix or path.startswith(self.prefix + "/"):
                new_path = path[len(self.prefix) :] or "/"
                scope = dict(scope)
                scope["path"] = new_path
                # Starlette also consults raw_path when present.
                scope["raw_path"] = new_path.encode("utf-8")
        await self.app(scope, receive, send)


def install_path_prefix(app, prefix: str | None = None) -> str:
    """Install PathPrefixMiddleware when a prefix is configured. Returns the prefix used."""
    resolved = prefix if prefix is not None else http_path_prefix_from_env()
    if resolved:
        # Pure ASGI middleware: add last so it runs first on the way in.
        app.add_middleware(PathPrefixMiddleware, prefix=resolved)
    return resolved
