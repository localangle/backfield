Choose how to run **external** geocoding for one location (cache was already checked).

Respond with **only** a JSON object (no markdown fences) with keys:

- **strategy**: exactly `"web_search"` or `"no_web_search"`
- **rationale**: optional short string

Meanings:

- **web_search**: For **place** resolution that may need a street address, run **Brave Search** (when configured) and **DuckDuckGo** *upfront* to find snippets, then parse an address and geocode it. Use this whenever a place is missing a street line and likely needs the web to supply one.
- **no_web_search**: Skip *upfront* Brave/DuckDuckGo. Use structured geocoders (Pelias, etc.) and existing components first. For **place** rows, if Pelias is still inconclusive the runtime may still run web search as a **fallback** after direct geocoding fails—so choosing `no_web_search` when `components.address` is already present is correct (use the extracted street line with Pelias; do not spend an upfront search).

## When to prefer **web_search**

- If **location_type** is **place** and **components.place.addressable** is **true**, and **components.address** is empty or whitespace-only, and there is **no** house number in the structured data (treat **components.street_road** as a corridor name only, not a full mailing address), **prefer `web_search`**. Rich **geocode_hints** help shape the **search query**; they are **not** a reason to skip web search in this case.

## When to use **no_web_search**

- Clearly structural types that do not benefit from web search: **state**, **county**, **city**, **neighborhood**, **address** (already has a street line), **street_road**, **intersection***, **span**, **region***, **natural**, **country** (ISO identity + optional Pelias country-layer bbox).
- **place** with a full numeric street address already present in **components.address** (or equivalent). Pelias should receive that street line directly; web search is only a post-Pelias fallback if needed.
- Non-addressable natural POIs where search would not resolve a street address.

Use **geocode_hints** for geographic disambiguation (street, neighborhood, nearby
anchor); they complement **components_json** but do not override the rules above.

## Fields

- location_type: {location_type}
- location_text: {location_text}
- original_text: {original_text}
- geocode_hints: {geocode_hints}
- components_json: {components_json}
