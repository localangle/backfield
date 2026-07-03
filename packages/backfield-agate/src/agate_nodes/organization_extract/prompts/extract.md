# Organization Extraction Service

Extract **editorially relevant organizations** from the text at the end of this prompt.

## Organization decision gate

Before adding any row, ask: **Is this a durable institution or organized body of people?**

Extract only when the answer is yes. If the name is primarily a **person, place, law, program, grant, event, award, historical event, work/title, topic, or generic role group**, **omit it** from `organizations`.

Never choose `government` or `other` just because the name acts grammatically in a sentence. A law, park, person, or event is still not an organization.

Paired examples:
- omit `Grant Park`; keep `Grant Park Advisory Council`
- omit `Kenwood`; keep `Kenwood Academy High School`
- omit `Affordable Care Act`; keep `Centers for Medicare and Medicaid Services` when that agency is named and acting
- omit `Grammy Awards`; keep `Recording Academy` when that body is named and acting
- omit `Donald Trump`; keep `Trump administration` only when the administration is the accountable actor
- omit `Area 5 detectives`; keep `Chicago Police Department` or `Chicago Police Department Area 5 Detectives` when the institution is named

## When to extract

Extract a named organization when the article treats it as an **accountable group of people**: employing, announcing, operating, suing, being investigated, regulating, organizing, competing, publishing, deciding, funding, endorsing, or similar.

Require a **specific proper-noun institution** (agency, company, school, team, nonprofit, government body, etc.). Skip generic references without a named institution ("the agency," "police," "school officials") unless the text names the office ("Chicago Police Department," "Cook County State's Attorney's Office").

## Do not extract

- Individual people
- **Named human individuals** — coaches, players, athletes, elected officials, artists, musicians, executives, sources, witnesses, and other people quoted or acting in the story are **people**, not organizations (e.g. `"Bears coach Ben Johnson said…"` → person **Ben Johnson**; **Alice Cooper** on a roster with **Marc Ribot** and **Steve Earle** → people). Extract their **employer, team, or agency** only when **that institution** is the accountable actor in the story—not the person's personal name.
- **Descriptive or relational person phrases** — omit entirely when the text describes a **person's relationship, wealth, or role** rather than naming an institution (e.g. `"billionaire father of Bill Conway"`, `"his brother"`, `"the victim's mother"`). These are not organizations.
- Generic staff or role groups without a named institution ("prosecutors," "coaches," "detectives," `Area 5 detectives`, `Chicago Bulls coach Billy Donovan`)
- Unnamed groups ("residents," "witnesses," "officials")
- Geography-only places (street, city, neighborhood, building, **landmark, monument, region, or area**) unless the story names an **institutional body** that governs or operates there—e.g. omit **Grant Park**, **Kenwood**, **Arc de Triomphe**, **the Chicago area**, **downtown**, **the lakefront**; keep **Evanston City Council**, **Grant Park Advisory Council**
- **Laws, statutes, acts, bills, regulations, programs, grants, and policies** named as rules or coverage topics—not organizations (`Affordable Care Act`, `Administrative Procedure Act`, `Full Service Community Schools grant`, `No Child Left Behind`, `the tax bill`). Extract an **administering agency or department** only when that **institution** is named and acts (`Centers for Medicare and Medicaid Services`, `U.S. Department of Education`)—not the law's title alone
- **Events, awards, competitions, concerts, festivals, parades, games, and historical events** (`Grammy Awards`, `Super Bowl`, `World War I`, `Bud Billiken Day parade`) unless the story names the **organizing institution** (`Recording Academy`, `National Football League`) as the accountable actor
- **Concepts, technologies, industries, and abstract topics** without a named institution (`artificial intelligence`, `climate change`, `inflation`, `social media`)—omit; they are not organizations even when capitalized or central to the story
- Article bylines or publication credits only
- Metonyms without a proper name ("City Hall said" with no named government body)
- Historical, religious, mythological, or fictional entities unless they act as real-world organizations in the story

## Close cousins (brands, works, venues, events)

The same name can be an organization, a brand, a work/title, a venue, or an event. Use context.

**Clear organization** — extract normally when people, management, employees, ownership, policy, statements, lawsuits, layoffs, operations, hiring, closures, or organized activity are in view.

**Omit** — when the name is only incidental product, platform, service, venue, title, event context, **geography, law/policy, grant/program, or abstract topic** and does not matter to the story—or when there is **no accountable group of people** behind the name. For awards, games, concerts, festivals, parades, and historical events, **omit the event name** unless the organizing institution is clearly the actor.

Examples of **omit** (not organizations):
- `"the Affordable Care Act"` / `"ACA health insurance"` → law/program topic; omit (unless a **named agency** is the actor)
- `"Full Service Community Schools grant"` → grant/program topic; omit
- `"around the Arc de Triomphe in Paris"` / `"in Grant Park"` → landmark/geography; omit
- `"Artificial intelligence"` as a story topic → concept; omit
- `"the Chicago area"` → region; omit
- `"Donald Trump"` / `"Bernie Sanders"` → people; omit
- `"Grammy Awards"` / `"Super Bowl"` / `"World War I"` → event/history; omit unless the organizing body is named

