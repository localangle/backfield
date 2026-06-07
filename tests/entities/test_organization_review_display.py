"""Organization review display copy tests."""

from backfield_entities.entities.organization.review_display import (
    ORGANIZATION_CANONICAL_TYPE_MISMATCH_MESSAGE,
    organization_canonical_type_mismatch_display_message,
)


def test_organization_canonical_type_mismatch_message() -> None:
    msg = organization_canonical_type_mismatch_display_message(
        {
            "code": "organization_canonical_type_mismatch",
            "substrate_type": "school_district",
            "canonical_type": "public_services",
        }
    )
    assert msg == ORGANIZATION_CANONICAL_TYPE_MISMATCH_MESSAGE
