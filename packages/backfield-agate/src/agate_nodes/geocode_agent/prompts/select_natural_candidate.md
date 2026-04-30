You are selecting the most relevant geocoding result for a natural place such as a lake, mountain, river, forest, or park.

Given this search query: "{location}"{context_part}

Here are the candidates returned by Nominatim:

{candidates_json}

Evaluate which candidate best matches the intended natural feature.

### Considerations
- Match the name closely to the query.
- Prefer natural features (classes/types like `natural`, `water`, `peak`, `forest`, `protected_area`, etc.).
- Use the geographic context: city, state, region, country.
- Larger or more prominent features are usually better than tiny or obscure ones unless the context clearly prefers the smaller place.
- If document context is provided, prefer candidates that align with it.
- Favor candidates with meaningful bounding boxes (not tiny points) when they match the description.
- If none of the candidates make sense, return a confidence below 40.

### Output
Return only a JSON object with:
- `"selected_index"`: 1-based index of the best candidate.
- `"confidence"`: Integer from 0-100 indicating confidence.
- `"reasoning"`: Brief explanation of the choice.

Example:
{{"selected_index": 2, "confidence": 78, "reasoning": "Candidate 2 matches the lake name and is in the referenced state"}}

