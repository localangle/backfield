"""Regression tests for geocoder log sanitization."""

from __future__ import annotations

from unittest.mock import patch

from agate_utils.geocoding.pelias import _log_pelias_exception
from backfield_observability.external import sanitize_error_message


def test_sanitize_error_message_redacts_api_key() -> None:
    assert sanitize_error_message("boom api_key=secret-value") == "redacted:api_key"


def test_pelias_exception_log_omits_customer_text() -> None:
    with patch("agate_utils.geocoding.pelias.logger.error") as error:
        _log_pelias_exception(
            "search geocoding",
            RuntimeError("fail"),
            detail="text='123 Main St'",
        )
    assert error.called
    # First positional args after self are the format string + args.
    args = error.call_args.args
    rendered = args[0] % args[1:] if len(args) > 1 else str(args[0])
    assert "123 Main St" not in rendered
    assert "Pelias" in args[0]
    assert "search geocoding" in args
