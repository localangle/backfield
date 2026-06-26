"""Request and job context for structured log fields."""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass

_request_id: ContextVar[str | None] = ContextVar("bf_request_id", default=None)
_client: ContextVar[str | None] = ContextVar("bf_client", default=None)
_run_id: ContextVar[str | None] = ContextVar("bf_run_id", default=None)
_job_id: ContextVar[str | None] = ContextVar("bf_job_id", default=None)


@dataclass(frozen=True)
class LogContextReset:
    tokens: tuple[tuple[ContextVar[str | None], Token], ...]


def bind_log_context(
    *,
    request_id: str | None = None,
    client: str | None = None,
    run_id: str | None = None,
    job_id: str | None = None,
) -> LogContextReset:
    bound: list[tuple[ContextVar[str | None], Token]] = []
    if request_id is not None:
        bound.append((_request_id, _request_id.set(request_id)))
    if client is not None:
        bound.append((_client, _client.set(client)))
    if run_id is not None:
        bound.append((_run_id, _run_id.set(run_id)))
    if job_id is not None:
        bound.append((_job_id, _job_id.set(job_id)))
    return LogContextReset(tuple(bound))


def reset_log_context(reset: LogContextReset | None) -> None:
    if reset is None:
        return
    for var, token in reset.tokens:
        var.reset(token)


def clear_log_context() -> None:
    _request_id.set(None)
    _client.set(None)
    _run_id.set(None)
    _job_id.set(None)


def read_log_context() -> dict[str, str]:
    fields: dict[str, str] = {}
    for key, var in (
        ("request_id", _request_id),
        ("client", _client),
        ("run_id", _run_id),
        ("job_id", _job_id),
    ):
        value = var.get()
        if value:
            fields[key] = value
    return fields
