"""Resolve GeocodeAgent LiteLLM model ids from catalog pins."""

from __future__ import annotations

from dataclasses import dataclass

from backfield_ai.model_resolve import resolve_geocode_litellm_models
from backfield_db import (
    BackfieldAiModelConfig,
    BackfieldOrganization,
    BackfieldProject,
)
from sqlmodel import Session, SQLModel, create_engine


@dataclass
class _GeocodeParams:
    evaluationModel: str = "gpt-4o-mini"
    routerModel: str = "gpt-4o-mini"
    geographicReasoningModel: str = "gpt-4o"
    geographicEstimationModel: str = ""
    evaluationAiModelConfigId: str | None = None
    routerAiModelConfigId: str | None = None
    geographicReasoningAiModelConfigId: str | None = None
    geographicEstimationAiModelConfigId: str | None = None


def _engine():
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    return engine


def test_resolve_geocode_models_estimation_falls_back_to_reasoning() -> None:
    engine = _engine()
    with Session(engine) as session:
        org = BackfieldOrganization(name="Org", slug="org-geo-est-fb")
        session.add(org)
        session.commit()
        session.refresh(org)
        org_id = int(org.id)  # type: ignore[arg-type]
        proj = BackfieldProject(name="P", slug="p-geo-est-fb", organization_id=org_id)
        session.add(proj)
        session.commit()
        session.refresh(proj)
        project_id = int(proj.id)  # type: ignore[arg-type]

        params = _GeocodeParams(
            geographicReasoningModel="gpt-4o",
            geographicEstimationModel="",
        )
        eval_m, router_m, geo_m, est_m = resolve_geocode_litellm_models(
            session, project_id, params
        )
        assert eval_m == "gpt-4o-mini"
        assert router_m == "gpt-4o-mini"
        assert geo_m == "gpt-4o"
        assert est_m == "gpt-4o"


def test_resolve_geocode_models_estimation_catalog_pin() -> None:
    engine = _engine()
    with Session(engine) as session:
        org = BackfieldOrganization(name="Org", slug="org-geo-est-pin")
        session.add(org)
        session.commit()
        session.refresh(org)
        org_id = int(org.id)  # type: ignore[arg-type]
        session.add(
            BackfieldAiModelConfig(
                id="geo-est-pin",
                organization_id=org_id,
                name="Geo Est",
                provider="openai",
                provider_model_id="gpt-5",
                model_kind="generative",
                capabilities_json=["text"],
            )
        )
        proj = BackfieldProject(name="P", slug="p-geo-est-pin", organization_id=org_id)
        session.add(proj)
        session.commit()
        session.refresh(proj)
        project_id = int(proj.id)  # type: ignore[arg-type]

        params = _GeocodeParams(
            geographicReasoningModel="gpt-4o",
            geographicEstimationAiModelConfigId="geo-est-pin",
        )
        _eval_m, _router_m, geo_m, est_m = resolve_geocode_litellm_models(
            session, project_id, params
        )
        assert geo_m == "gpt-4o"
        assert est_m == "gpt-5"
