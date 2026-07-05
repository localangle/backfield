# Organization Extraction Service

Extract **editorially relevant organizations** from the text at the end of this prompt.

## Organization decision gate

Before adding any row, ask: **Is this a durable institution or organized body of people?**

Extract only when the answer is yes. If the name is primarily a **person, place, law, program, grant, fund, event, award, historical event, film/performance/show title, publication or survey title, landmark or building, broad social descriptor, work/title, topic, or generic role group**, **omit it** from `organizations`.

Require a **specific proper-noun institution**—not a broad descriptor, demographic phrase, or generic category label (`American civil society`, `Arizona families`, `Arizona grand jury`).

Never choose `government` or `other` just because the name acts grammatically in a sentence. A law, park, person, film title, or event is still not an organization.

Paired examples:
- omit `Grant Park`; keep `Grant Park Advisory Council`
- omit `Kenwood`; keep `Kenwood Academy High School`
- omit `Affordable Care Act`; keep `Centers for Medicare and Medicaid Services` when that agency is named and acting
- omit `Anti-Weaponization Fund`; keep the **administering agency or office** only when that institution is named and acting
- omit `Grammy Awards`; keep `Recording Academy` when that body is named and acting
- omit `Donald Trump`, `Antonio Martínez Ocasio`, `Ayo Dosunmu`; keep `Trump administration` only when the administration is the accountable actor
- omit `Area 5 detectives`; keep `Chicago Police Department` or `Chicago Police Department Area 5 Detectives` when the institution is named
- omit `A Mighty Wind`, `Angelo, My Love`; keep a **named production company, studio, or presenter** only when that institution is the actor
- omit `American Community Survey`; keep `U.S. Census Bureau` when that agency is named and acting
- omit `Anne Frank House`, `Arc de Triomphe`; keep a **named museum foundation or operating institution** only when that body is the actor—not the landmark name alone
- omit `American civil society`, `Arizona families`, `Arizona grand jury`; keep a **named office, agency, or committee** only when the institution is explicit
- omit `Budweiser`, `Google`, `Twitter` as bare **consumer brand or product** names; keep **`Budweiser employees union`**, **`Google executive team`**, or a **named corporate entity** only when that organized body is explicit and acting
- omit `Pearl Jam`, `The Beatles`, `Alice Cooper` (as the act); those are **bands or musical acts**—extract as **people**, not organizations

## When to extract

Extract a named organization when the article treats it as an **accountable group of people**: employing, announcing, operating, suing, being investigated, regulating, organizing, competing, publishing, deciding, funding, endorsing, or similar.

Require a **specific proper-noun institution** (agency, company, school, team, nonprofit, government body, etc.). Skip generic references without a named institution ("the agency," "police," "school officials") unless the text names the office ("Chicago Police Department," "Cook County State's Attorney's Office").

## Do not extract

- **Consumer brands, products, and platforms** named alone—not organizations (`Budweiser`, `Google`, `Coca-Cola`, `Twitter` as incidental platform use). Extract a **named union, division, executive group, subsidiary, or corporate entity** only when that **organized body** is explicit (`Budweiser employees union`, `Google executive team`, `Alphabet Inc.` when the company is the actor)—not the bare brand name alone
- **Musical groups, bands, and recording acts** (`Pearl Jam`, `The Beatles`, `Alice Cooper` when referring to the act)—extract as **people**, not organizations
- Individual people
- **Named human individuals** — coaches, players, athletes, elected officials, artists, musicians, actors, executives, sources, witnesses, and other people quoted or acting in the story are **people**, not organizations (e.g. `"Bears coach Ben Johnson said…"` → person **Ben Johnson**; **Alice Cooper** on a roster with **Marc Ribot** and **Steve Earle** → people; **Antonio Martínez Ocasio**, **Ayo Dosunmu** → people). Extract their **employer, team, or agency** only when **that institution** is the accountable actor in the story—not the person's personal name.
- **Descriptive or relational person phrases** — omit entirely when the text describes a **person's relationship, wealth, or role** rather than naming an institution (e.g. `"billionaire father of Bill Conway"`, `"his brother"`, `"the victim's mother"`). These are not organizations.
- Generic staff or role groups without a named institution ("prosecutors," "coaches," "detectives," `Area 5 detectives`, `Chicago Bulls coach Billy Donovan`)
- Unnamed groups ("residents," "witnesses," "officials")
- Geography-only places (street, city, neighborhood, building, **landmark, monument, historic site, museum building, region, or area**) unless the story names an **institutional body** that governs or operates there—e.g. omit **Grant Park**, **Kenwood**, **Arc de Triomphe**, **Anne Frank House**, **the Chicago area**, **downtown**, **the lakefront**; keep **Evanston City Council**, **Grant Park Advisory Council**
- **Films, performances, shows, albums, books, and other creative works** named as titles—not organizations (`A Mighty Wind`, `Angelo, My Love`, `Hamilton`, `The Daily Show` as a program title). Extract a **named studio, network, production company, or presenter** only when that institution is the accountable actor—not the title alone
- **Publications, surveys, reports, and datasets** named as titles or products—not organizations (`American Community Survey`, `Consumer Price Index`, `Statistical Abstract`). Extract the **publishing agency, bureau, or company** only when that institution is named and acting
- **Broad descriptors and generic social categories** that are not proper-noun institutions (`American civil society`, `Arizona families`, `Arizona grand jury`, `local residents`, `the business community`). These are topics or groups, not organizations—omit unless a **named institution** is explicit
- **Laws, statutes, acts, bills, regulations, programs, grants, funds, and policies** named as rules or coverage topics—not organizations (`Affordable Care Act`, `Administrative Procedure Act`, `Anti-Weaponization Fund`, `Full Service Community Schools grant`, `No Child Left Behind`, `the tax bill`). Extract an **administering agency or department** only when that **institution** is named and acts (`Centers for Medicare and Medicaid Services`, `U.S. Department of Education`)—not the law, program, or fund title alone
- **Events, awards, competitions, concerts, festivals, parades, games, and historical events** (`Grammy Awards`, `Super Bowl`, `World War I`, `Bud Billiken Day parade`) unless the story names the **organizing institution** (`Recording Academy`, `National Football League`) as the accountable actor
- **Concepts, technologies, industries, and abstract topics** without a named institution (`artificial intelligence`, `climate change`, `inflation`, `social media`)—omit; they are not organizations even when capitalized or central to the story
- Article bylines or publication credits only
- Metonyms without a proper name ("City Hall said" with no named government body)
- Historical, religious, mythological, or fictional entities unless they act as real-world organizations in the story

