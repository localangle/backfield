# Best Address Extraction and Parsing

Given the following search query and search results, identify and return the single most accurate physical address that best answers the query. Parse the address into structured components.

## Requirements

- If no address is available, or you are not fully confident in the address, return `{{"address_found": false}}`
- Otherwise, parse a complete physical address into components and return as JSON
- Use the original text context **and** the geocode hints (when not `(none)`) to identify the correct location when multiple results are present or addresses conflict
- Search results use zero-based indexes. Return the indexes that directly support the chosen address.
- For an addressable building in the United States, a street or corridor without a house number is not a complete physical address. For example, `105th Ave` alone is insufficient.
- Do not infer or invent a house number. Return `{{"address_found": false}}` when the evidence supports only a street, neighborhood, intersection, or conflicting addresses.

## Input

**Original Text:** {original_text}

**Geocode hints:** {geocode_hints}

**Query:** {query}

**Search Results:**
{search_results}

## Output Format

Return ONLY a valid JSON object with this exact structure:

If an address is found:
```json
{{
  "address_found": true,
  "street": "123 Main St",
  "city": "Minneapolis",
  "state": "MN",
  "zipcode": "55401",
  "country": "US",
  "evidence_indexes": [0, 2]
}}
```

If no address is found:
```json
{{
  "address_found": false,
  "evidence_indexes": []
}}
```

CRITICAL:
- Return ONLY the JSON object, no markdown formatting
- No ```json``` code blocks
- No additional text or explanations
- The JSON must be valid and parseable
- When `address_found` is true, `street`, `city`, and `country` are required. Include state/region and postal code when supported by the evidence.

