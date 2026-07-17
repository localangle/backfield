"""LangGraph consolidate node for organizing geocoded results into structured format."""

import copy
import hashlib
import logging
from typing import Any

from agate_utils.geocoding.h3 import h3_cell
from backfield_entities.ingest.geocode_cache.sanity import (
    explicit_location_components_match_labels,
)

from ..types import AgentState
from .emit_location_line import (
    compute_emit_location_line,
    maybe_upgrade_address_to_named_place,
    maybe_upgrade_intersection_to_named_place,
)
from .geocode import _adv_info

logger = logging.getLogger(__name__)

AGATE_GEOCODE_ROUTER_AUDIT_KEY = "agate_geocode_router_audit"

# Pelias layers at city scale or coarser (not street / venue / neighbourhood).
_PELIAS_CITY_OR_COARSER_LAYERS: frozenset[str] = frozenset(
    {
        "coarse",
        "continent",
        "country",
        "county",
        "dependency",
        "disputed",
        "localadmin",
        "locality",
        "macrocounty",
        "macroregion",
        "ocean",
        "region",
    }
)
# Pelias layers that are plausibly finer than a city centroid for our QA purposes.
_PELIAS_FINER_THAN_LOCALITY: frozenset[str] = frozenset(
    {
        "address",
        "borough",
        "intersection",
        "macrohood",
        "neighbourhood",
        "neighborhood",
        "postalcode",
        "street",
        "venue",
    }
)


def _geocoding_confidence_dict(geocoding_result: Any) -> dict[str, Any]:
    result = getattr(geocoding_result, "result", None)
    conf = getattr(result, "confidence", None) if result is not None else None
    return conf if isinstance(conf, dict) else {}


def _stylebook_or_canonical_hit(geocoding_result: Any) -> bool:
    rid = str(getattr(getattr(geocoding_result, "result", None), "id", "") or "")
    if rid.lower().startswith("stylebook:"):
        return True
    geo = str(getattr(geocoding_result, "geocoder", "") or "").lower()
    if geo.startswith("stylebook"):
        return True
    conf = _geocoding_confidence_dict(geocoding_result)
    if str(conf.get("source") or "").lower() == "canonical":
        return True
    if conf.get("canonical_id"):
        return True
    return False


def _neighborhood_or_district_token(components: dict[str, Any], *, location_type: str) -> str:
    c = components or {}
    lt = (location_type or "").strip().lower()
    if lt == "district":
        d = c.get("district")
        if isinstance(d, dict):
            return str(d.get("name") or d.get("label") or "").strip().lower()
        return str(d or "").strip().lower()
    return str(c.get("neighborhood") or "").strip().lower()


def _place_name_token(components: dict[str, Any]) -> str:
    c = components or {}
    p = c.get("place")
    if isinstance(p, dict):
        return str(p.get("name") or "").strip().lower()
    return str(p or "").strip().lower()


def _address_line_for_qa(components: dict[str, Any], location_text: str) -> str:
    c = components or {}
    a = str(c.get("address") or "").strip()
    if a:
        return a
    return str(location_text or "").strip()


def _address_requests_street_resolution(addr_line: str) -> bool:
    """True when the extract looks like a street / mailing line (not city-only)."""
    s = (addr_line or "").strip()
    if not s:
        return False
    if any(ch.isdigit() for ch in s):
        return True
    # Street-style line without a house number (e.g. "Main St, Chicago, IL").
    return len(s) >= 10


def _label_contains_token(label: str, token: str) -> bool:
    t = (token or "").strip().lower()
    if len(t) < 2:
        return False
    return t in (label or "").strip().lower()


