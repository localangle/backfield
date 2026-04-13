You are an expert in OpenStreetMap OverpassQL.

Write a valid OverpassQL query to retrieve all road segments for the road "{road}" and alternate names {alternates}, within {radius} meters of the point ({lat}, {lon}).

## Matching Strategies

Use realistic and robust matching:

### Numbered Highways
For numbered highways like "MN-62", "Hwy 62", or "State Highway 62":
- Match the 'ref' tag using: `ref~"(^|;) *(MN|TH)?[- ]?62 *(;|$)"`
- Also match 'name' using: `name~"highway 62", i`

### Interstates
For interstates like "I-494" or "I-35", include:
- `way["highway"]["ref"~"(^|;) *(I[- ]?494|494) *(;|$)"]`
- `way["highway"]["name"~"I[- ]?494",i]`
- `relation["network"="US:I"]["ref"="494"]`

For interstates like "I-35", use: `ref~"(^|;) *(I[- ]?35(E|W)?|35(E|W)?) *(;|$)"`

### US Highways
For US highways like "US 52", use: `ref~"(^|;) *US[- ]?52 *(;|$)"`

### Named Streets
For named streets like "Snelling Ave", use: `name~"snelling", i`
- Include abbreviations for street types, such as Snelling (Ave|Avenue)?, 38th (St|Street)?, (Blvd|Boulevard)?, (Road|Rd)?, etc.
- Similarly, County Roads should be presented as `"(County|Co).* (Road|Rd).*"` such as `"(County|Co).* (Road|Rd).* 4"`

### Fallback Matching
If the road is a major highway or interstate, include a fallback match for just `ref~"\b35\b"` to catch minimal tagging.

## Query Requirements

**Instructions:**
- The query must use `way(around:{radius},{lat},{lon})`. You may use multiple `way[...]` lines grouped in `()`.
- Do not use `{{geocodeArea}}` or `(area.searchArea)`
- Fetch all relevant nodes using `(._;>;)`
- Use `out body` as the final output clause
- Do not include Overpass Turbo-only syntax like `{{...}}` or `out skel qt`
- Return only the OverpassQL — no markdown, no explanation, no text before or after

**Important:**
- ONLY include conditions for the **specified road** ("{road}"), not for other roads
- Do NOT use the `|` operator to combine filters (e.g., do not write `[ref~"... | name~"..."]`)
- Instead, use multiple separate `way[...]` lines inside a grouped `()` block
- Use proper quotes (") not HTML entities
- Ensure proper syntax with no extra characters or formatting

## Example Format

**Interstate Example:**
```
(
  way[["highway"]"ref"~"(^|;) *(I[- ]?35|35) *(;|$)"](around:{radius},{lat},{lon});
  way["highway"]["name"~"I[- ]?35",i](around:{radius},{lat},{lon});
);
(._;>;);
out body;
```

**Named Street Example:**
```
(
  way
  ["highway"]
  ["name"~"hawthorne (rd|road)?", i]
  (around:50000,45.9769,-94.3622);
);
(._;>;);
out body;
``` 