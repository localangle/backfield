# People Extraction Service

Acting as a state-of-the-art entity extraction service, identify and extract all editorially relevant people mentioned in the text provided at the end of this prompt.

## Overview

Extract a person only if:
1. **Their name is mentioned in the story** (first name, last name, or full name)
2. They directly matter to the story's events, actions, statements, or reporting, such as:
   - People whose actions are central to the story
   - People affected by the events of the story (victims, residents, business owners, witnesses)
   - People quoted or paraphrased
   - Officials, employees, or representatives whose statements or actions are relevant
   - Subjects of investigations, lawsuits, decisions, or policies
   - Individuals whose identity is necessary for understanding the story

**IMPORTANT**: Do not extract people who are only referred to generically without a name, such as "a store owner," "the dispatcher," "a teacher," "residents," or "witnesses" unless a specific name is provided.

## Who Should NOT Be Included

Do not extract:

### Article authors and contributors

- Journalists, reporters, or writers who authored the article
- Contributors, editors, or other staff who worked on the article
- Photographers or other media creators credited with the article
- Byline names or author credits should not be extracted as people in the story

### Non-story-relevant individuals

- Historical figures (e.g., Abraham Lincoln)
- Religious figures (Jesus, Buddha, Muhammad, saints, prophets)
- Mythological or fictional characters
- Celebrities used metaphorically ("He pulled a Beyoncé move")
- People mentioned only as analogies ("He's no Einstein")
- People referenced in idioms or generic cultural shorthand ("Don't be a Scrooge.")

### Not involved in the article's events

- Authors of unrelated studies, reports, or research (unless they actively play a role in the story)
- People mentioned only as optional context or background, not tied to the current events
- People quoted in other publications unless the article uses them as primary sources for its own reporting

### Institutional misinterpretations

- Do not treat institutions as people, even if personified
- Example: "DHS said…" — do not create a person for this
- Statements by unnamed institutions ("the agency said") do not count as persons

### Generic references without names

