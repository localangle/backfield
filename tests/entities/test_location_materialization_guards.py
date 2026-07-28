from __future__ import annotations

from typing import cast

import pytest
from backfield_db import SubstrateLocation
from backfield_entities.entities.location.persist import materialize_new_canonical_and_link
from sqlmodel import Session


@pytest.mark.parametrize("status", ["failed", "needs_review"])
def test_review_or_failed_location_cannot_materialize(status: str) -> None:
    location = SubstrateLocation(
        id=1,
        project_id=1,
        name="1400 Example Avenue",
        normalized_name="1400 example avenue",
        identity_fingerprint=f"fingerprint-{status}",
        location_type="address",
        status=status,
    )

    with pytest.raises(
        ValueError,
        match="rejected or review-required geocode cannot materialize",
    ):
        materialize_new_canonical_and_link(
            cast(Session, object()),
            stylebook_id=1,
            location=location,
        )


def test_review_bucket_cannot_materialize_even_with_provisional_status() -> None:
    location = SubstrateLocation(
        id=1,
        project_id=1,
        name="Example Point",
        normalized_name="example point",
        identity_fingerprint="fingerprint-review-bucket",
        location_type="point",
        status="provisional",
        source_details_json={"places_bucket": "needs_review"},
    )

    with pytest.raises(ValueError):
        materialize_new_canonical_and_link(
            cast(Session, object()),
            stylebook_id=1,
            location=location,
        )
