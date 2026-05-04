"""Guards for optional address / intersection → named-place display upgrade (consolidate)."""

from agate_nodes.geocode_agent.nodes.emit_location_line import (
    accept_address_venue_upgrade,
    accept_named_venue_upgrade,
)


def test_accept_venue_upgrade_when_venue_in_story() -> None:
    story = (
        "From March 5-29 at North Shore Center for the Performing Arts, "
        "9501 Skokie Blvd., Skokie. Tickets on sale."
    )
    upgraded = "North Shore Center for the Performing Arts, Skokie, IL"
    baseline = "9501 Skokie Blvd, Skokie, IL"
    assert accept_address_venue_upgrade(upgraded, baseline, story, "") is True


def test_accept_venue_upgrade_rejects_name_not_in_story() -> None:
    story = (
        "From March 5-29 at North Shore Center for the Performing Arts, "
        "9501 Skokie Blvd., Skokie."
    )
    upgraded = "Imaginary Playhouse, Skokie, IL"
    baseline = "9501 Skokie Blvd, Skokie, IL"
    assert accept_address_venue_upgrade(upgraded, baseline, story, "") is False


def test_accept_venue_upgrade_allows_geocode_hints() -> None:
    story = "Tickets available this spring."
    hints = "Venue is North Shore Center for the Performing Arts at the Skokie address."
    upgraded = "North Shore Center for the Performing Arts, Skokie, IL"
    baseline = "9501 Skokie Blvd, Skokie, IL"
    assert accept_address_venue_upgrade(upgraded, baseline, story, hints) is True


def test_accept_venue_upgrade_rejects_identical_to_baseline() -> None:
    line = "9501 Skokie Blvd, Skokie, IL"
    assert accept_address_venue_upgrade(line, line, "any story", "") is False


def test_accept_venue_upgrade_rejects_number_leading_head() -> None:
    story = "Meet at 9501 Skokie Blvd in Skokie."
    upgraded = "9501 Skokie Events Hall, Skokie, IL"
    baseline = "9501 Skokie Blvd, Skokie, IL"
    assert accept_address_venue_upgrade(upgraded, baseline, story, "") is False


def test_accept_named_venue_upgrade_alias_matches_primary() -> None:
    """``accept_address_venue_upgrade`` remains an alias of ``accept_named_venue_upgrade``."""
    assert accept_address_venue_upgrade is accept_named_venue_upgrade


def test_accept_venue_upgrade_intersection_baseline_venue_in_story() -> None:
    story = (
        "Police gathered outside Wrigley Field at the corner of Clark and Addison in Chicago."
    )
    upgraded = "Wrigley Field, Chicago, IL"
    baseline = "W Addison St & N Clark St, Chicago, IL"
    assert accept_named_venue_upgrade(upgraded, baseline, story, "") is True
