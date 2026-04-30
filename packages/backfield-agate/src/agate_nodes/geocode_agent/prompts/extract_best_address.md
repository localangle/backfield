# Best Address Extraction and Parsing

Given the following search query and search results, identify and return the single most accurate physical address that best answers the query. Parse the address into structured components.

## Requirements

- If no address is available, or you are not fully confident in the address, return `{{"address_found": false}}`
- Otherwise, parse the address into components and return as JSON
- Use the original text context to help identify the correct location when multiple results are present

## Input

**Original Text:** {original_text}

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
  "country": "US"
}}
```

If no address is found:
```json
{{
  "address_found": false
}}
```

CRITICAL:
- Return ONLY the JSON object, no markdown formatting
- No ```json``` code blocks
- No additional text or explanations
- The JSON must be valid and parseable
- All fields except address_found are optional (omit if not available)

