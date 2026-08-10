"""Webhook destination URL validation (SSRF policy).

Pure stdlib so both the worker and Core API can enforce the same policy.
DNS is re-resolved on every call, so callers should validate immediately
before each delivery attempt.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit

from backfield_events.config import allow_private_webhook_destinations

MAX_URL_LENGTH = 2048


class WebhookDestinationError(ValueError):
    """The destination URL is not allowed by the webhook SSRF policy."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class ValidatedDestination:
    url: str
    host: str
    resolved_addresses: tuple[str, ...]


def display_host_for_url(url: str) -> str:
    """Sanitized destination host (plus non-default port) for display and logs."""
    parts = urlsplit(url.strip())
    host = parts.hostname or ""
    if parts.port and parts.port not in (80, 443):
        return f"{host}:{parts.port}"
    return host


def validate_webhook_url(
    url: str,
    *,
    allow_private: bool | None = None,
    resolve_dns: bool = True,
) -> ValidatedDestination:
    """Validate scheme, shape, and resolved addresses; raise ``WebhookDestinationError``.

    ``allow_private`` defaults to the local-development environment escape hatch and
    permits http/private addresses for controlled local receivers only.
    """
    if allow_private is None:
        allow_private = allow_private_webhook_destinations()

    cleaned = (url or "").strip()
    if not cleaned:
        raise WebhookDestinationError("Destination URL is required")
    if len(cleaned) > MAX_URL_LENGTH:
        raise WebhookDestinationError("Destination URL is too long")

    parts = urlsplit(cleaned)
    if parts.scheme not in ("https", "http"):
        raise WebhookDestinationError("Destination URL must use https")
    if parts.scheme == "http" and not allow_private:
        raise WebhookDestinationError("Destination URL must use https")
    if parts.username or parts.password:
        raise WebhookDestinationError("Destination URL must not embed credentials")
    if parts.fragment:
        raise WebhookDestinationError("Destination URL must not include a fragment")

    host = parts.hostname
    if not host:
        raise WebhookDestinationError("Destination URL must include a host")

    addresses: tuple[str, ...] = ()
    literal = _ip_literal(host)
    if literal is not None:
        _require_public_address(literal, allow_private=allow_private)
        addresses = (str(literal),)
    elif resolve_dns:
        addresses = _resolve_and_check(host, allow_private=allow_private)

    return ValidatedDestination(url=cleaned, host=host, resolved_addresses=addresses)


def _ip_literal(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None


def _resolve_and_check(host: str, *, allow_private: bool) -> tuple[str, ...]:
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except OSError as e:
        raise WebhookDestinationError("Destination host could not be resolved") from e

    resolved: list[str] = []
    for info in infos:
        raw = info[4][0]
        try:
            address = ipaddress.ip_address(raw)
        except ValueError:
            continue
        _require_public_address(address, allow_private=allow_private)
        resolved.append(str(address))
    if not resolved:
        raise WebhookDestinationError("Destination host could not be resolved")
    return tuple(dict.fromkeys(resolved))


def _require_public_address(
    address: ipaddress.IPv4Address | ipaddress.IPv6Address,
    *,
    allow_private: bool,
) -> None:
    if allow_private:
        return
    blocked = (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )
    if blocked or not address.is_global:
        raise WebhookDestinationError("Destination address is not allowed")
