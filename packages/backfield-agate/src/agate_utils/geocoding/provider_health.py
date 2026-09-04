"""Run-scoped geocoder provider health counters (auth / rate-limit)."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field


@dataclass
class GeocoderProviderHealthCounters:
    """Mutable per-provider failure counters for the current geocode run."""

    auth_error: int = 0
    rate_limit: int = 0
    http_error: int = 0


@dataclass
class GeocoderHealthState:
    by_provider: dict[str, GeocoderProviderHealthCounters] = field(default_factory=dict)

    def record(self, provider: str, kind: str) -> None:
        key = (provider or "unknown").strip().lower() or "unknown"
        bucket = self.by_provider.setdefault(key, GeocoderProviderHealthCounters())
        if kind == "auth_error":
            bucket.auth_error += 1
        elif kind == "rate_limit":
            bucket.rate_limit += 1
        else:
            bucket.http_error += 1

    def snapshot(self) -> dict[str, dict[str, int]]:
        out: dict[str, dict[str, int]] = {}
        for provider, counters in sorted(self.by_provider.items()):
            if counters.auth_error or counters.rate_limit or counters.http_error:
                out[provider] = {
                    "auth_error": counters.auth_error,
                    "rate_limit": counters.rate_limit,
                    "http_error": counters.http_error,
                }
        return out


_CTX: ContextVar[GeocoderHealthState | None] = ContextVar(
    "bf_geocoder_health_ctx", default=None
)


def begin_geocoder_health_tracking() -> object:
    """Start a fresh counter bag; return a reset token for ``end_geocoder_health_tracking``."""
    return _CTX.set(GeocoderHealthState())


def end_geocoder_health_tracking(token: object) -> dict[str, dict[str, int]]:
    """Snapshot counters and restore the previous context."""
    state = _CTX.get()
    snapshot = state.snapshot() if state is not None else {}
    _CTX.reset(token)
    return snapshot


def record_geocoder_http_status(provider: str, status_code: int) -> None:
    """Record a non-success HTTP status against the active health context (if any)."""
    state = _CTX.get()
    if state is None:
        return
    if status_code in (401, 403):
        state.record(provider, "auth_error")
    elif status_code == 429:
        state.record(provider, "rate_limit")
    elif status_code >= 400:
        state.record(provider, "http_error")


def snapshot_geocoder_health() -> dict[str, dict[str, int]]:
    state = _CTX.get()
    if state is None:
        return {}
    return state.snapshot()
