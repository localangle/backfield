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

**IMPORTANT**: Do not extract generic institutional references without a recognizable name, such as "the agency," "city officials," "police," or "the school district" unless the text names the specific organization (e.g. "Chicago Police Department," "Cook County").

## Who Should NOT Be Included

Do not extract:

- **Individual people** — extract organizations only, never persons
- **Unnamed groups** — "residents," "witnesses," "officials," "employees" without an organization name
- **Places that are only geography** — a street, city, or building name is not an organization unless the story treats it as an institution (e.g. "Wrigley Field" as a venue operated by a named team or authority)
- **Article authors and news outlets** when they appear only as bylines or publication credits for this article
- **Metonyms without a proper name** — "City Hall said" without naming the city government body when only the metonym appears
- **Historical, religious, mythological, or fictional entities** unless they function as real-world organizations in the story's events

## Organization Identification Rules

### 1. Names Required

Use the **most specific conventional name** appearing in the article (e.g. "Chicago Police Department" not only "police"). You may normalize obvious abbreviations when the full name is clear from context.

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