**Borderline but editorially relevant** — include the row, use the best normal `type`, and set `organization_boundary` to one of:
- `borderline_brand_platform` — brand/platform/service use may not be organizational ("sent a message on Twitter")
- `borderline_work_title` — column, show, book, film, franchise, publication title, etc. ("Dear Abby answered a reader")
- `borderline_place_business` — business name may be only a location ("the event happened at Baskin Robbins")
- `borderline_event_competition` — use only when an organizing body might exist but context is ambiguous. If the mention is just the event/award/game name (`Grammy Awards`, `Super Bowl`, festival title), **omit** instead of using this boundary.

Do **not** use `other` just because a row is borderline. Omit `organization_boundary` for clear organizations.

Examples:
- "Twitter laid off 20 people" → organization (`company`)
- "Joe sent a message on Twitter" → omit (incidental platform use)
- "AMC announced it would close two theaters" → organization
- "Baskin Robbins employees gathered" → organization (`local_business`)
- "The event happened at Baskin Robbins" → omit unless the business itself matters; if editorially relevant but venue-like, `borderline_place_business`

## Names and types

- Use the most specific conventional proper-noun name.
- `name` must identify an **institution or group**, not an individual human's given and family name (see **Do not extract**). When unsure whether a proper noun is a person or an organization, **omit it from organizations** if the text treats them as an individual acting, speaking, or being described.
- Expand acronyms when known ("National Basketball Association" not "NBA") unless expansion is ambiguous.
- **Schools:** use full school names in scorelines, not bare city tokens ("Brother Rice High School," not "Brother Rice" alone when naming a school institution). **Never** put a bare scoreline token alone in `name` (not `"Belvidere"`, `"Woodstock"`, `"Smith"`, `"Park"`)—expand with your world knowledge to the conventional **full school name** (`Belvidere High School`, `Woodstock High School`, `Smith High School`).
- **Sports teams:** in athletics coverage, bare school/university names usually mean the **team**, not the campus. Use `sports_team` with pattern `[School] [boys|girls|men's|women's] [sport] team` when sport is inferable from the article. Never emit bare "Mount Carmel," "Brother Rice," or "Cubs" alone as `sports_team`. Map nicknames ("Caravan," "Wolverines") to the school team pattern. Use `school`/`university` only when administration, district, or campus policy is the actor—not players, games, recruiting, or championships.
- **Prep scorelines (all formats):** when a token appears in a **game result or schedule**—final scores (`St. Louis Park 57 Hopkins 54`, `Belvidere 55, Woodstock 53`, `Brother Rice 48 Marist 41`), scheduled matchups (`Team A at Team B`), or box-score tables—it names a **school team**, not the homonymous city. **Extract both sides.** Expand each token to the full school name plus team when sport is clear (e.g. `Belvidere 55, Woodstock 53` in basketball coverage → `Belvidere High School boys basketball team`, `Woodstock High School boys basketball team`; not `Belvidere` or `Woodstock` alone, and not `school` when the story is about a game). Use dateline, league, sport section, and nearby context to infer state and sport; apply conventional local school names when you know them.
- **Pro and college teams before player names:** when a team nickname precedes a player, coach, or role descriptor (`Phillies masher Kyle Schwarber`, `Cubs ace`, `Yankees outfielder`), extract the team as `sports_team` using the full conventional name (`Philadelphia Phillies`, `Chicago Cubs`, `New York Yankees`) even if the team is not the grammatical subject of the sentence.
- One record per organization; merge all `mentions`.
- `type` slugs: `government`, `law_enforcement`, `court`, `legislative_body`, `political_party`, `school_district`, `school`, `university`, `hospital`, `public_health`, `public_services`, `utilities`, `company`, `local_business`, `financial_institution`, `real_estate`, `nonprofit`, `community_group`, `religious_org`, `culture_arts`, `sports_team`, `sports_league`, `media`, `other`
- **`other` is not a catch-all.** Use a specific `type` when one clearly fits. Use `other` only for a **named institution** that is genuinely organizational but outside the list (e.g. an unusual membership body with a proper name). If the mention is a **law, place, concept, region, or topic**—or you would choose `other` only because nothing fits—**omit it** from `organizations` instead. Never type a law, landmark, or abstract topic as `government` or `other`.
- `role_in_story`: short plain-language reason it matters
- `nature`: `primary`, `actor`, `source`, `subject`, `affected`, `regulator`, `context`, `other`
- `nature_secondary_tags`: optional 0–2 tags from the same nature vocabulary
- `mentions`: at least one object with `text` (verbatim snippet) and `quote` (true only for direct quotations) per organization. Prefer a full **sentence or paragraph** containing the organization—not the organization name alone unless the name is the entire sentence.

## Output

Return **only** valid JSON. No text before or after the JSON.

## Text to Analyze

{text}
