# Organization Extraction Service

Extract **editorially relevant organizations** from the text at the end of this prompt.

## When to extract

Extract a named organization when the article treats it as an **accountable group of people**: employing, announcing, operating, suing, being investigated, regulating, organizing, competing, publishing, deciding, funding, endorsing, or similar.

Require a **specific proper-noun institution** (agency, company, school, team, nonprofit, government body, etc.). Skip generic references without a named institution ("the agency," "police," "school officials") unless the text names the office ("Chicago Police Department," "Cook County State's Attorney's Office").

## Do not extract

- Individual people
- Generic staff or role groups without a named institution ("prosecutors," "coaches," "detectives")
- Unnamed groups ("residents," "witnesses," "officials")
- Geography-only places (street, city, building) unless the story treats them as institutions
- Article bylines or publication credits only
- Metonyms without a proper name ("City Hall said" with no named government body)
- Historical, religious, mythological, or fictional entities unless they act as real-world organizations in the story

## Close cousins (brands, works, venues, events)

The same name can be an organization, a brand, a work/title, a venue, or an event. Use context.

**Clear organization** — extract normally when people, management, employees, ownership, policy, statements, lawsuits, layoffs, operations, hiring, closures, or organized activity are in view.

**Omit** — when the name is only incidental product, platform, service, venue, title, or event context and does not matter to the story.

**Borderline but editorially relevant** — include the row, use the best normal `type`, and set `organization_boundary` to one of:
- `borderline_brand_platform` — brand/platform/service use may not be organizational ("sent a message on Twitter")
- `borderline_work_title` — column, show, book, film, franchise, publication title, etc. ("Dear Abby answered a reader")
- `borderline_place_business` — business name may be only a location ("the event happened at Baskin Robbins")
- `borderline_event_competition` — named event/competition may not be an organizing body ("Lollapalooza drew 100,000 people")

Do **not** use `other` just because a row is borderline. Omit `organization_boundary` for clear organizations.

Examples:
- "Twitter laid off 20 people" → organization (`company`)
- "Joe sent a message on Twitter" → omit (incidental platform use)
- "AMC announced it would close two theaters" → organization
- "Baskin Robbins employees gathered" → organization (`local_business`)
- "The event happened at Baskin Robbins" → omit unless the business itself matters; if editorially relevant but venue-like, `borderline_place_business`

## Names and types

- Use the most specific conventional proper-noun name.
- Expand acronyms when known ("National Basketball Association" not "NBA") unless expansion is ambiguous.
- **Schools:** use full school names in scorelines, not bare city tokens ("Brother Rice High School," not "Brother Rice" alone when naming a school institution).
- **Sports teams:** in athletics coverage, bare school/university names usually mean the **team**, not the campus. Use `sports_team` with pattern `[School] [boys|girls|men's|women's] [sport] team` when sport is inferable from the article. Never emit bare "Mount Carmel," "Brother Rice," or "Cubs" alone as `sports_team`. Map nicknames ("Caravan," "Wolverines") to the school team pattern. Use `school`/`university` only when administration, district, or campus policy is the actor—not players, games, recruiting, or championships.
- **Pro and college teams before player names:** when a team nickname precedes a player, coach, or role descriptor (`Phillies masher Kyle Schwarber`, `Cubs ace`, `Yankees outfielder`), extract the team as `sports_team` using the full conventional name (`Philadelphia Phillies`, `Chicago Cubs`, `New York Yankees`) even if the team is not the grammatical subject of the sentence.
- One record per organization; merge all `mentions`.
- `type` slugs: `government`, `law_enforcement`, `court`, `legislative_body`, `political_party`, `school_district`, `school`, `university`, `hospital`, `public_health`, `public_services`, `utilities`, `company`, `local_business`, `financial_institution`, `real_estate`, `nonprofit`, `community_group`, `religious_org`, `culture_arts`, `sports_team`, `sports_league`, `media`, `other`
- `role_in_story`: short plain-language reason it matters
- `nature`: `primary`, `actor`, `source`, `subject`, `affected`, `regulator`, `context`, `other`
- `nature_secondary_tags`: optional 0–2 tags from the same nature vocabulary
- `mentions`: at least one object with `text` (verbatim snippet) and `quote` (true only for direct quotations) per organization

## Output

Return **only** valid JSON. No text before or after the JSON.

## Text to Analyze

{text}