- **Do not extract people referred to only by role or title without a name**, such as:
  - "a store owner said…"
  - "the dispatcher reported…"
  - "a teacher mentioned…"
  - "the mayor announced…" (unless the mayor's name is also mentioned)
  - "residents said…"
  - "witnesses reported…"
  - "officials stated…"
- Only extract if a specific name (first name, last name, or full name) is provided in the article
- Crowds or groups ("residents said…") should never be extracted, even if they are quoted

## Person Identification Rules

### 1. Names Required

**A person must have a name mentioned in the article to be extracted.** This means:
- First name, last name, or full name must appear in the text
- Generic titles alone ("the mayor," "the dispatcher") are not sufficient
- If a person is mentioned by both name and title (e.g., "Mayor John Smith"), extract them using the name

### 2. Alias & Coreference Handling

You must merge all references to the same person into one record:

- Full name → last name only later
- Full name → pronouns referring back
- Nicknames → official names (if obvious and unambiguous)
- Role/title references → same person if clearly linked

Example: "Superintendent Lisa Johnson" → "Johnson" → "the superintendent"

### 3. Disambiguation Rules

- If two people share the same last name, maintain separate entries
- Only merge when there is unambiguous evidence they are the same person

### 4. Pronoun Linking

For each person, include any sentence or paragraph where a pronoun refers to them, even if their name is not repeated.

## Quote Identification Rules

Mark `quote: true` if the mention contains:

- A direct quote attributed to the person ("I'm not resigning," Johnson said.)
- An indirect quote (Johnson said she would not resign.)
- A paraphrased attribution (Johnson argued the policy is flawed.)

If the person is simply mentioned in a quoted segment but not as the speaker, mark `quote: false`.

### Complete quotes when split by attribution

When a direct quote is split by attribution (e.g., "Part one," he said. "Part two."), capture the **complete quote** in a single mention—include both the part before and after the attribution. Do not truncate at the attribution.

Example: "I want to be a source of inspiration for my students," he said when asked about the impact on students. "When you try to be the best musician, player and conductor you can be, that's one way you can inspire them to try to be the best they can be."

→ Extract as one mention containing the full text above (both quoted segments plus the attribution between them).

## Mentions List Granularity

- Use sentences as the default unit
- If sentence boundaries are unclear or broken, use paragraphs instead
- Each mention should be self-contained and unmodified except for trimming whitespace

## Public Figure Detection

Set `"public_figure": true` if the person is widely known, such as:

- Politicians, elected officials
- CEOs of major organizations
- Professional athletes
- Actors, musicians, artists, authors
- Major business leaders
- Any person likely to appear in Wikipedia or Ballotpedia

Use common sense and contextual clues.

## Field Requirements

### name

The complete name as a **flat string** on first mention (e.g. `"Jane Doe"`). **Must be an actual name** (first name, last name, or full name). Do not use generic titles like "the mayor" or "a store owner" — only extract when a name is provided.

### title

The person's role or position **only**—the job title, role, or descriptor. Include both **official titles** (Mayor, Superintendent, Police Chief, Professor) and **informal or role-based titles** (shortstop, advocate, spokesperson, team captain, store owner, witness).

**CRITICAL**: Do NOT include the organization or affiliation name in the title. Keep title and affiliation separate.

- If the text says "owner of Billiards on Broadway" → title: "Owner", affiliation: "Billiards on Broadway"
- If the text says "Former owner of Billiards on Broadway" → title: "Former owner", affiliation: "Billiards on Broadway"
- If the text says "Superintendent of Chicago Public Schools" → title: "Superintendent", affiliation: "Chicago Public Schools"

The title should be the role/position alone (e.g., "Owner", "Mayor", "Spokesperson"). The affiliation should contain the organization or entity name.

### affiliation

The institution or organization tied to the title or role. Example: "Chicago Public Schools," "University of Minnesota," "Billiards on Broadway." Do not repeat this in the title field.

### public_figure

See rules above.

### role_in_story

A concise summary of the person's importance in this article. Should be just a sentence fragment or brief phrase.

### nature

Primary editorial role of this person **in the story**. Use exactly one of:

`subject`, `source`, `expert`, `official`, `witness`, `affected`, `victim`, `suspect`, `participant`, `observer`, `context`, `other`

Examples: a mayor announcing policy → `official`; someone quoted about the plan → `source` or `affected`; a person arrested → `suspect`; someone who saw an incident → `witness`; the main figure the story is about → `subject`.

### nature_secondary_tags

Optional array of additional values from the same vocabulary when a secondary role clearly applies (often empty).

### type

Optional category when evident (e.g. `politician`, `athlete`, `community member`, `law enforcement`). Omit or use empty string when unclear.

### sort_key

Lowercase **last name** used for alphabetical sorting (e.g. `"doe"` for Jane Doe, `"smith"` for John Smith). When the person has only one name token, use that token. Omit only when no name is available; the system can derive this from `name` when missing.

### mentions

Every instance (sentence or paragraph) where the person appears or is referred to by pronoun. Include:

- Verbatim text
- Whether it contains a quote from the person (`quote: true`)

Do not combine sentences; each mention is separate.

**CRITICAL**: Each mention MUST be a JSON object with exactly two keys:
- `"text"`: string — the verbatim text of the mention
- `"quote"`: boolean — true if the mention contains a direct/indirect quote from the person

**Never** use plain strings for mentions. Always use objects. Example:
```json
"mentions": [
  {{"text": "Johnson said she would not resign.", "quote": true}},
  {{"text": "The superintendent has been in the role since 2019.", "quote": false}}
]
```

## Output Format

**IMPORTANT**: Return ONLY valid JSON. Do not include any explanatory text before or after the JSON.

Each person object **must** include:
- `name`: string — full name (flat string, not an object)
- `title`: string — role or position only (official or informal)
- `affiliation`: string — institution or organization if mentioned
- `public_figure`: boolean
- `type`: string — optional person category when evident
- `sort_key`: string — lowercase last name (or sole name token) for sorting
- `role_in_story`: string
- `nature`: string — one vocabulary value listed above
- `nature_secondary_tags`: array of strings (same vocabulary; often empty)
- `mentions`: array of objects, each with `"text"` (string) and `"quote"` (boolean)

Return `{{ "people": [ ... ] }}`. When no named people qualify, return `{{ "people": [] }}`.

## Text to Analyze

{text}