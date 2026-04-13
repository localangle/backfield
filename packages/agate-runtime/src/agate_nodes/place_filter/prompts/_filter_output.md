## Output Format

Return a JSON array of judgments with format: `[{{"index": 0, "relevant": true, "reason": "..."}}, ...]`

Each judgment should have:
   - `index`: integer index of the location in the input array
   - `relevant`: boolean indicating if the location should be kept
   - `reason`: string explaining the decision (optional)

Here is an example:

```json
[
  {{
    "index": 0,
    "relevant": true,
    "reason": "This location is directly relevant to the main topic"
  }},
  {{
    "index": 1,
    "relevant": false,
    "reason": "This location is mentioned but not central to the story"
  }}
]
```

Return only the JSON array, no additional text or explanation.
