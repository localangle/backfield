"""SSRF destination policy tests."""

from __future__ import annotations

import pytest
from backfield_events.destinations import (
    WebhookDestinationError,
    display_host_for_url,
    validate_webhook_url,
)


def _validate(url: str, **kwargs):
    kwargs.setdefault("resolve_dns", False)
    kwargs.setdefault("allow_private", False)
    return validate_webhook_url(url, **kwargs)


def test_https_url_accepted_without_dns() -> None:
    destination = _validate("https://example.com/hooks/backfield")
    assert destination.host == "example.com"


def test_http_rejected_unless_private_allowed() -> None:
    with pytest.raises(WebhookDestinationError):
        _validate("http://example.com/hooks")
    assert _validate("http://localhost:9999/hooks", allow_private=True).host == "localhost"


def test_credentials_and_fragments_rejected() -> None:
    with pytest.raises(WebhookDestinationError):
        _validate("https://user:pass@example.com/hooks")
    with pytest.raises(WebhookDestinationError):
        _validate("https://example.com/hooks#fragment")


def test_unsafe_schemes_rejected() -> None:
    for url in ("ftp://example.com/x", "file:///etc/passwd", "gopher://example.com"):
        with pytest.raises(WebhookDestinationError):
            _validate(url)


@pytest.mark.parametrize(
    "host",
    [
        "127.0.0.1",
        "10.0.0.8",
        "192.168.1.1",
        "172.16.0.1",
        "169.254.169.254",  # cloud metadata service
        "224.0.0.1",  # multicast
        "0.0.0.0",
        "::1",
        "fe80::1",
    ],
)
def test_private_loopback_linklocal_metadata_literals_rejected(host: str) -> None:
    bracketed = f"[{host}]" if ":" in host else host
    with pytest.raises(WebhookDestinationError):
        _validate(f"https://{bracketed}/hooks")


def test_private_literals_allowed_in_local_dev_mode() -> None:
    destination = _validate("https://127.0.0.1:8443/hooks", allow_private=True)
    assert destination.resolved_addresses == ("127.0.0.1",)


def test_display_host_sanitizes_path_and_default_ports() -> None:
    assert display_host_for_url("https://hooks.example.com/secret/path?k=v") == (
        "hooks.example.com"
    )
    assert display_host_for_url("https://hooks.example.com:8443/x") == "hooks.example.com:8443"
    assert display_host_for_url("https://hooks.example.com:443/x") == "hooks.example.com"
