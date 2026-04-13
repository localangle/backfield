from typing import Dict, Any, List
from ..types import AgentState
from agate_utils.geocoding.wof import get_geocode_by_id, get_parents_by_coords

########## HELPER FUNCTIONS ##########

def _collect_all_parent_ids(state: AgentState):
    parents, seen, final_output = [], set(), state.get("final_output", {})
    places = final_output.get("places", {})

    def collect_from(entries):
        if not isinstance(entries, list):
            return
        for entry in entries:
            for parent in entry.get("parent_ids", []):
                pid = f"{parent.get('id', '')}:{parent.get('name', '')}"
                if (
                    pid
                    and parent.get("id")
                    and parent.get("name")
                    and pid not in seen
                ):
                    parents.append(
                        {
                            **parent,
                            "child_original_text": entry.get("original_text", ""),
                        }
                    )
                    seen.add(pid)

    for entries in (places.get("areas", {}) or {}).values():
        collect_from(entries)
    collect_from(places.get("points", []))
    return parents


def _add_missing_parent_stubs(state: AgentState, all_parent_ids: List[Dict[str, Any]]):
    final_output = state.get("final_output", {})
    places = final_output.setdefault("places", {})
    areas = places.setdefault("areas", {})

    placetype_mapping = {
        "region": ("states", "state"),
        "county": ("counties", "county"),
        "locality": ("cities", "city"),
        "neighbourhood": ("neighborhoods", "neighborhood"),
    }

    processed_ids = set()

    for parent in all_parent_ids:
        parent_id_str = parent.get("id", "")
        parent_name = parent.get("name", "")
        child_original_text = parent.get("child_original_text", parent_name)

        if not parent_id_str or not parent_name or parent_id_str in processed_ids:
            continue

        area_type = our_type = None
        for placetype, (target_area, type_name) in placetype_mapping.items():
            if placetype in parent_id_str:
                area_type, our_type = target_area, type_name
                break

        if not area_type or not our_type:
            continue

        current_list = areas.setdefault(area_type, [])
        existing_ids = {item.get("id") for item in current_list if item.get("id")}

        if parent_id_str not in existing_ids:
            geocode = get_geocode_by_id(parent_id_str)
            bbox = geocode.get("geocode", {}).get("result", {}).get("geometry", {}).get("coordinates")
            parent_parent_ids: List[Dict[str, str]] = []

            if isinstance(bbox, list) and len(bbox) == 4:
                west, south, east, north = bbox
                lat = (south + north) / 2
                lon = (west + east) / 2
                try:
                    hierarchy = get_parents_by_coords(lat, lon, our_type)
                    for value in hierarchy.values():
                        pid = value.get("id")
                        name = value.get("name")
                        if pid and name and pid != parent_id_str:
                            parent_parent_ids.append({"id": pid, "name": name})
                except Exception:
                    parent_parent_ids = []

            stub_entry = {
                "id": parent_id_str,
                "original_text": child_original_text,
                "location": parent_name,
                "type": our_type,
                "description": "Parent object referenced by child locations",
                "parent_ids": parent_parent_ids,
                "geocode": geocode.get(
                    "geocode",
                    {
                        "geocode_type": "parent_stub",
                        "result": {
                            "id": parent_id_str,
                            "formatted_address": parent_name,
                            "geometry": {"type": "Unknown", "coordinates": []},
                        },
                    },
                ),
            }
            current_list.append(stub_entry)

        processed_ids.add(parent_id_str)

    places["areas"] = areas
    final_output["places"] = places
    state["final_output"] = final_output
    return state

########## ENRICH NODE ##########

async def enrich_node(state: AgentState) -> AgentState:
    parents = _collect_all_parent_ids(state)
    state = _add_missing_parent_stubs(state, parents)
    state["all_parent_ids"] = parents
    return state