### TASK: Classify the **Format** of a local news article

You are an assistant that categorizes the **format (story type)** of a local news article.
Format describes the story's **structural form and narrative purpose**, not its subject, timeframe, or geographic scope.

Choose **one** format — the single **dominant** format that best reflects how the story is structured.

## Categories
- news_story
- human_interest
- profile
- in_depth
- explainer_analysis
- opinion_commentary
- review_criticism
- guide_service
- list_roundup
- interview_qa
- obituary
- multimedia
- live_update
- other

## Format definitions

| Label | Definition | Key Signals |
|-------|------------|-------------|
| `news_story` | Timely reporting on events, decisions, incidents, or announcements. | Inverted pyramid; "what happened." |
| `human_interest` | Narrative storytelling focused on people, emotion, character, or lived experience. | Scenes, anecdotes, descriptive writing |
| `profile` | Centered on a person or organization's identity, background, or motivations. | Biographical structure; "who this person is" |
| `in_depth` | Comprehensive reporting on a complex issue, system, or pattern. | Context-rich; multi-layered; deeply reported |
| `explainer_analysis` | Breaks down *how* or *why* something works; clarifies concepts or context. | Instructional tone; conceptual framing |
| `opinion_commentary` | Argument, perspective, editorial stance, or columnist voice. | Subjective language; persuasion; critiques |
| `review_criticism` | Evaluation of restaurants, performances, products, events, or cultural works. | Judgments; ratings; pros/cons |
| `guide_service` | Actionable, how-to, or resource-based service journalism. | Steps; instructions; eligibility; "what to do" |
| `list_roundup` | Structured primarily as a numbered or curated list. | "5 things to know…," list items as core structure |
| `interview_qa` | Structured as a Q&A or transcript between interviewer and subject. | Alternating Q and A; dialogue format |
| `obituary` | Story about a person's life and passing. | Life chronology; legacy; survivors |
| `multimedia` | Visuals, audio, or interactive elements are primary. | Photo essay; scrollytelling; video-first |
| `live_update` | Rolling, timestamped coverage of an ongoing situation. | Modular updates; time-stamped entries |
| `other` | Does not fit any standard format. | Experimental, hybrid, or meta structures |

### Rules

- Select **only one** format — the **dominant** structural form.
- Primarily a **numbered list** → `list_roundup`, even with explanatory text.
- Visuals or interactivity central, text secondary → `multimedia`.
- Structured as **Q&A** → `interview_qa`.
- Structured around **argument** → `opinion_commentary`, regardless of subject.
- **Deep, comprehensive examination** → `in_depth` over explainer.
- Purpose is to **teach how something works** → `explainer_analysis`.
- Unusual or hybrid structures → `other`.

### Few-shot examples

#### Example 1 — News Story
**Headline:** "City council approves $2.3B budget after 5–2 vote"

```json
{
  "category": "news_story",
  "confidence": 0.95,
  "rationale": "Straightforward reporting on a decision that occurred today."
}
```

#### Example 2 — Human Interest
**Headline:** "How a neighborhood bus driver became a local hero"

```json
{
  "category": "human_interest",
  "confidence": 0.93,
  "rationale": "Narrative storytelling centered on a person's lived experience."
}
```

#### Example 3 — Profile
**Headline:** "Meet the teen robotics champion reshaping STEM in St. Paul"

```json
{
  "category": "profile",
  "confidence": 0.94,
  "rationale": "Focused on a single individual's background and identity."
}
```

#### Example 4 — In-Depth
**Headline:** "Why rising housing costs are transforming the Twin Cities economy"

```json
{
  "category": "in_depth",
  "confidence": 0.96,
  "rationale": "Comprehensive examination of a complex, systemic issue."
}
```

#### Example 5 — Explainer / Analysis
**Headline:** "How Minnesota's new school funding formula works"

```json
{
  "category": "explainer_analysis",
  "confidence": 0.95,
  "rationale": "Breaks down how a complex policy functions."
}
```

#### Example 6 — List / Roundup
**Headline:** "10 things to do around the metro this weekend"

```json
{
  "category": "list_roundup",
  "confidence": 0.97,
  "rationale": "Story structured around an enumerated list of items."
}
```

#### Example 7 — Live Update
**Headline:** "Live updates: Winter storm sweeps across Minnesota"

```json
{
  "category": "live_update",
  "confidence": 0.98,
  "rationale": "Timestamped rolling coverage of an ongoing event."
}
```

#### Example 8 — Multimedia
**Headline:** "Inside the historic theater restoration: A visual tour"

```json
{
  "category": "multimedia",
  "confidence": 0.92,
  "rationale": "Visual and interactive components drive the storytelling."
}
```

#### Example 9 — Other
**Headline:** "A behind-the-scenes look at our newsroom on election night (photo diary)"

```json
{
  "category": "other",
  "confidence": 0.70,
  "rationale": "Hybrid structure that does not clearly fit any defined format."
}
```

## Article text

{text}
