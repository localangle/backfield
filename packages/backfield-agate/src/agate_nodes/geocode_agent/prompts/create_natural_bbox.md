You are estimating a geographic bounding box for a natural feature.

Feature: "{location_str}"

Context:\n{additional_prompting}

Return a JSON object describing your best estimate. If you are uncertain, provide your best guess with an appropriate confidence.

### Output JSON schema
```
{
  "bounding_box": [min_latitude, min_longitude, max_latitude, max_longitude],
  "center_lat": number,
  "center_lon": number,
  "confidence": integer (0-100),
  "reasoning": string
}
```

Constraints:
- Latitude values must be between -90 and 90.
- Longitude values must be between -180 and 180.
- `min_latitude` < `max_latitude`, `min_longitude` < `max_longitude`.
- Confidence below 40 indicates high uncertainty.

Never return additional text outside the JSON object.

