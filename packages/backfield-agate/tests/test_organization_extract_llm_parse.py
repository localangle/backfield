"""OrganizationExtract LLM parsing and normalization."""

from __future__ import annotations

import pytest
from agate_nodes.organization_extract.llm_organization_parse import organization_from_llm_entry
from agate_nodes.organization_extract.organization_schemas import ExtractedOrganization


def test_organization_from_llm_entry_normalizes_type_and_nature() -> None:
    org = organization_from_llm_entry(
        {
            "name": "Chicago Police Department",
            "type": "law enforcement",
            "role_in_story": "Increased patrols",
            "nature": "regulator",
            "nature_secondary_tags": ["source"],
            "mentions": [{"text": "Chicago Police Department increased patrols.", "quote": False}],
        }
    )
    assert isinstance(org, ExtractedOrganization)
    assert org.name == "Chicago Police Department"
    assert org.type == "law_enforcement"
    assert org.nature == "regulator"
    assert org.nature_secondary_tags == ["source"]


def test_organization_from_llm_entry_requires_name() -> None:
    with pytest.raises(ValueError, match="name"):
        organization_from_llm_entry(
            {
                "type": "government",
                "mentions": [{"text": "City Hall announced.", "quote": False}],
            }
        )


def test_organization_from_llm_entry_requires_mentions() -> None:
    with pytest.raises(ValueError, match="mentions"):
        organization_from_llm_entry({"name": "Cook County", "type": "government"})
