from __future__ import annotations

from unittest.mock import Mock, patch

from agate_utils.locations import match_canonical_location


def test_stylebook_service_call_sends_explicit_organization_header() -> None:
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"match": None}
    with patch("agate_utils.locations.requests.get", return_value=response) as request:
        match_canonical_location(
            "Springfield",
            "http://stylebook",
            "news",
            service_token="service-secret",
            organization_id=42,
        )
    assert request.call_args.kwargs["headers"] == {
        "Authorization": "Bearer service-secret",
        "X-Backfield-Organization-ID": "42",
    }


def test_stylebook_service_call_never_uses_implicit_organization() -> None:
    with patch("agate_utils.locations.requests.get") as request:
        assert (
            match_canonical_location(
                "Springfield",
                "http://stylebook",
                "news",
                service_token="service-secret",
            )
            is None
        )
    request.assert_not_called()
