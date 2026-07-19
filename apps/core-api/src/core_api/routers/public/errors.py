"""Structured error responses for the consumer-facing public API."""

from __future__ import annotations

from typing import Any

from backfield_auth.log_context import read_log_context
from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException

PUBLIC_PREFIX = "/public/v1"


class PublicErrorDetail(BaseModel):
    code: str
    message: str
    details: Any | None = None


class PublicErrorResponse(BaseModel):
    error: PublicErrorDetail
    request_id: str


def _request_id(request: Request) -> str:
    return read_log_context().get("request_id") or request.headers.get("x-request-id", "")


def _error_code(status_code: int) -> str:
    return {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
        429: "rate_limit_exceeded",
        422: "validation_error",
        503: "service_unavailable",
    }.get(status_code, "http_error")


def _public_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    details: Any | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    request_id = _request_id(request)
    response_headers = dict(headers or {})
    response_headers["X-Request-ID"] = request_id
    body = PublicErrorResponse(
        error=PublicErrorDetail(code=code, message=message, details=details),
        request_id=request_id,
    )
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder(body),
        headers=response_headers,
    )


async def public_http_exception_handler(
    request: Request,
    exc: HTTPException,
) -> JSONResponse:
    """Normalize HTTP errors only on the public namespace."""
    if not request.url.path.startswith(PUBLIC_PREFIX):
        return await http_exception_handler(request, exc)
    detail = exc.detail
    message = detail if isinstance(detail, str) else "Request failed."
    details = None if isinstance(detail, str) else detail
    return _public_response(
        request,
        status_code=exc.status_code,
        code=_error_code(exc.status_code),
        message=message,
        details=details,
        headers=exc.headers,
    )


async def public_validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Normalize request validation errors only on the public namespace."""
    if not request.url.path.startswith(PUBLIC_PREFIX):
        return await request_validation_exception_handler(request, exc)
    return _public_response(
        request,
        status_code=422,
        code="validation_error",
        message="Request validation failed.",
        details=exc.errors(),
    )


_REQUEST_ID_HEADER = {
    "X-Request-ID": {
        "description": "Request correlation identifier.",
        "schema": {"type": "string"},
    }
}

PUBLIC_ERROR_RESPONSES = {
    400: {
        "model": PublicErrorResponse,
        "description": "Invalid request",
        "headers": _REQUEST_ID_HEADER,
    },
    401: {
        "model": PublicErrorResponse,
        "description": "Authentication required",
        "headers": _REQUEST_ID_HEADER,
    },
    403: {
        "model": PublicErrorResponse,
        "description": "Insufficient permission",
        "headers": _REQUEST_ID_HEADER,
    },
    404: {
        "model": PublicErrorResponse,
        "description": "Resource not found",
        "headers": _REQUEST_ID_HEADER,
    },
    409: {
        "model": PublicErrorResponse,
        "description": "Request conflict",
        "headers": _REQUEST_ID_HEADER,
    },
    422: {
        "model": PublicErrorResponse,
        "description": "Request validation failed",
        "headers": _REQUEST_ID_HEADER,
    },
    429: {
        "model": PublicErrorResponse,
        "description": "Rate limit exceeded",
        "headers": {
            **_REQUEST_ID_HEADER,
            "Retry-After": {
                "description": "Seconds until a request can be retried.",
                "schema": {"type": "integer"},
            },
            "RateLimit-Limit": {"schema": {"type": "integer"}},
            "RateLimit-Remaining": {"schema": {"type": "integer"}},
            "RateLimit-Reset": {
                "description": "Seconds until the current window resets.",
                "schema": {"type": "integer"},
            },
        },
    },
    503: {
        "model": PublicErrorResponse,
        "description": "Service unavailable",
        "headers": {
            **_REQUEST_ID_HEADER,
            "Retry-After": {
                "description": "Seconds until a request can be retried.",
                "schema": {"type": "integer"},
            },
        },
    },
}
