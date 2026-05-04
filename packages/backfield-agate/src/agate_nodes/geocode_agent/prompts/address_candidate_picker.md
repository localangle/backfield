You are helping pick the best Pelias geocoding candidate for a **street address** from a news story.

## Inputs

**Original text (verbatim mention):** {original_text}

**Geocode hints (extractor context; may be `(none)`):** {geocode_hints}

**Search query used:** {query}

## Candidates (JSON)

Each candidate has an **index** (1-based), **label** (Pelias display string), **layer**, optional **coordinates** [lon, lat], and optional **confidence** (0–100 if inferable from the payload; otherwise null).

{candidates_json}

## Task

Return **only** a JSON object (no markdown fences) with:

- **selected_index**: integer, 1-based index of the best-matching candidate
- **confidence**: integer 0–100 for how sure you are this is the correct real-world location

Rules:

- Prefer candidates whose **label** and geography align with **original_text** and **geocode_hints** when hints are not `(none)`.
- If you are unsure or no candidate fits, set **confidence** below 40 and pick **selected_index** 1.

Example output:

{{"selected_index": 2, "confidence": 85}}
