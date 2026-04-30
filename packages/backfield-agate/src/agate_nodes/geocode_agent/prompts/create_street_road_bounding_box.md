You are a geographic analysis AI. Given raw Nominatim geocoding data and the original text context, create an appropriate bounding box that best represents the street/road area mentioned in the context.

Street/Road: {street_name}
City: {city}
State: {state_abbr}
Original Text Context: "{original_text}"

Raw Nominatim Data:
{raw_nominatim_data}

Based on the original text context and the available road segments from Nominatim, determine which segments are most relevant and create an appropriate bounding box. Consider:
- Which segments are most likely mentioned in the original text context
- Street length and typical width based on the context
- Geographic relevance (e.g., "near downtown", "residential area", "highway section")
- Street type and category from the Nominatim data

Each segment in the data has:
- place_id: Unique identifier
- osm_type: Usually "way" for road segments
- osm_id: OpenStreetMap ID
- class: Usually "highway"
- type: Road type (residential, secondary, primary, etc.)
- name: Street name
- display_name: Full address string
- boundingbox: [south, north, west, east] coordinates as strings
- lat/lon: Center point coordinates

Return a JSON object with:
{{
    "west": <west longitude>,
    "south": <south latitude>, 
    "east": <east longitude>,
    "north": <north latitude>,
    "reasoning": "<brief explanation of which segments were chosen and why>",
    "selected_segments": [<list of place_ids that were considered most relevant>]
}}

The bounding box should encompass the most relevant segments based on the original text context.
