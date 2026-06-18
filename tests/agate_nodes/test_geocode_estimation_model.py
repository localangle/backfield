"""GeocodeAgent geographic estimation model selection helpers."""

from __future__ import annotations

from agate_nodes.geocode_agent.models.area.area import Area
from agate_nodes.geocode_agent.models.point.address import Address


def test_estimation_model_falls_back_to_reasoning_on_address() -> None:
    model = Address(name="123 Main St")
    model._geographic_reasoning_llm_model = "reason-model"  # type: ignore[attr-defined]
    model._geographic_reasoning_ai_model_config_id = "reason-cfg"  # type: ignore[attr-defined]

    assert model._geographic_estimation_litellm_model() == "reason-model"
    assert model._geographic_estimation_model_config_id() == "reason-cfg"


def test_estimation_model_uses_explicit_pin_on_area() -> None:
    model = Area(name="Example region")
    model._geographic_reasoning_llm_model = "reason-model"  # type: ignore[attr-defined]
    model._geographic_estimation_llm_model = "est-model"  # type: ignore[attr-defined]
    model._geographic_estimation_ai_model_config_id = "est-cfg"  # type: ignore[attr-defined]

    assert model._geographic_estimation_litellm_model() == "est-model"
    assert model._geographic_estimation_model_config_id() == "est-cfg"
