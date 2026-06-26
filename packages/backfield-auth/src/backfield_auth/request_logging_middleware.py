"""ASGI middleware that binds request context and emits structured access logs."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from backfield_auth.log_context import bind_log_context, clear_log_context, reset_log_context
from backfield_auth.structured_logging import log_event

logger = logging.getLogger("backfield.request")

_QUIET_PATHS = frozenset({"/health", "/healthz", "/readyz", "/version"})


class RequestLoggingMiddleware:
    """Bind ``request_id`` / ``client`` and log one JSON line per HTTP request."""

    def __init__(self, app: Any, *, service_name: str) -> None:
        self.app = app
        self.service_name = service_name

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path") or ""
        if path in _QUIET_PATHS:
            await self.app(scope, receive, send)
            return

        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        request_id = headers.get("x-request-id") or str(uuid.uuid4())
        client = headers.get("x-client-id") or _client_label(headers, scope)
        context_reset = bind_log_context(request_id=request_id, client=client)

        started = time.perf_counter()
        status_code = 500

        async def send_wrapper(message: dict[str, Any]) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                headers_out = list(message.get("headers", []))
                if not any(k.lower() == b"x-request-id" for k, _ in headers_out):
                    headers_out.append((b"x-request-id", request_id.encode("latin-1")))
                message = {**message, "headers": headers_out}
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            log_event(
                logger,
                "http_request",
                method=scope.get("method"),
                path=path,
                status_code=status_code,
                duration_ms=duration_ms,
            )
            reset_log_context(context_reset)
            clear_log_context()


def _client_label(headers: dict[str, str], scope: dict[str, Any]) -> str | None:
    user_agent = headers.get("user-agent", "").strip()
    if user_agent:
        return user_agent[:200]
    client = scope.get("client")
    if isinstance(client, (list, tuple)) and client:
        return str(client[0])
    return None
