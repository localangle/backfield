"""Article-level deduplication for consolidated GeocodeAgent places."""

from __future__ import annotations

from typing import Any

from agate_nodes.geocode_agent.place_dedupe import deduplicate_consolidated_places


def _empty_places() -> dict[str, Any]:
    return {
        "areas": {
            "states": [],
            "counties": [],
            "cities": [],
            "neighborhoods": [],
            "regions": [],
            "other": [],
        },
        "points": [],
        "needs_review": [],
    }


def _entry(
    name: str,
    *,
    location_type: str,
    result_id: str,
    coordinates: list[float] | None = None,
    formatted_address: str | None = None,
    mention: str,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "id": result_id,
        "formatted_address": formatted_address or name,
    }
    if coordinates is not None:
        result["geometry"] = {"type": "Point", "coordinates": coordinates}
    return {
        "id": result_id,
        "location": name,
        "type": location_type,
        "original_text": mention,
        "mentions": [{"text": mention}],
        "components": {
            "city": "Chicago",
            "state": {"name": "Illinois", "abbr": "IL"},
            "country": {"name": "United States", "abbr": "US"},
        },
        "geocode": {
            "geocode_type": "pelias_search",
            "result": result,
        },
    }


def test_deduplicates_repeated_city_with_different_resolver_ids() -> None:
    places = _empty_places()
    places["areas"]["cities"] = [
        _entry(
            "Chicago, IL",
            location_type="city",
            result_id="pelias:locality:chicago",
            mention="CHICAGO — The event opened Thursday.",
        ),
        _entry(
            "Chicago, IL",
            location_type="city",
            result_id="geocodio:city:chicago",
            mention="The pavilion is in Chicago.",
        ),
    ]

    deduplicated = deduplicate_consolidated_places(places)

    assert len(deduplicated["areas"]["cities"]) == 1
    assert deduplicated["areas"]["cities"][0]["mentions"] == [
        {"text": "CHICAGO — The event opened Thursday."},
        {"text": "The pavilion is in Chicago."},
    ]


def test_deduplicates_same_named_venue_with_nearby_address_results() -> None:
    places = _empty_places()
    places["points"] = [
        _entry(
            "Jay Pritzker Pavilion, Chicago, IL",
            location_type="place",
            result_id="pelias:venue:pavilion",
            coordinates=[-87.6216, 41.8830],
            formatted_address="201 E Randolph St, Chicago, IL 60601",
            mention="The concert returns to Jay Pritzker Pavilion.",
        ),
        _entry(
            "Jay Pritzker Pavilion, Chicago, IL",
            location_type="place",
            result_id="geocodio:201-east-randolph",
            coordinates=[-87.6220, 41.8832],
            formatted_address="201 East Randolph Street, Chicago, IL 60601",
            mention="Pritzker Pavilion hosts the final performance.",
        ),
    ]

    deduplicated = deduplicate_consolidated_places(places)

    assert len(deduplicated["points"]) == 1
    assert deduplicated["points"][0]["mentions"] == [
        {"text": "The concert returns to Jay Pritzker Pavilion."},
        {"text": "Pritzker Pavilion hosts the final performance."},
    ]


def test_keeps_same_name_at_materially_different_locations() -> None:
    places = _empty_places()
    places["points"] = [
        _entry(
            "Target, Chicago, IL",
            location_type="place",
            result_id="pelias:target:north",
            coordinates=[-87.6500, 41.9400],
            formatted_address="2112 N Clybourn Ave, Chicago, IL",
            mention="The North Side Target will close.",
        ),
        _entry(
            "Target, Chicago, IL",
            location_type="place",
            result_id="pelias:target:south",
            coordinates=[-87.6200, 41.7600],
            formatted_address="8560 S Cottage Grove Ave, Chicago, IL",
            mention="The South Side Target remains open.",
        ),
    ]

    deduplicated = deduplicate_consolidated_places(places)

    assert len(deduplicated["points"]) == 2


def test_keeps_different_colocated_places_with_shared_resolver_id() -> None:
    places = _empty_places()
    places["points"] = [
        _entry(
            "Jay Pritzker Pavilion, Chicago, IL",
            location_type="place",
            result_id="pelias:address:201-east-randolph",
            coordinates=[-87.6216, 41.8830],
            mention="The pavilion hosted a concert.",
        ),
        _entry(
            "Millennium Park, Chicago, IL",
            location_type="place",
            result_id="pelias:address:201-east-randolph",
            coordinates=[-87.6216, 41.8830],
            mention="The festival filled Millennium Park.",
        ),
    ]

    deduplicated = deduplicate_consolidated_places(places)

    assert len(deduplicated["points"]) == 2


def test_keeps_colocated_venue_and_address_with_shared_resolver_identity() -> None:
    places = _empty_places()
    places["points"] = [
        _entry(
            "Jay Pritzker Pavilion, Chicago, IL",
            location_type="place",
            result_id="pelias:address:201-east-randolph",
            coordinates=[-87.6216, 41.8830],
            formatted_address="201 E Randolph St, Chicago, IL 60601",
            mention="The concert returns to Jay Pritzker Pavilion.",
        ),
        _entry(
            "Jay Pritzker Pavilion, Chicago, IL",
            location_type="address",
            result_id="pelias:address:201-east-randolph",
            coordinates=[-87.6216, 41.8830],
            formatted_address="201 E Randolph St, Chicago, IL 60601",
            mention="The filing lists 201 E Randolph St.",
        ),
    ]

    deduplicated = deduplicate_consolidated_places(places)

    assert len(deduplicated["points"]) == 2
    assert {entry["type"] for entry in deduplicated["points"]} == {"address", "place"}


def test_prefers_resolved_row_over_matching_review_row() -> None:
    places = _empty_places()
    places["points"] = [
        _entry(
            "Jay Pritzker Pavilion, Chicago, IL",
            location_type="place",
            result_id="pelias:venue:pavilion",
            coordinates=[-87.6216, 41.8830],
            mention="The pavilion hosted a concert.",
        )
    ]
    places["needs_review"] = [
        {
            "id": "non-geocoded:jay-pritzker-pavilion",
            "location": "Jay Pritzker Pavilion, Chicago, IL",
            "type": "place",
            "original_text": "Pritzker Pavilion will host another event.",
            "mentions": [{"text": "Pritzker Pavilion will host another event."}],
            "components": {
                "city": "Chicago",
                "state": {"name": "Illinois", "abbr": "IL"},
            },
            "geocoded": False,
        }
    ]

    deduplicated = deduplicate_consolidated_places(places)

    assert len(deduplicated["points"]) == 1
    assert deduplicated["needs_review"] == []
    assert len(deduplicated["points"][0]["mentions"]) == 2
