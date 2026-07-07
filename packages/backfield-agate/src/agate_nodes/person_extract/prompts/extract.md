# People Extraction Service

Extract every editorially relevant **person** named in the news text at the end of this prompt. Return only valid JSON.

A person is relevant when they are named in the story (first name, last name, or full name) and matter to its events: actors, victims, witnesses, sources quoted or paraphrased, officials, subjects of investigations or policies.

## Hard stops — the person test

Apply this test to **every row before you emit it**: *is `name` the name of an individual human being?* If not — or if you are unsure — **omit the row**. A missing row is always better than a person record for an organization, place, role label, or product. This is the most common and most damaging extraction error.

Never emit as `people.name`:

| Category | Examples | Where it belongs |
|----------|----------|------------------|
| Role or role + agency, no personal name | `ICE agent`, `Illinois Border Patrol agent`, `Chicago police officer`, `federal authorities`, `store owner`, `the mayor` | Omit entirely |
| Government body, agency, or acronym | `ATF`, `DHS`, `FBI`, `Alcohol, Tobacco, Firearms and Explosives`, `National Transportation Safety Board`, `Illinois Gaming Board`, `Cook County State's Attorney's Office` | Organization extract |
| Legislature or governing body | `Illinois General Assembly`, `General Assembly`, `City Council`, `County Board` | Organization extract |
| Company, firm, or fund | `H&R Block`, `Engaged Capital`, `Permanent Capital`, `BlackEdge Capital`, `Kittelson & Associates`, `Finkl Steel`, `American Ancestors` | Organization extract |
| School or campus | `Loyola Academy`, `Glenbard East High School`, `University of Chicago` | Organization extract |
| Media outlet or call sign | `ESPN 1000`, `WBEZ`, `CBS2`, `BBC` | Organization extract |
| Sports team or league | `Chicago Sky`, `Team USA`, `MLB` | Organization extract |
| Law or statute | `Presidential Records Act of 1978`, `Clean Air Act`, `First Amendment` | Omit |
| Software or AI product | `Gemini AI`, `ChatGPT` | Omit |
| Consumer brand alone | `Budweiser`, `Google`, `Coca-Cola` | Omit |
| City, place, airport, or venue | `Buenos Aires`, `Anchorage`, `O'Hare Airport`, `Wrigley Field` | Place extract |
| Family or collective | `the Sackler family`, `the couple`, `residents`, `witnesses` | Omit (extract named individual members separately) |

**Warning signs that a name is an institution, not a person:** it contains **Office, Department, Bureau, Agency, Administration, Authority, Commission, Board, Division, Corporation, Company, Foundation, Institute, Association, Union, School, Academy, University, Hospital, Medical Center, Capital, Partners, Holdings, Ventures, Equity, Associates, LLC, Inc., Media, News**; it is an all-caps acronym (`CTA`, `DHS`, `PBS`); or it ends in a number (`ESPN 1000`). Investment firms and funds ending in **Capital**, **Partners**, or **Holdings** are companies — never people.

Institutions stay institutions even when personified as the grammatical subject: `"DHS said…"`, `"WBEZ reported…"`, `"the American Medical Association announced…"` never create a person. Extract the named **individual** when one appears (`"Detective Maria Lopez of the Chicago Police Department"` → person `Maria Lopez`), never the organization itself.

**One exception — bands are people:** named musical groups and recording acts (`Pearl Jam`, `The Beatles`, `Alice Cooper` as the act) go in `people` with `type`: `artist_entertainer` and `public_figure`: `true` when widely known. Do not put bands in organization extraction.

If a borderline row must be emitted anyway, set `review_handling`: `auto_defer`, `review_reason_code`: `not_a_person`.

## Also do not extract

- **Article authors and staff**: bylines, contributors, editors, photographers credited on the article.
- **Non-story figures**: historical figures (Abraham Lincoln), religious or fictional characters, celebrities used metaphorically or in analogies ("He's no Einstein").
- **Background-only people**: authors of unrelated studies, people quoted only in other publications, optional context not tied to the story's events.

## Identity rules

1. **A name is required.** Generic titles alone ("the mayor," "a detective") never create a person. Title-only references may merge into an existing named person's record but cannot create one.
2. **Merge coreferences** into one record: full name → last name → pronouns → nicknames → role references, when clearly the same person ("Superintendent Lisa Johnson" → "Johnson" → "the superintendent").
3. **Surnames from family references**: when the article names a relative of someone with an established surname (`Rocky Wirtz's brother, Peter` → `Peter Wirtz`), use the full inferred name, set `surname_inferred_from_relative`: `true`, and route with `review_handling`: `flag_review`, `review_reason_code`: `first_name_only`. Do not infer from vague references when the anchor surname is not established in the same passage.
4. **Namesakes stay separate.** Two people sharing a last name get separate entries; merge only with unambiguous evidence.
5. **Pronoun mentions count.** Include sentences where a pronoun refers to the person even when the name is not repeated.

## Fields

### name

The fullest personal name form used in the article, as a flat string (`"Jane Doe"`). Strip honorifics and post-nominals (`Gov.`, `Dr.`, `Mr.`, `Rev.`, `Sen.`, `Jr.`, `Ph.D.`, …): `"Gov. J.B. Pritzker"` → `"JB Pritzker"` with `title`: `Governor`. Write initials **without periods** (`"PT Barnum"`, `"JB Pritzker"`). If the article uses only a surname after introduction, use the fullest form established earlier.

### title

