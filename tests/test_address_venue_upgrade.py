"""Guards for optional address → named-place display upgrade (geocode consolidate)."""

from agate_nodes.geocode_agent.nodes.emit_location_line import accept_address_venue_upgrade


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
