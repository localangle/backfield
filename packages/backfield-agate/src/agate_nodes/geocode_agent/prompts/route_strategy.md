Choose how to run **external** geocoding for one location (cache was already checked).

Respond with **only** a JSON object (no markdown fences) with keys:

- **strategy**: exactly `"web_search"` or `"no_web_search"`
- **rationale**: optional short string

Meanings:

- **web_search**: For **place** resolution that may need a street address, allow **Brave Search** (when configured) and **DuckDuckGo** as fallback to find snippets, then parse an address and geocode it. Use this whenever a place might need the web to supply a missing street line.
- **no_web_search**: **Neither Brave nor DuckDuckGo** runs. Use only structured geocoders (Pelias, etc.) and existing components.

## When to prefer **web_search**

- If **location_type** is **place** and **components.place.addressable** is **true**, and **components.address** is empty or whitespace-only, and there is **no** house number in the structured data (treat **components.street_road** as a corridor name only, not a full mailing address), **prefer `web_search`**. Rich **geocode_hints** help shape the **search query**; they are **not** a reason to skip web search in this case.

## When to use **no_web_search**

- Clearly structural types that do not benefit from web search: **state**, **county**, **city**, **neighborhood**, **address** (already has a street line), **street_road**, **intersection***, **span**, **region***, **natural**.
- **place** with a full numeric street address already present in **components.address** (or equivalent) so web search adds little.
- Non-addressable natural POIs where search would not resolve a street address.

Use **geocode_hints** for geographic disambiguation (street, neighborhood, nearby
anchor); they complement **components_json** but do not override the rules above.

## Fields

- location_type: {location_type}
- location_text: {location_text}
- original_text: {original_text}
- geocode_hints: {geocode_hints}
- components_json: {components_json}
