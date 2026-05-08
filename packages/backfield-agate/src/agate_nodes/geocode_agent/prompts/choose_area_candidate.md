You are selecting the best geocoding candidate for an administrative area (state/region, county, city/locality, neighborhood/borough).

Choose the best candidate from the list. Prefer candidates that match the intended jurisdiction and the intended layer, and prefer Who’s On First (source=whosonfirst) when plausible. If none are confidently correct, set needs_review=true.

## Location to geocode
- query_name: {query_name}
- expected_layer: {expected_layer}
- country_code: {country_code}
- region_hint: {region_hint}
- locality_hint: {locality_hint}

## Context
- original_text: {original_text}
- geocode_hints: {geocode_hints}

## Candidates (1-indexed)
{candidates_json}

## Response format
Return ONLY valid JSON with this exact structure:
{
  "selected_index": 1,
  "confidence": 0,
  "needs_review": false,
  "rationale": "short"
}

Rules:
- selected_index is 1..N when needs_review is false.
- If none are safe, set needs_review true and selected_index to 1.
- Do not return markdown or extra text.