def _geocode_city_level_fallback_qa(
    location_type: str,
    formatted_line: str,
    components: dict[str, Any],
    geocoding_result: Any,
    *,
    location_text: str = "",
) -> bool:
    """True when a fine-grained extract likely resolved to a city-or-coarser hit only.

    Flags neighborhood / district / address / place / point rows for ``needs_review`` so
    city-centroid or locality-only fallbacks do not ship as silently verified geocodes.
    """
    lt = (location_type or "").strip().lower()
    if lt not in ("neighborhood", "district", "address", "place", "point"):
        return False
    # Trust Stylebook for coarse admin rows only; street/POI extracts still need fallback QA.
    if _stylebook_or_canonical_hit(geocoding_result) and lt not in ("address", "place", "point"):
        return False

    label = str(formatted_line or "")
    label_cf = label.strip().lower()
    conf = _geocoding_confidence_dict(geocoding_result)
    geo = str(getattr(geocoding_result, "geocoder", "") or "").lower()
    layer = str(conf.get("pelias_layer") or "").strip().lower()

    if lt in ("neighborhood", "district"):
        token = _neighborhood_or_district_token(components, location_type=lt)
        if len(token) < 2:
            return False
        if _label_contains_token(label_cf, token):
            return False
        if layer in _PELIAS_FINER_THAN_LOCALITY:
            return False
        if layer in _PELIAS_CITY_OR_COARSER_LAYERS:
            return True
        if geo == "nominatim":
            nt = str(conf.get("nominatim_type") or "").strip().lower()
            if nt in ("city", "town", "administrative") and not _label_contains_token(
                label_cf, token
            ):
                return True
        if geo.startswith("geocodio"):
            acc = str(conf.get("accuracy_type") or "").strip().lower()
            if acc in ("city", "county", "state") and not _label_contains_token(label_cf, token):
                return True
        return False

    if lt == "address":
        addr_line = _address_line_for_qa(components, location_text)
        if not _address_requests_street_resolution(addr_line):
            return False
        addr_cf = addr_line.strip().lower()
        # Strong match: house number or leading street fragment appears in geocoder label.
        if addr_cf and addr_cf[: min(24, len(addr_cf))] in label_cf:
            return False
        if layer in _PELIAS_FINER_THAN_LOCALITY:
            return False
        if layer in _PELIAS_CITY_OR_COARSER_LAYERS:
            return True
        if geo == "nominatim":
            # Building / house results often carry ``administrative`` in OSM; digits in the label
            # usually mean we resolved finer than city-only.
            if any(ch.isdigit() for ch in label_cf):
                return False
            nt = str(conf.get("nominatim_type") or "").strip().lower()
            if nt in ("city", "town", "state", "administrative"):
                return True
        if geo.startswith("geocodio"):
            acc = str(conf.get("accuracy_type") or "").strip().lower()
            if acc in ("city", "county", "state"):
                return True
        return False

    # place / point
    token = _place_name_token(components)
    if len(token) < 2:
        return False
    if _label_contains_token(label_cf, token):
        return False
    if layer in _PELIAS_FINER_THAN_LOCALITY:
        return False
    if layer in _PELIAS_CITY_OR_COARSER_LAYERS:
        return True
    if geo == "nominatim":
        nt = str(conf.get("nominatim_type") or "").strip().lower()
        if nt in ("city", "town", "administrative") and not _label_contains_token(label_cf, token):
            return True
    if geo.startswith("geocodio"):
        acc = str(conf.get("accuracy_type") or "").strip().lower()
        if acc in ("city", "county", "state") and not _label_contains_token(label_cf, token):
            return True
    return False


# Rough WGS84 bounds (west, south, east, north) for post-geocode plausibility checks.
_COUNTRY_BBOX: dict[str, tuple[float, float, float, float]] = {
    "US": (-170.0, 17.0, -65.0, 72.0),
    "CA": (-141.0, 41.0, -52.0, 84.0),
    "MX": (-118.0, 14.0, -86.0, 33.5),
    "FR": (-5.5, 41.0, 10.0, 51.5),
    "GB": (-8.8, 49.5, 2.0, 61.0),
    "CN": (73.0, 18.0, 135.0, 54.0),
}

_COUNTRY_LABEL_TO_ABBR: dict[str, str] = {
    "china": "CN",
    "france": "FR",
    "united states": "US",
    "united states of america": "US",
    "usa": "US",
    "canada": "CA",
    "mexico": "MX",
    "united kingdom": "GB",
    "uk": "GB",
}


