"""Agate node implementations."""

from backfield_core.nodes.db_output import run_db_output
from backfield_core.nodes.geocode_agent import run_geocode_agent
from backfield_core.nodes.json_input import run_json_input
from backfield_core.nodes.output import run_output
from backfield_core.nodes.place_extract import run_place_extract
from backfield_core.nodes.s3_input import run_s3_input
from backfield_core.nodes.text_input import run_text_input

NODE_RUNNERS: dict[str, callable] = {
    "TextInput": run_text_input,
    "JSONInput": run_json_input,
    "S3Input": run_s3_input,
    "PlaceExtract": run_place_extract,
    "GeocodeAgent": run_geocode_agent,
    "Output": run_output,
    "DBOutput": run_db_output,
}

__all__ = ["NODE_RUNNERS"]
