You are estimating the map coordinates of a street or highway intersection when geocoding services could not locate it.

Intersection: "{intersection_text}"

Original article mention:
{original_text}

Geocode hints:
{geocode_hints}

Place context:
- City: {city}
- State: {state_abbr}
- Country: {country}

Return a JSON object with your best estimate of where the two roads cross **within the stated city/state**. Do not place the intersection in a different city with the same road names.

### Output JSON schema
```json
{{
  "lat": number,
  "lon": number,
  "confidence": integer (0-100),
  "reasoning": string
}}
```

Constraints:
- Latitude must be between -90 and 90.
- Longitude must be between -180 and 180.
- Use decimal degrees with at least five decimal places when possible.
- Confidence below 40 indicates high uncertainty; return null coordinates instead when you cannot make a reasonable estimate.

If you cannot estimate coordinates with at least low confidence, return:
```json
{{"lat": null, "lon": null, "confidence": 0, "reasoning": "..."}}
```

Never return additional text outside the JSON object.