def _expected_country_abbr_from_components(components: dict[str, Any]) -> str | None:
    country = components.get("country")
    if not isinstance(country, dict):
        return None
    abbr = country.get("abbr")
    if isinstance(abbr, str) and abbr.strip():
        return abbr.strip().upper()
    return None


def _coordinates_in_country_bbox(lon: float, lat: float, country_abbr: str) -> bool:
    box = _COUNTRY_BBOX.get(country_abbr.upper())
    if box is None:
        return True
    west, south, east, north = box
    return west <= lon <= east and south <= lat <= north


def _point_coordinates_from_geocode(geocoding_result: Any) -> tuple[float, float] | None:
    result = getattr(geocoding_result, "result", None)
    geometry = getattr(result, "geometry", None) if result is not None else None
    if geometry is None or getattr(geometry, "type", None) != "Point":
        return None
    coords = getattr(geometry, "coordinates", None)
    if not isinstance(coords, (list, tuple)) or len(coords) < 2:
        return None
    try:
        return float(coords[0]), float(coords[1])
    except (TypeError, ValueError):
        return None


def _result_country_abbr_from_geocode(
    geocoding_result: Any,
    formatted_line: str,
) -> str | None:
    conf = _geocoding_confidence_dict(geocoding_result)
    cc = conf.get("pelias_country_code")
    if isinstance(cc, str) and cc.strip():
        return cc.strip().upper()[:2]
    label = formatted_line.strip().lower()
    if label in _COUNTRY_LABEL_TO_ABBR:
        return _COUNTRY_LABEL_TO_ABBR[label]
    head = label.split(",")[0].strip()
    if head in _COUNTRY_LABEL_TO_ABBR:
        return _COUNTRY_LABEL_TO_ABBR[head]
    return None


def _geocode_region_mismatch_qa(
    components: dict[str, Any],
    formatted_line: str,
    geocoding_result: Any,
) -> bool:
    """True when resolver country/centroid disagrees with PlaceExtract country context."""
    expected = _expected_country_abbr_from_components(components)
    if not expected:
        return False
    if _stylebook_or_canonical_hit(geocoding_result):
        return False

    resolved = _result_country_abbr_from_geocode(geocoding_result, formatted_line)
    if resolved and resolved != expected:
        return True

    coords = _point_coordinates_from_geocode(geocoding_result)
    if coords is not None and not _coordinates_in_country_bbox(coords[0], coords[1], expected):
        return True

    return False


def _normalize_us_state_abbr(value: str | None) -> str | None:
    """Return a 2-letter US state/DC abbr when ``value`` is a known name or abbr."""
    # Local import keeps consolidate free of place_extract cycles at module import.
    from agate_nodes.place_extract.location_utils import US_STATE_ABBR_BY_NAME, US_STATES

    raw = str(value or "").strip()
    if not raw:
        return None
    upper = raw.upper()
    if upper in US_STATES:
        return upper
    return US_STATE_ABBR_BY_NAME.get(raw.lower())


def _expected_state_abbr_from_extract(
    components: dict[str, Any],
    *,
    location_type: str,
    location_text: str,
) -> str | None:
    state = components.get("state") if isinstance(components, dict) else None
    if isinstance(state, dict):
        abbr = _normalize_us_state_abbr(str(state.get("abbr") or ""))
        if abbr:
            return abbr
        abbr = _normalize_us_state_abbr(str(state.get("name") or ""))
        if abbr:
            return abbr
    elif isinstance(state, str):
        abbr = _normalize_us_state_abbr(state)
        if abbr:
            return abbr
    if (location_type or "").strip().lower() == "state":
        return _normalize_us_state_abbr(location_text)
    return None


