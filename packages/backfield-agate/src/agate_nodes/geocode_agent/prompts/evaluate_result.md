You are evaluating the quality of a geocoding result for a location extraction.

Your task is to determine if the geocoding result is a good match for the original location query.

## Location Details
- **Original Query**: {location_text}
- **Location Type**: {location_type}
- **Geocoder Used**: {geocoder}

## Geocoding Result
- **Processed String**: {processed_str}
- **Geometry Type**: {geometry_type}
- **Coordinates**: {coordinates}

# Evaluation Criteria

1. **Geography Type Match**: Does the result type match the expected type?
   - If looking for a city, did we get a city result?
   - If looking for a state, did we get a state/region result?
   - If looking for a county, did we get a county result?

2. **Geographic Accuracy**: Are the coordinates reasonable?
   - Do they fall within the expected geographic region?
   - Does the state/country match expectations from the original text?

3. **Address Quality**: Does the formatted address make sense?
   - Is it a complete, well-formed address?
   - Does it match the query intent?

4. **Confidence**: If confidence information is available, is it acceptable?
   - Higher confidence scores are better
   - Exact matches are preferred over fuzzy matches

# Quality Levels

- **good**: The result accurately matches the query. Use this result.
- **poor**: The result is questionable or incomplete. Try another geocoder.
- **failed**: No result was returned or the result is completely wrong. Skip this location.

# Response Format

Return ONLY a valid JSON object with this exact structure:

```json
{{
  "quality": "good" | "poor" | "failed",
  "reason": "Brief explanation of your assessment"
}}
```

CRITICAL: 
- Return ONLY the JSON object, no markdown formatting
- No ```json``` code blocks
- No additional text or explanations
- The JSON must be valid and parseable

