# Organization Extraction Service

Acting as a state-of-the-art entity extraction service, identify and extract all **editorially relevant organizations** mentioned in the text provided at the end of this prompt.

## Overview

Extract an organization only if:

1. **A specific named organization is mentioned** (agency, company, school, team, nonprofit, government body, etc.)
2. It matters to the story's events, actions, statements, or reporting, such as:
   - Organizations whose actions or decisions are central to the story
   - Organizations quoted or paraphrased as sources
   - Organizations affected by or regulating the events
   - Employers, institutions, or agencies tied to named people **when the organization itself is editorially relevant** (not only as a person's affiliation shorthand)

**IMPORTANT**: Do not extract generic institutional references without a recognizable proper-noun institution, such as "the agency," "city officials," "police," or "the school district" unless the text names the specific organization (e.g. "Chicago Police Department," "Cook County State's Attorney's Office").

## Who Should NOT Be Included

Do not extract:

- **Individual people** — extract organizations only, never persons
- **Generic role or staff groups without a proper institution name** — e.g. "Cook County prosecutors" when the story means prosecutors as a group, not a named office; "detectives," "prosecutors," "coaches" without naming the agency, department, or office
- **Unnamed groups** — "residents," "witnesses," "officials," "employees" without an organization name
- **Places that are only geography** — a street, city, or building name is not an organization unless the story treats it as an institution (e.g. "Wrigley Field" as a venue operated by a named team or authority)
- **Article authors and news outlets** when they appear only as bylines or publication credits for this article
- **Metonyms without a proper name** — "City Hall said" without naming the city government body when only the metonym appears
- **Historical, religious, mythological, or fictional entities** unless they function as real-world organizations in the story's events

## Organization Identification Rules

### 1. Names Required

Use the **most specific conventional proper-noun name** for each organization. Organizations are generally **proper nouns** naming a specific institution—not a generic role, profession, or unnamed subset of people.

- **Include** named institutions: "Chicago Police Department," "Cook County State's Attorney's Office," "Brother Rice High School"
- **Exclude** functional or generic phrases without a proper institution: "Cook County prosecutors" (prosecutors as a group), "police said" without naming the department, "school officials"
- **Include** when the text names the office or agency even if phrased functionally: "Cook County Prosecutor's Office," "the Minneapolis Park Board"

#### Expand acronyms and abbreviations

When the full conventional name is known or clearly inferable, use the **expanded form** in `name`, not the acronym alone.

- "National Basketball Association" not "NBA"
- "Federal Bureau of Investigation" not "FBI"
- "National Collegiate Athletic Association" not "NCAA"

Keep the article's form only when expansion is ambiguous or the acronym is the story's established proper name with no clear expansion.

#### High schools and campuses

Use the same **school naming** logic as PlaceExtract:

- Return the **full conventional school name** when inferable from context or general knowledge—not a bare city-like token or scoreline shorthand
- In **scorelines and game summaries** (e.g. "St. Louis Park 57 Hopkins 54"), short tokens name **school institutions**, not the homonymous city. Prefer **Brother Rice High School**, **St. Louis Park High School**, **Hopkins High School** (or the best-known formal name), not "Brother Rice," "St. Louis Park," or "Hopkins" alone
- When story shorthand clearly means a school (e.g. "Park" for St. Louis Park High School, "Crete-Monee" for Crete-Monee High School), return the **complete school name**

Set `type` to `school` for the institution; use `sports_team` when extracting the athletic program (see below).

#### Prep and college sports teams

When the story refers to a **high school or college sports team**, build `name` to include **school (full name when possible), sport, and gender or level** whenever they can be inferred—do not emit only the school short name.

- "Mt. Carmel football team" not "Mt. Carmel"
- "Brother Rice boys basketball team" not "Brother Rice"
- "Hopkins girls soccer team" not "Hopkins"
- "University of Minnesota men's hockey team" not "Minnesota" or "the Gophers" unless the mascot is the only proper name given and sport/level cannot be inferred

Set `type` to `sports_team` for these athletic programs.

### 2. One Record Per Organization

If the same organization appears multiple times, emit **one** object with **all** supporting `mentions` snippets.

### 3. Type Classification

Set `type` to one of these slugs (use `other` when none fit):

`government`, `law_enforcement`, `court`, `legislative_body`, `political_party`, `school_district`, `school`, `university`, `hospital`, `public_health`, `public_services`, `utilities`, `company`, `local_business`, `financial_institution`, `real_estate`, `nonprofit`, `community_group`, `religious_org`, `culture_arts`, `sports_team`, `sports_league`, `media`, `other`

### 4. Role and Nature

- **`role_in_story`**: Short phrase describing why this organization matters in the article (plain language, not codes).
- **`nature`**: Primary editorial role — one of: `primary`, `actor`, `source`, `subject`, `affected`, `regulator`, `context`, `other`
- **`nature_secondary_tags`**: Optional list of additional nature values from the same vocabulary (usually 0–2 tags).

### 5. Mentions

Each organization must include a `mentions` array with at least one object containing:

- `text` — verbatim snippet from the article
- `quote` — `true` only when the snippet is a direct quotation attributed to the organization or its representative; otherwise `false`

## Output Format

**IMPORTANT**: Return ONLY valid JSON. Do not include explanatory text before or after the JSON.

## Text to Analyze

{text}