def _result_state_abbr_from_geocode(
    geocoding_result: Any,
    formatted_line: str,
) -> str | None:
    conf = _geocoding_confidence_dict(geocoding_result)
    for key in ("pelias_region_a", "region_a", "state_abbr", "state_code"):
        abbr = _normalize_us_state_abbr(str(conf.get(key) or ""))
        if abbr:
            return abbr
    for key in ("pelias_region", "region", "state"):
        abbr = _normalize_us_state_abbr(str(conf.get(key) or ""))
        if abbr:
            return abbr
    # Trailing ", OR" / ", Oregon" in formatted geocoder label.
    label = str(formatted_line or "").strip()
    if "," in label:
        tail = label.rsplit(",", 1)[-1].strip()
        abbr = _normalize_us_state_abbr(tail)
        if abbr:
            return abbr
    return _normalize_us_state_abbr(label)


def _geocode_subnational_label_mismatch_qa(
    location_type: str,
    components: dict[str, Any],
    location_text: str,
    formatted_line: str,
    geocoding_result: Any,
) -> bool:
    """True when expected state/country contradicts the geocoder's admin labels.

    Narrow gate for bare state/country extracts and rows with explicit admin
    components (Oregon→Maryland, Michigan→Illinois).
    """
    if _stylebook_or_canonical_hit(geocoding_result):
        return False

    comps = components if isinstance(components, dict) else {}
    lt = (location_type or "").strip().lower()
    expected_state = _expected_state_abbr_from_extract(
        comps, location_type=lt, location_text=location_text
    )
    expected_country = _expected_country_abbr_from_components(comps)
    if lt == "country" and not expected_country:
        expected_country = _COUNTRY_LABEL_TO_ABBR.get(str(location_text or "").strip().lower())

    state_comp = comps.get("state")
    if isinstance(state_comp, dict):
        state_label = str(state_comp.get("abbr") or state_comp.get("name") or "").strip()
        has_explicit_state = bool(state_label)
    elif isinstance(state_comp, str):
        has_explicit_state = bool(state_comp.strip())
    else:
        has_explicit_state = False
    country_comp = comps.get("country")
    has_explicit_country = isinstance(country_comp, dict) and bool(
        str(country_comp.get("abbr") or "").strip()
    )
    check_state = lt == "state" or has_explicit_state
    check_country = lt == "country" or has_explicit_country
    if not check_state and not check_country:
        return False

    if check_state and expected_state:
        resolved_state = _result_state_abbr_from_geocode(geocoding_result, formatted_line)
        if resolved_state and resolved_state != expected_state:
            return True

    if check_country and expected_country:
        resolved_country = _result_country_abbr_from_geocode(geocoding_result, formatted_line)
        if resolved_country and resolved_country != expected_country:
            return True

    return False


def _point_entry_without_geometry(entry: dict[str, Any]) -> dict[str, Any]:
    """Move rejected provider identity to audit-only metadata."""
    out = copy.deepcopy(entry)
    geocode = out.pop("geocode", None)
    if isinstance(geocode, dict):
        result = geocode.get("result")
        rejected: dict[str, Any] = {
            "geocode_type": geocode.get("geocode_type"),
        }
        if isinstance(result, dict):
            rejected["provider_id"] = result.get("id")
            rejected["formatted_address"] = result.get("formatted_address")
        out["rejected_geocode_audit"] = rejected
    identity_basis = "|".join(
        (
            str(out.get("type") or ""),
            str(out.get("original_text") or out.get("location") or ""),
        )
    )
    out["id"] = f"rejected:{hashlib.sha256(identity_basis.encode()).hexdigest()[:20]}"
    out["geocoded"] = False
    out["geocode_disposition"] = "rejected"
    return out


