Choose how to run **external** geocoding for one location (cache was already checked).

Respond with **only** a JSON object (no markdown fences) with keys:
- **strategy**: exactly `"legacy_default"` or `"no_web_search"`
- **rationale**: optional short string

Meanings:
- **legacy_default**: Normal pipeline, including Brave web search when configured for place-like flows.
- **no_web_search**: Same pipeline but **without** Brave web search for place resolution.

Use **no_web_search** when web search is unlikely to help or could add noise. Otherwise use **legacy_default**.

## Fields

- location_type: {location_type}
- location_text: {location_text}
- original_text: {original_text}
- components_json: {components_json}