## Close cousins (brands, works, venues, events)

The same name can be an organization, a brand, a work/title, a venue, or an event. Use context.

**Clear organization** — extract normally when people, management, employees, ownership, policy, statements, lawsuits, layoffs, operations, hiring, closures, or organized activity are in view—and the text names an **organized body**, not just a **brand** (`Budweiser employees union`, `Google executive team`, `Twitter laid off 20 people` when Twitter-the-company is acting).

**Omit** — when the name is only a **consumer brand or product** with no accountable group (`Budweiser`, `Google`, `Coca-Cola`); incidental platform, service, venue, title, event context, **geography, law/policy, grant/program, or abstract topic**; or when there is **no accountable group of people** behind the name. **Musical bands and acts** belong in **people** extraction, not here. For awards, games, concerts, festivals, parades, and historical events, **omit the event name** unless the organizing institution is clearly the actor.

Examples of **omit** (not organizations):
- `"Budweiser"` / `"Google"` / `"Coca-Cola"` as brand or product references → omit (not `"Budweiser"` as `company`)
- `"Pearl Jam"` / `"The Rolling Stones"` / `"Alice Cooper"` (the act) → band; omit from organizations (people extraction)
- `"the Affordable Care Act"` / `"ACA health insurance"` → law/program topic; omit (unless a **named agency** is the actor)
- `"Anti-Weaponization Fund"` / `"Full Service Community Schools grant"` → fund/program topic; omit
- `"American Community Survey"` → publication/survey title; omit (unless **U.S. Census Bureau** or similar agency is the actor)
- `"A Mighty Wind"` / `"Angelo, My Love"` → film or performance title; omit
- `"Anne Frank House"` / `"around the Arc de Triomphe in Paris"` / `"in Grant Park"` → landmark/site/geography; omit
- `"American civil society"` / `"Arizona families"` / `"Arizona grand jury"` → broad descriptor, not a proper-noun institution; omit
- `"Artificial intelligence"` as a story topic → concept; omit
- `"the Chicago area"` → region; omit
- `"Donald Trump"` / `"Bernie Sanders"` / `"Antonio Martínez Ocasio"` / `"Ayo Dosunmu"` → people; omit
- `"Grammy Awards"` / `"Super Bowl"` / `"World War I"` → event/history; omit unless the organizing body is named

Examples of **keep** (organizations):
- `"Budweiser employees union"` → organization (named union/body)
- `"Google executive team"` → organization (named executive group)
- `"Twitter laid off 20 people"` → organization (`company`) when the corporate actor is clear

**Borderline but editorially relevant** — include the row, use the best normal `type`, and set `organization_boundary` to one of:
- `borderline_brand_platform` — only when a **named corporate or platform entity** is acting but context is ambiguous (not a bare consumer brand with no organized body)
- `borderline_work_title` — column, show, book, film, franchise, publication title, etc. ("Dear Abby answered a reader")
- `borderline_place_business` — business name may be only a location ("the event happened at Baskin Robbins")
- `borderline_event_competition` — use only when an organizing body might exist but context is ambiguous. If the mention is just the event/award/game name (`Grammy Awards`, `Super Bowl`, festival title), **omit** instead of using this boundary.

Do **not** use `other` just because a row is borderline. Omit `organization_boundary` for clear organizations.

Examples:
- "Twitter laid off 20 people" → organization (`company`)
- "Joe sent a message on Twitter" → omit (incidental platform use)
- "Budweiser employees union voted to strike" → organization
- "Budweiser" as a product mention only → omit
- "Google executive team announced layoffs" → organization
- "Google" as a search engine reference only → omit
- "AMC announced it would close two theaters" → organization
- "The event happened at Baskin Robbins" → omit unless the business itself matters; if editorially relevant but venue-like, `borderline_place_business`

## Names and types

- Use the most specific conventional proper-noun name.
- `name` must identify an **institution or group**, not an individual human's given and family name (see **Do not extract**). A label must be a **proper-noun institution**, not a broad descriptor (`American civil society`), fund/program title (`Anti-Weaponization Fund`), publication/survey title (`American Community Survey`), landmark (`Anne Frank House`), or creative-work title (`A Mighty Wind`). When unsure whether a proper noun is a person or an organization, **omit it from organizations** if the text treats them as an individual acting, speaking, or being described.
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