def _city_geocode_admin_level_mismatch(
    location_type: str,
    formatted_line: str,
    components: dict[str, Any],
    geocoding_result: Any,
) -> bool:
    """True when a city request resolves to a state- or national-scale result."""
    if location_type not in ("city", "town"):
        return False
    city = str((components or {}).get("city") or "").strip()
    if not city:
        return False
    label = (formatted_line or "").lower()
    if city.lower() in label:
        return False
    result = getattr(geocoding_result, "result", None)
    conf = getattr(result, "confidence", None) if result is not None else None
    conf_dict: dict[str, Any] = conf if isinstance(conf, dict) else {}
    geo = str(getattr(geocoding_result, "geocoder", "") or "")
    layer = str(conf_dict.get("pelias_layer") or "").lower()
    if layer in ("region", "country"):
        return True
    if geo == "nominatim" and str(conf_dict.get("nominatim_type") or "").lower() == "state":
        return True
    if geo.startswith("geocodio"):
        acc_t = str(conf_dict.get("accuracy_type") or "").lower()
        if acc_t == "state":
            return True
    return False


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

    country_identity = state.get("country_terminal_identity")
    if location_type == "country" and isinstance(country_identity, dict):
        country_name = str(country_identity.get("name") or "").strip()
        country_code = str(country_identity.get("abbr") or "").strip().upper()
        country_entry = {
            "id": f"iso-country:{country_code}",
            "original_text": original_text,
            "location": country_name,
            "type": "country",
            "description": extra_fields.get("description", "Recognized country"),
            "country_code": country_code,
            "geocode_disposition": "accepted_authoritative_identity",
        }
        canonical_id = country_identity.get("canonical_id")
        if canonical_id:
            country_entry["canonical_id"] = str(canonical_id)
        for key, value in extra_fields.items():
            if key != "description":
                country_entry[key] = value
        _attach_router_audit(country_entry, state)
        state["final_output"] = {
            "places": {
                "areas": {
                    "states": [],
                    "counties": [],
                    "cities": [],
                    "neighborhoods": [],
                    "regions": [],
                    "other": [country_entry],
                },
                "points": [],
                "needs_review": [],
            }
        }
        return state
    
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
        if location_type == "country" and failure_reason == "country_identity_unresolved":
            non_geocoded_entry["reason_code"] = "country_identity_unresolved"
            non_geocoded_entry["geocode_disposition"] = "needs_country_identity_review"
        
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

    # Preserve canonical identity from a Stylebook match for downstream linking.
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
    effective_type = location_type
    if location_type == "address":
        emit_location, _ = await maybe_upgrade_address_to_named_place(
            state,
            formatted_address=formatted_line,
            baseline_location_line=emit_location,
        )
    elif location_type in ("intersection_road", "intersection_highway"):
        emit_location, upgraded_to_place = await maybe_upgrade_intersection_to_named_place(
            state,
            formatted_address=formatted_line,
            baseline_location_line=emit_location,
        )
        if upgraded_to_place:
            effective_type = "place"

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
        "type": effective_type,
        "description": extra_fields.get("description", f"Geocoded {effective_type} location"),
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
    components_for_qa = state.get("location_components") or {}
    comps_dict = components_for_qa if isinstance(components_for_qa, dict) else {}
    if not explicit_location_components_match_labels(
        components=comps_dict,
        location_text=location_text,
        match_label=formatted_line,
        match_formatted_address=formatted_line,
    ):
        qa_entry = _point_entry_without_geometry(
            {
                **location_entry,
                "geocode_component_mismatch": True,
                "geocode_qa_code": "geocode_component_mismatch",
            }
        )
        _attach_router_audit(qa_entry, state)
        consolidated["places"]["needs_review"].append(qa_entry)
        state["final_output"] = consolidated
        return state
    subnational_mismatch = _geocode_subnational_label_mismatch_qa(
        location_type,
        comps_dict,
        location_text,
        formatted_line,
        geocoding_result,
    )
    if subnational_mismatch and location_type in ("state", "country"):
        qa_entry = _point_entry_without_geometry(
            {
                **location_entry,
                "geocode_subnational_mismatch": True,
                "geocode_qa_code": "geocode_subnational_mismatch",
            }
        )
        _attach_router_audit(qa_entry, state)
        consolidated["places"]["needs_review"].append(qa_entry)
    elif location_type in ["state"]:
        consolidated["places"]["areas"]["states"].append(location_entry)
    elif location_type in ["county"]:
        consolidated["places"]["areas"]["counties"].append(location_entry)
    elif location_type in ["city", "town"]:
        if subnational_mismatch or _city_geocode_admin_level_mismatch(
            location_type, formatted_line, components_for_qa, geocoding_result
        ):
            qa_code = (
                "geocode_subnational_mismatch"
                if subnational_mismatch
                else "geocode_admin_level_mismatch"
            )
            qa_entry = _point_entry_without_geometry(
                {
                    **location_entry,
                    "geocode_admin_level_mismatch": qa_code
                    == "geocode_admin_level_mismatch",
                    "geocode_subnational_mismatch": qa_code
                    == "geocode_subnational_mismatch",
                    "geocode_qa_code": qa_code,
                }
            )
            _attach_router_audit(qa_entry, state)
            consolidated["places"]["needs_review"].append(qa_entry)
        else:
            consolidated["places"]["areas"]["cities"].append(location_entry)
    elif location_type == "political_district":
        consolidated["places"]["areas"]["other"].append(location_entry)
    elif location_type in ["neighborhood", "district"]:
        components_qa = state.get("location_components") or {}
        if _geocode_city_level_fallback_qa(
            location_type,
            formatted_line,
            components_qa if isinstance(components_qa, dict) else {},
            geocoding_result,
            location_text=location_text,
        ):
            qa_entry = _point_entry_without_geometry(
                {
                    **location_entry,
                    "geocode_city_level_fallback": True,
                    "geocode_qa_code": "geocode_city_level_fallback",
                }
            )
            _attach_router_audit(qa_entry, state)
            consolidated["places"]["needs_review"].append(qa_entry)
        else:
            consolidated["places"]["areas"]["neighborhoods"].append(location_entry)
    elif location_type in ["region", "area"] or location_type.startswith("region_"):
        consolidated["places"]["areas"]["regions"].append(location_entry)
    elif location_type in ["natural", "street_road"]:
        consolidated["places"]["areas"]["other"].append(location_entry)
    elif location_type in [
        "address",
        "point",
        "place",
        "intersection_road",
        "intersection_highway",
    ]:
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
            "type": effective_type,
            "description": extra_fields.get("description", f"Geocoded {effective_type} location"),
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

        components_qa = state.get("location_components") or {}
        comps_dict = components_qa if isinstance(components_qa, dict) else {}
        region_mismatch = (
            location_type in ("address", "place", "point")
            and _geocode_region_mismatch_qa(
                comps_dict,
                formatted_line,
                geocoding_result,
            )
        )
        city_fallback = (
            location_type in ("address", "place", "point")
            and _geocode_city_level_fallback_qa(
                location_type,
                formatted_line,
                comps_dict,
                geocoding_result,
                location_text=location_text,
            )
        )
        llm_intersection_estimate = (
            location_type in ("intersection_road", "intersection_highway")
            and geocoding_result.geocoder == "intersection_llm_estimate"
        )
        if region_mismatch:
            qa_point = _point_entry_without_geometry(
                {
                    **point_entry,
                    "geocode_region_mismatch": True,
                    "geocode_qa_code": "geocode_region_mismatch",
                }
            )
            _attach_router_audit(qa_point, state)
            consolidated["places"]["needs_review"].append(qa_point)
        elif city_fallback:
            qa_point = _point_entry_without_geometry(
                {
                    **point_entry,
                    "geocode_city_level_fallback": True,
                    "geocode_qa_code": "geocode_city_level_fallback",
                }
            )
            _attach_router_audit(qa_point, state)
            consolidated["places"]["needs_review"].append(qa_point)
        elif llm_intersection_estimate:
            qa_point = _point_entry_without_geometry(
                {
                    **point_entry,
                    "geocode_llm_intersection_estimate": True,
                    "geocode_qa_code": "llm_intersection_estimate",
                }
            )
            _attach_router_audit(qa_point, state)
            consolidated["places"]["needs_review"].append(qa_point)
        else:
            consolidated["places"]["points"].append(point_entry)
    else:
        consolidated["places"]["areas"]["other"].append(location_entry)
    
    state["final_output"] = consolidated
    return state
