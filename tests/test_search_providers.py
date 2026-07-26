"""Provider normalization tests for address discovery search."""

from __future__ import annotations

from unittest.mock import patch

from agate_utils.search import brave_place_search, brave_web_search


def test_brave_web_search_keeps_oakland_station_address_evidence() -> None:
    payload = {
        "type": "search",
        "web": {
            "results": [
                {
                    "title": "Oakland Station - 1428 105th Ave Oakland, CA 94603",
                    "url": "https://www.apartments.com/oakland-station/",
                    "description": "Oakland Station is an apartment community.",
                    "extra_snippets": [
                        "Oakland Station is located at 1428 105th Ave in Oakland, CA."
                    ],
                },
                {
                    "title": "Contact Us - Oakland Station",
                    "url": "https://www.oaklandstationapts.com/contact_us/",
                    "description": "1428 105th Avenue Oakland, CA 94603",
                    "location": {
                        "postal_address": {
                            "streetAddress": "1428 105th Avenue",
                            "addressLocality": "Oakland",
                            "addressRegion": "CA",
                            "postalCode": "94603",
                            "country": "US",
                        }
                    },
                },
            ]
        },
        "locations": {"results": []},
        "infobox": {"results": []},
    }
    with patch("agate_utils.search.brave_web_search_raw", return_value=payload):
        response = brave_web_search(
            "brave-key",
            q="Oakland Station 105th Avenue Oakland CA address",
        )

    assert response.success is True
    assert len(response.results) == 2
    evidence = "\n".join(result.snippet for result in response.results)
    assert "1428 105th Ave" in evidence
    assert "Postal address: 1428 105th Avenue, Oakland, CA, 94603, US" in evidence


def test_brave_web_search_deduplicates_mixed_result_groups() -> None:
    row = {
        "title": "Oakland Station",
        "url": "https://example.com/oakland-station",
        "description": "1428 105th Avenue, Oakland, CA 94603",
    }
    payload = {
        "web": {"results": [row]},
        "locations": {"results": [row]},
        "infobox": {"results": []},
    }
    with patch("agate_utils.search.brave_web_search_raw", return_value=payload):
        response = brave_web_search("brave-key", q="Oakland Station address")

    assert len(response.results) == 1


def test_brave_place_search_keeps_description_and_postal_address() -> None:
    payload = {
        "results": [
            {
                "title": "Oakland Station",
                "url": "https://example.com/oakland-station",
                "description": "Affordable apartment community",
                "postal_address": {
                    "displayAddress": "1428 105th Avenue, Oakland, CA 94603"
                },
            }
        ]
    }
    with patch("agate_utils.search.brave_place_search_raw", return_value=payload):
        response = brave_place_search(
            "brave-key",
            q="Oakland Station address",
            location="Oakland CA US",
        )

    assert response.success is True
    assert response.results[0].snippet == (
        "Affordable apartment community\n"
        "Postal address: 1428 105th Avenue, Oakland, CA 94603"
    )
