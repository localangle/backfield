"""PersonEnrich runner for the Backfield executor."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError
from sqlmodel import Session

from agate_nodes.person_enrich.enrich import enrich_public_figures
from agate_nodes.person_enrich.params import PersonEnrichParams

if TYPE_CHECKING:
    from agate_runtime.context import AgateEnvContext

logger = logging.getLogger(__name__)

_SETTINGS_WARNING = "Person Enrich settings could not be read. People were left unchanged."


def run_person_enrich(params: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    # Imported lazily so node registration can load this module during package init.
    from agate_runtime.runners import default_context

    return run_person_enrich_with_context(params, inputs, default_context())


def run_person_enrich_with_context(
    params: dict[str, Any],
    inputs: dict[str, Any],
    context: AgateEnvContext,
) -> dict[str, Any]:
    from agate_runtime.upstream_input import flatten_upstream_inputs

    flat = flatten_upstream_inputs(inputs if isinstance(inputs, dict) else {})
    raw_people = flat.get("people")
    people: list[Any] = list(raw_people) if isinstance(raw_people, list) else []
    try:
        settings = PersonEnrichParams.model_validate(params or {})
    except ValidationError:
        logger.warning("Person Enrich params failed validation", exc_info=True)
        return {"people": people, "warnings": [_SETTINGS_WARNING]}

    litellm_model = ""
    api_key: str | None = None
    api_base: str | None = None
    stylebook_id: int | None = None
    project_id = context.project_id
    if project_id is not None and settings.ai_model_config_id and settings.selected_sources():
        litellm_model, api_key, api_base, stylebook_id = _load_project_context(
            project_id,
            settings.ai_model_config_id,
        )

    def cached_links(person: dict[str, Any]) -> dict[str, str] | None:
        if project_id is None or stylebook_id is None:
            return None
        return _cached_links_for_person(
            project_id=project_id,
            stylebook_id=stylebook_id,
            person=person,
            sources=settings.selected_sources(),
        )

    enriched, warnings = enrich_public_figures(
        people,
        settings,
        litellm_model=litellm_model,
        api_key=api_key,
        api_base=api_base,
        cached_links=cached_links,
        system_prompt=context.project_system_prompt,
    )
    output: dict[str, Any] = {"people": enriched}
    if warnings:
        output["warnings"] = warnings
    return output


def _load_project_context(
    project_id: int,
    model_config_id: str,
) -> tuple[str, str | None, str | None, int | None]:
    try:
        from backfield_ai.catalog_runtime import resolve_llm_auth_for_model_config
        from backfield_db.session import get_engine
        from backfield_entities.catalog.resolve import resolve_stylebook_id_for_project_id

        engine = get_engine()
        with Session(engine) as session:
            model, api_key, api_base = resolve_llm_auth_for_model_config(
                session,
                project_id=project_id,
                model_config_id=model_config_id,
                fallback_litellm_model="",
            )
            try:
                stylebook_id = resolve_stylebook_id_for_project_id(session, project_id)
            except Exception:
                logger.warning("Person Enrich could not resolve the Stylebook", exc_info=True)
                stylebook_id = None
        return model, api_key, api_base, stylebook_id
    except Exception:
        logger.warning("Person Enrich could not load the decision model", exc_info=True)
        return "", None, None, None


def _cached_links_for_person(
    *,
    project_id: int,
    stylebook_id: int,
    person: dict[str, Any],
    sources: set[str],
) -> dict[str, str] | None:
    from backfield_db.session import get_engine
    from backfield_entities.entities.person.enrichment import cached_selected_links

    name = person.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    affiliation = person.get("affiliation")
    affiliation_text = affiliation.strip() if isinstance(affiliation, str) else None
    engine = get_engine()
    with Session(engine) as session:
        return cached_selected_links(
            session,
            stylebook_id=stylebook_id,
            name=name,
            affiliation=affiliation_text,
            sources=sources,
            project_id=project_id,
        )