The role or position **only** — official (Mayor, Police Chief) or informal (shortstop, spokesperson, store owner). Never include the organization name: "owner of Billiards on Broadway" → `title`: `Owner`, `affiliation`: `Billiards on Broadway`.

### affiliation

The organization tied to the title, written AP-style with the fullest clear name (`ACLU` → `American Civil Liberties Union`; `Sox` → `Boston Red Sox`). Empty string when none is stated or implied.

**Sports teams (critical):** assign a team only when the text clearly ties it to the person — `"Cubs ace Shota Imanaga"`, `"Kyle Tucker of the Cubs"`, `"former Yankees slugger Aaron Judge"`. Never assign a team from game context alone: in `"The Cubs beat the Pirates 5-3. Kyle Tucker homered."`, do not give Tucker either team unless his team was established elsewhere. When unsure, leave `affiliation` empty — a wrong team (especially the opponent) causes serious catalog errors.

### public_figure

`true` when widely known: politicians, major executives, professional athletes, entertainers, anyone likely to appear in Wikipedia or Ballotpedia.

### role_in_story

Brief phrase summarizing why this person is in the article.

### nature

Primary editorial role in the story, exactly one of:

`subject`, `source`, `expert`, `official`, `witness`, `affected`, `victim`, `suspect`, `participant`, `observer`, `context`, `other`

Mayor announcing policy → `official`; someone quoted about it → `source` or `affected`; person arrested → `suspect`; main figure of the story → `subject`.

### nature_secondary_tags

Optional array from the same vocabulary when a secondary role clearly applies (often empty).

### type

Story-relative role — one slug (classify why they appear in **this story**, not full biography):

`athlete`, `coach`, `sports_official`, `sports_executive`, `elected_official`, `government_official`, `political_staff`, `lawyer_legal_advocate`, `judge_court_official`, `law_enforcement_public_safety`, `crime_justice_subject`, `business_owner_executive`, `business_professional`, `labor_union_representative`, `artist_entertainer`, `media_journalism`, `arts_culture_professional`, `education_research_expert`, `healthcare_worker`, `community_member`, `unknown`, `other`

Prefer story function over job title: chef at a restaurant opening → `business_owner_executive`; chef profiled for creative work → `arts_culture_professional`; chef quoted as a neighbor → `community_member`. Mayor on policy → `elected_official`; agency director → `government_official`; police chief → `law_enforcement_public_safety`; person charged → `crime_justice_subject`; judge → `judge_court_official`; resident quoted → `community_member`. Use `unknown` when the role cannot be inferred; `other` only when the role is clear but no category fits.

### sort_key

Lowercase last name (`"doe"` for Jane Doe), or the sole name token for mononyms.

### mentions

Every sentence (or paragraph when sentence boundaries are broken) where the person appears or is referenced by pronoun, verbatim except trimmed whitespace. Each mention is a separate object — never combine sentences, never use plain strings:

```json
"mentions": [
  {{"text": "Johnson said she would not resign.", "quote": true}},
  {{"text": "The superintendent has been in the role since 2019.", "quote": false}}
]
```

Mark `quote: true` when the mention contains a direct quote, indirect quote, or paraphrased attribution **from that person**; `false` when they are merely mentioned inside someone else's quote. When a direct quote is split by attribution ("Part one," he said. "Part two."), capture the complete quote as one mention including the attribution between the parts.

## Review routing (canonical linking)

| Situation | `review_handling` | `review_reason_code` |
|-----------|-------------------|----------------------|
| Child (minor) | `auto_defer` | `child` |
| Animal (named pet, etc.) | `auto_defer` | `animal` |
| Non-person that had to be emitted (organization, place, role label, product) | `auto_defer` | `not_a_person` |
| Stage name or alias without a clear legal name (`Prince`) | `flag_review` | `stage_name_or_alias` |
| Descriptive pseudonym or anonymous-source label (`TRUTH-TELLER IN ARKANSAS`) | `flag_review` | `pseudonym` |
| First name only, no surname anywhere in the article | `flag_review` | `first_name_only` |
| Surname inferred from a family reference | `flag_review` | `first_name_only` (note which relative established it) |
| Normal named person with full identity | `none` | omit |

Include a short editor-facing `review_message` whenever handling is not `none`. Use `auto_defer` only for children, animals, and non-people; aliases, pseudonyms, and first-name-only mentions use `flag_review` so editors see them in the open queue.

## Output format

Return ONLY valid JSON — no explanatory text. Each person object must include:

- `name`: string — full personal name (flat string)
- `title`: string — role or position only
- `affiliation`: string — organization, or empty string
- `public_figure`: boolean
- `type`: string — one taxonomy slug from **type** (never invent categories)
- `sort_key`: string — lowercase last name
- `role_in_story`: string
- `nature`: string — one vocabulary value from **nature**
- `nature_secondary_tags`: array of strings (same vocabulary; often empty)
- `mentions`: array of objects with `"text"` (string) and `"quote"` (boolean)
- `review_handling`: string — `none`, `flag_review`, or `auto_defer`
- `review_reason_code`: string — when handling is not `none`: `child`, `animal`, `not_a_person`, `stage_name_or_alias`, `pseudonym`, or `first_name_only`
- `review_message`: string — short explanation when handling is not `none`
- `surname_inferred_from_relative`: boolean — `true` only for inferred family surnames

Return `{{ "people": [ ... ] }}`. When no named people qualify, return `{{ "people": [] }}`.

## Text to Analyze

{text}
