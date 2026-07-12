# Organization Extraction Service

Extract every editorially relevant **organization** named in the news text at the end of this prompt. Return only valid JSON.

An organization is relevant when the article treats it as an **accountable group of people**: employing, announcing, operating, suing, being investigated, regulating, organizing, competing, publishing, deciding, funding, or endorsing.

## Hard stops — the organization test

Apply this test to **every row before you emit it**: *is `name` a durable institution or organized body of people, named as a specific proper noun?* If not — or if you are unsure — **omit the row**. A missing row is always better than an organization record for a person, place, law, event, or topic. Never choose `government` or `other` just because a name acts grammatically in a sentence.

Never emit as `organizations.name`:

| Category | Examples | Keep instead (only when named and acting) |
|----------|----------|-------------------------------------------|
| Individual people | `Donald Trump`, `Ayo Dosunmu`, `Bears coach Ben Johnson`, `billionaire father of Bill Conway`, `his brother` | Their employer, team, or agency when **that institution** is the actor |
| Bands and musical acts | `Pearl Jam`, `The Beatles`, `Alice Cooper` (the act) | Nothing — bands belong in **people** extraction |
| Consumer brands or products alone | `Budweiser`, `Google`, `Coca-Cola`, `Twitter` as incidental platform use | `Budweiser employees union`, `Google executive team`, `Twitter` when the company itself acts (layoffs, lawsuits) |
| Laws, programs, grants, funds, policies | `Affordable Care Act`, `Anti-Weaponization Fund`, `Full Service Community Schools grant`, `No Child Left Behind` | The administering agency (`Centers for Medicare and Medicaid Services`, `U.S. Department of Education`) |
| Events, awards, games, historical events | `Grammy Awards`, `Super Bowl`, `World War I`, `Bud Billiken Day parade` | The organizing body (`Recording Academy`, `National Football League`) |
| Creative works and titles | `A Mighty Wind`, `Hamilton`, `The Daily Show` (the program) | The named studio, network, production company, or presenter |
| Publications, surveys, datasets | `American Community Survey`, `Consumer Price Index`, `Statistical Abstract` | The publishing agency (`U.S. Census Bureau`) |
| Geography, landmarks, venues | `Grant Park`, `Kenwood`, `Anne Frank House`, `Arc de Triomphe`, `the Chicago area`, `downtown` | The governing or operating body (`Grant Park Advisory Council`, `Kenwood Academy High School`) |
| Broad descriptors and role groups | `American civil society`, `Arizona families`, `Arizona grand jury`, `prosecutors`, `Area 5 detectives`, `residents`, `officials` | A named office or department (`Chicago Police Department`) |
| Generic public-service groups or laws with geography | `Illinois police departments`, `Illinois DMVs`, `Illinois state law`, `state courts`, `local schools` | A specific named body (`Chicago Police Department`, `Illinois Secretary of State`, `Illinois Supreme Court`) |
| Concepts, industries, topics | `artificial intelligence`, `climate change`, `inflation`, `social media` | Nothing — even when capitalized or central to the story |
| Metonyms with no named body | `"City Hall said"` with no named government body | The named body when the text provides one |

Skip generic references without a named institution ("the agency," "police," "school officials," "Illinois police departments," "Illinois state law"); article bylines and publication credits; and historical, religious, or fictional entities unless they act as real-world organizations in the story.

## Borderline cousins

The same name can be an organization, a brand, a work/title, a venue, or an event — use context. When a borderline mention is editorially relevant, include the row with the best normal `type` and set `organization_boundary`:

- `borderline_brand_platform` — a **named corporate or platform entity** is acting but context is ambiguous (never a bare consumer brand with no organized body)
- `borderline_work_title` — column, show, book, film, franchise, or publication title ("Dear Abby answered a reader")
- `borderline_place_business` — business name may be only a location ("the event happened at Baskin Robbins")
- `borderline_event_competition` — an organizing body might exist but context is ambiguous; if the mention is just the event or award name, **omit** instead

Omit `organization_boundary` for clear organizations, and never use `other` just because a row is borderline.

Examples:
- "Twitter laid off 20 people" → organization (`company`); "Joe sent a message on Twitter" → omit
- "Budweiser employees union voted to strike" → organization; "Budweiser" as a product mention → omit
- "AMC announced it would close two theaters" → organization (`company`)

## Names

- Use the most specific conventional proper-noun name; expand acronyms when known (`National Basketball Association`, not `NBA`) unless expansion is ambiguous.
- One record per organization; merge all `mentions`.
- **Schools:** always the full school name (`Brother Rice High School`), never a bare scoreline token (`Belvidere`, `Woodstock`, `Park`) — expand with your world knowledge to the conventional full name.
- **Sports teams:** in athletics coverage, bare school or university names mean the **team**. Use `sports_team` with the pattern `[School] [boys|girls|men's|women's] [sport] team` when the sport is inferable. Map nicknames ("Caravan," "Wolverines") to the school team pattern. Use `school`/`university` only when administration, district, or campus policy is the actor.
- **Prep scorelines (all formats):** tokens in game results, schedules, or box scores (`Belvidere 55, Woodstock 53`, `Team A at Team B`) name **school teams**, not the homonymous cities. **Extract both sides**, expanded to full school team names (`Belvidere High School boys basketball team`). Use dateline, league, and sport section to infer state and sport.
- **Pro and college teams before player names:** when a team nickname precedes a player or role (`Phillies masher Kyle Schwarber`, `Cubs ace`), extract the team as `sports_team` with the full conventional name (`Philadelphia Phillies`, `Chicago Cubs`) even when the team is not the grammatical subject.

## Fields

### type

One slug: `government`, `law_enforcement`, `court`, `legislative_body`, `political_party`, `school_district`, `school`, `university`, `hospital`, `public_health`, `public_services`, `utilities`, `company`, `local_business`, `financial_institution`, `real_estate`, `nonprofit`, `community_group`, `religious_org`, `culture_arts`, `sports_team`, `sports_league`, `media`, `other`

**`other` is not a catch-all.** Use it only for a named institution that is genuinely organizational but outside the list. If you would choose `other` only because nothing fits — or the mention is a law, place, concept, or topic — **omit the row** instead.

### role_in_story

Short plain-language reason the organization matters in this article.

### nature

One of: `primary`, `actor`, `source`, `subject`, `affected`, `regulator`, `context`, `other`

### nature_secondary_tags

Optional 0–2 additional tags from the same vocabulary.

### mentions

At least one object per organization with `text` (verbatim snippet) and `quote` (true only for direct quotations). Prefer a full sentence or paragraph containing the organization — not the name alone unless the name is the entire sentence.

## Output

Return **only** valid JSON. No text before or after the JSON.

## Text to Analyze

{text}
