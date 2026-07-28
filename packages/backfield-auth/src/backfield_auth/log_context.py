"""Request and job context for structured log fields."""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass

_request_id: ContextVar[str | None] = ContextVar("bf_request_id", default=None)
_request_client: ContextVar[str | None] = ContextVar("bf_request_client", default=None)
_run_id: ContextVar[str | None] = ContextVar("bf_run_id", default=None)
_job_id: ContextVar[str | None] = ContextVar("bf_job_id", default=None)
_item_id: ContextVar[str | None] = ContextVar("bf_item_id", default=None)


@dataclass(frozen=True)
class LogContextReset:
    tokens: tuple[tuple[ContextVar[str | None], Token], ...]


def bind_log_context(
    *,
    request_id: str | None = None,
    request_client: str | None = None,
    client: str | None = None,
    run_id: str | None = None,
    job_id: str | None = None,
    item_id: str | None = None,
) -> LogContextReset:
    """Bind correlation fields for the current request or task.

    ``client`` is accepted as a deprecated alias for ``request_client`` so older
    call sites keep working during the observability schema migration.
    """
    bound: list[tuple[ContextVar[str | None], Token]] = []
    if request_id is not None:
        bound.append((_request_id, _request_id.set(request_id)))
    resolved_request_client = request_client if request_client is not None else client
    if resolved_request_client is not None:
        bound.append((_request_client, _request_client.set(resolved_request_client)))
    if run_id is not None:
        bound.append((_run_id, _run_id.set(run_id)))
    if job_id is not None:
        bound.append((_job_id, _job_id.set(job_id)))
    if item_id is not None:
        bound.append((_item_id, _item_id.set(item_id)))
    return LogContextReset(tuple(bound))


def reset_log_context(reset: LogContextReset | None) -> None:
    if reset is None:
        return
    for var, token in reset.tokens:
        var.reset(token)


def clear_log_context() -> None:
    _request_id.set(None)
    _request_client.set(None)
    _run_id.set(None)
    _job_id.set(None)
    _item_id.set(None)


def read_log_context() -> dict[str, str]:
    fields: dict[str, str] = {}
    for key, var in (
        ("request_id", _request_id),
        ("request_client", _request_client),
        ("run_id", _run_id),
        ("job_id", _job_id),
        ("item_id", _item_id),
    ):
        value = var.get()
        if value:
            fields[key] = value
    return fields
