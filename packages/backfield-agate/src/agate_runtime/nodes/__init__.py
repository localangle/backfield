"""Agate node implementations."""

from agate_runtime.nodes.db_output import run_db_output
from agate_runtime.nodes.embed_text import run_embed_text
from agate_runtime.nodes.geocode_agent import run_geocode_agent
from agate_runtime.nodes.json_input import run_json_input
from agate_runtime.nodes.organization_extract import run_organization_extract
from agate_runtime.nodes.output import run_output
from agate_runtime.nodes.person_extract import run_person_extract
from agate_runtime.nodes.place_extract import run_place_extract
from agate_runtime.nodes.s3_input import run_s3_input
from agate_runtime.nodes.text_input import run_text_input

NODE_RUNNERS: dict[str, callable] = {
    "TextInput": run_text_input,
    "JSONInput": run_json_input,
    "S3Input": run_s3_input,
    "PlaceExtract": run_place_extract,
    "PersonExtract": run_person_extract,
    "OrganizationExtract": run_organization_extract,
    "EmbedText": run_embed_text,
    "GeocodeAgent": run_geocode_agent,
    "Output": run_output,
    "DBOutput": run_db_output,
}

__all__ = ["NODE_RUNNERS"]
