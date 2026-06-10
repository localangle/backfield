### TASK: Classify the **Timeframe** of a local news article

You are an assistant that categorizes a story's **timeframe** — its primary temporal orientation.
The timeframe describes **how the story relates to time**: future, present, past, ongoing trends, recurring cycles, or timeless relevance.

Choose the **single dominant timeframe** that best reflects the story's focus.

## Categories
- future
- present
- past
- ongoing
- cyclical
- evergreen
- other

## Timeframe definitions

| Label | Definition | Key Signals |
|-------|------------|-------------|
| `future` | Oriented toward events, decisions, or conditions that **have not yet happened**. | Upcoming votes, deadlines, forecasts, planned policies |
| `present` | Centered on something **happening now** or **just happened** in a non-breaking way. | Meeting summaries, same-day coverage, immediate reactions |
| `past` | Looks **backward** at events that already happened — consequences, analysis, or reflection. | Anniversaries, impact reporting, retrospective pieces |
| `ongoing` | Covers a **durational phenomenon** without a single defining event. | Trends, crises, demographic shifts, persistent problems |
| `cyclical` | Concerns **recurring or seasonal patterns** on a predictable cadence. | Annual events, seasonal tips, school-year cycles |
| `evergreen` | **Not tied to any timeframe**; remains relevant whenever it is read. | How-tos, foundational explainers, general education |
| `other` | No clear temporal orientation, or mixed timeframes obscure the dominant one. | Meta coverage, behind-the-scenes pieces |

### Rules

- Primary orientation is **the future** → `future`, even with past context.
- **Recent event** → `present`.
- **Consequences or reflections** → `past`, even if new facts appear.
- **Trend**, not a moment → `ongoing`.
- **Seasonal or recurring cycles** → `cyclical`, not evergreen.
- **Useful anytime** → `evergreen`.
- No clear fit → `other`.

### Few-shot examples

#### Example 1 — Future
**Headline:** "What to expect as the city prepares to vote on a new zoning plan next week"

```json
{
  "category": "future",
  "confidence": 0.94,
  "rationale": "The story is oriented toward a vote that has not yet happened."
}
```

#### Example 2 — Present
**Headline:** "City council approves $2.3B budget after 5–2 vote"

```json
{
  "category": "present",
  "confidence": 0.95,
  "rationale": "Describes an event that happened today with immediate relevance."
}
```

#### Example 3 — Past
**Headline:** "A year after the floods, residents are still rebuilding"

```json
{
  "category": "past",
  "confidence": 0.96,
  "rationale": "Reflects on the long-term consequences of a previous event."
}
```

#### Example 4 — Ongoing
**Headline:** "Rising housing costs continue to reshape the metro area"

```json
{
  "category": "ongoing",
  "confidence": 0.93,
  "rationale": "Focuses on a long-term trend not tied to a specific moment."
}
```

#### Example 5 — Cyclical
**Headline:** "Your guide to staying safe during icy sidewalk season"

```json
{
  "category": "cyclical",
  "confidence": 0.90,
  "rationale": "Information tied to a recurring seasonal pattern."
}
```

#### Example 6 — Evergreen
**Headline:** "How to contest your property tax assessment"

```json
{
  "category": "evergreen",
  "confidence": 0.95,
  "rationale": "Relevant regardless of timing and not tied to any event or cycle."
}
```

#### Example 7 — Other
**Headline:** "A day in the life inside our newsroom during election night (photo diary)"

```json
{
  "category": "other",
  "confidence": 0.72,
  "rationale": "Meta, behind-the-scenes structure that does not map cleanly to temporal orientation."
}
```

## Article text

{text}
