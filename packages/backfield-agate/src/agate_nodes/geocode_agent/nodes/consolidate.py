"""LangGraph consolidate node for organizing geocoded results into structured format."""

import hashlib
import logging

from agate_utils.geocoding.h3 import h3_cell

from ..types import AgentState
from .emit_location_line import compute_emit_location_line
from .geocode import _adv_info

logger = logging.getLogger(__name__)

AGATE_GEOCODE_ROUTER_AUDIT_KEY = "agate_geocode_router_audit"


def _attach_router_audit(entry: dict, state: AgentState) -> None:
    audit = state.get("router_audit")
    if audit is not None:
        entry[AGATE_GEOCODE_ROUTER_AUDIT_KEY] = audit


########## CONSOLIDATE NODE ##########

async def consolidate_node(state: AgentState) -> AgentState:
    """
    Consolidate geocoded results into organized structure with areas and points.
    
    For non-addressable places (where geocoding was skipped), creates a special
    entry without geocode data.
    """
    geocoding_result = state.get("geocoding_result")
    location_type = (state.get("location_type") or "").lower()
    location_text = state.get("location_text") or ""
    original_text = state.get("original_text") or location_text
    extra_fields = state.get("extra_fields", {})
    
    # Handle non-addressable places (None geocoding result)
    if not geocoding_result:
        _adv_info(
            state,
            "No geocoding result for %s - creating non-geocoded entry",
            location_text,
        )
        
        # Get the failure reason from state
        failure_reason = state.get(
            "geocoding_failure_reason",
            f"Geocoding produced no result for {location_type or 'location'}",
        )
        
        # Create a non-geocoded entry
        non_geocoded_entry = {
            "id": f"non-geocoded:{location_text.lower().replace(' ', '-')}",
            "original_text": original_text,
            "location": location_text,
            "type": location_type,
            "geocoded": False,
            "reason": failure_reason
        }
        
        # Preserve all extra fields (including 'mural' and any other custom fields)
        for key, value in extra_fields.items():
            non_geocoded_entry[key] = value

        _attach_router_audit(non_geocoded_entry, state)

        state["final_output"] = {
            "places": {
                "areas": {
                    "states": [],
                    "counties": [],
                    "cities": [],
                    "neighborhoods": [],
                    "regions": [],
                    "other": []
                },
                "points": [],
                "needs_review": [non_geocoded_entry]
            }
        }
        return state
    
    # Create the consolidated structure
    consolidated = {
        "places": {
            "areas": {
                "states": [],
                "counties": [],
                "cities": [],
                "neighborhoods": [],
                "regions": [],
                "other": []
            },
            "points": [],
            "needs_review": []
        }
    }
    
    # Create the location entry
    # Generate ID based on location type
    if location_type == "street_road":
        # For street_road, use hash of location attribute truncated to 20 chars
        location_hash = hashlib.md5(location_text.encode()).hexdigest()[:20]
        entry_id = f"street_road:{location_hash}"
    else:
        # For other types, use the geocoding result ID
        entry_id = geocoding_result.result.id
    
    # Debug logging for geometry
    geometry_type = geocoding_result.result.geometry.type
    geometry_coords = geocoding_result.result.geometry.coordinates
    _adv_info(
        state,
        "Consolidating geometry: type=%s, coords_length=%s, coords_type=%s",
        geometry_type,
        len(str(geometry_coords)) if geometry_coords else 0,
        type(geometry_coords).__name__,
    )

    # Stylebook canonical id when this result came from a Stylebook canonical match (for core-api to create link)
    confidence = getattr(geocoding_result.result, "confidence", None) or {}
    canonical_id = confidence.get("canonical_id")
    if canonical_id is None and geocoding_result.result.id and str(
        geocoding_result.result.id
    ).startswith("stylebook:"):
        tail = str(geocoding_result.result.id).removeprefix("stylebook:").strip()
        canonical_id = tail or None

    formatted_line = geocoding_result.result.processed_str
    emit_location = await compute_emit_location_line(
        state,
        formatted_address=formatted_line,
    )

    result_base = {
        "id": geocoding_result.result.id,
        "formatted_address": formatted_line,
        "geometry": {
            "type": geometry_type,
            "coordinates": geometry_coords
        },
    }
    if canonical_id is not None:
        result_base["canonical_id"] = str(canonical_id).strip()

    location_entry = {
        "id": entry_id,
        "original_text": original_text,  # Original text from the article
        "location": emit_location,
        "type": location_type,
        "description": extra_fields.get("description", f"Geocoded {location_type} location"),
        "geocode": {
            "geocode_type": geocoding_result.geocoder,
            "result": dict(result_base),
        }
    }
    
    # Preserve all extra fields (including 'mural' and any other custom fields)
    for key, value in extra_fields.items():
        if key not in ["description"]:  # Description is already handled above
            location_entry[key] = value

    _attach_router_audit(location_entry, state)

    # Organize by location type
    if location_type in ["state"]:
        consolidated["places"]["areas"]["states"].append(location_entry)
    elif location_type in ["county"]:
        consolidated["places"]["areas"]["counties"].append(location_entry)
    elif location_type in ["city", "town"]:
        consolidated["places"]["areas"]["cities"].append(location_entry)
    elif location_type in ["neighborhood", "district"]:
        consolidated["places"]["areas"]["neighborhoods"].append(location_entry)
    elif location_type in ["region", "area"] or location_type.startswith("region_"):
        consolidated["places"]["areas"]["regions"].append(location_entry)
    elif location_type in ["natural", "street_road"]:
        consolidated["places"]["areas"]["other"].append(location_entry)
    elif location_type in ["address", "point", "place", "intersection_road", "intersection_highway"]:
        # Use H3 cell ID as the point ID
        coordinates = geocoding_result.result.geometry.coordinates
        try:
            # H3 expects (lat, lon) but GeoJSON uses [lon, lat]
            h3_id = 'h3:' + h3_cell(lat=coordinates[1], lon=coordinates[0], res=12)
        except Exception as e:
            logger.warning(f"Failed to generate H3 ID for point: {e}, using geocoder ID instead")
            h3_id = geocoding_result.result.id
        
        point_entry = {
            "id": h3_id,
            "original_text": original_text,
            "location": emit_location,
            "type": location_type,
            "description": extra_fields.get("description", f"Geocoded {location_type} location"),
            "geocode": {
                "geocode_type": geocoding_result.geocoder,
                "result": dict(result_base),
            }
        }
        
        # Preserve all extra fields (including 'mural' and any other custom fields)
        for key, value in extra_fields.items():
            if key not in ["description"]:  # Description is already handled above
                point_entry[key] = value

        _attach_router_audit(point_entry, state)

        consolidated["places"]["points"].append(point_entry)
    else:
        consolidated["places"]["areas"]["other"].append(location_entry)
    
    state["final_output"] = consolidated
    return state
