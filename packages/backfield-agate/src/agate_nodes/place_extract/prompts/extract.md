# Location Extraction Service

Extract **editorially relevant, literal, physical locations** from the text at the end of this prompt. Return only valid JSON.

Do **not** be maximalist. Include a location only when it matters to the story as real-world geography:

- Where key events occurred, or affected places readers would recognize (venues, parks, public spaces).
- Where sources or characters are **from**, or biographical context (lived, worked, grew up, went to school) tied to a real place.
- Scene-setting or dateline places when they indicate where reporting or events occur.
- **Lawmaker districts**: for "Joe Smith, R-Maple Grove," include **Maple Grove, MN**.

## Hard stops — the place test

Apply this test to **every row before you emit it**: *is `location` a literal, mappable, physical place that a reader could find on a map?* If not — or if you are unsure — **omit the row**. A missing row is always better than a location record for a team, conference, event, organization, or phrase. Being geocodable is not enough: the string must name **real geography in this story**.

Never emit as a location:

| Category | Examples | Extract instead (only when the story supports it) |
|----------|----------|---------------------------------------------------|
| Sports team, game, league, division, or era | `Chicago Bears`, `1969 Bears`, `Bears-Packers game`, `Game 7`, `home opener`, `Team USA`, `World Series`, `American League Central`, `Eastern Conference`, `American Basketball Association` | The stadium, arena, school campus, or city where the action is anchored. **Exception:** in **prep / IHSA scorelines and tournament results**, school-named tokens (`St. Rita`, `Maine South`, `East Peoria`) are **school campuses**, not pro/college teams — extract them per **Institutions and school sports** |
| Athletic conference, class, or bracket | `Class 3A`, `Class 3a, IL`, `IHSA 4A`, `West Suburban Conference Silver`, `Division 2`, sectional/regional/supersectional brackets | Nothing — these are competition labels, never geography of any type; **still extract every named school and venue on the same lines** |
| Event, proceeding, or activity title | `U.S. Senate Judiciary Committee Hearing`, `training camp`, `minicamp`, `OTAs`, `NFL Scouting Combine`, `Chicago Sky training camp`, `Lake Shore Tournament` | The named venue (`Lucas Oil Stadium`, `McCormick Place`) or campus when the article names one |
| Metonym for an institution | `Washington` meaning Congress or federal agencies, `City Hall` meaning city government, a city name meaning its team | `Washington, DC` only when action is anchored in the capital city; `City Hall` only as a physical meeting site |
| Person with appended geography | `Brandon Johnson, Chicago, IL`, `J.B. Pritzker, IL`, `Donald Trump, Georgia, US` | Only independently relevant real geography |
| Organization with inferred headquarters | `American Medical Association, IL`, `Department of Homeland Security, US`, `National Science Foundation, US` | The building or property only when an event occurs there |
| Demographic or identity-based area label | `Black neighborhoods, Chicago, IL`, `Latino communities`, `immigrant neighborhoods` | A **named** neighborhood when the story names one (`Austin, Chicago, IL`) |
| Broad descriptive macro-area | `Commercial Corridors of Chicago, IL`, `Chicago and Nearby Parts of Wisconsin and Indiana Region, IL`, `Smaller Counties, IL`, `Forty States, US`, `metro area`, `the community`, `city limits` | Named cities, counties, or regions that are each independently relevant |
| Venue interior or subpart | `dugout`, `visitor's bullpen`, `Section 112`, `press box`, `bleachers`, `concession stand`, `end zone` | The parent venue (`Wrigley Field`, `United Center`) |
| Narrative, policy, or attribution phrasing | headline clauses, lede paragraphs, `"helping residents take a more direct role in neighborhood improvements"`, `"Mayor X said…"` | Named venues mentioned inside those clauses (`North Commons Park`, `East Lake Library`) |
| Generic facility category | `libraries`, `recreation centers`, `community spaces`, `schools`, `parks` with no specific name | The named branch, campus, building, or park |
| Generic or ambiguous site | unnamed `bank`, `gas station`, `Target, Minneapolis, MN` with no specific store | The specific site when the story pins one down |
| Figurative or historical-cultural use | synecdoche, metaphor, idiom, hyperbole, places cited only as cultural reference | The place only when it is the physical setting |
| Standalone country or continent, too broad to matter | `United States`, `North America` as incidental framing | Keep only when the story truly hinges on country-scale geography |

**Washington disambiguation:** **Washington, DC** is the federal capital (postal **DC**, never **WA**). **Washington state** geography uses **WA** (`Seattle, WA`). When "Washington" alone means Congress, the White House, or federal agencies with no local scene, **omit**. When the story anchors action in the capital city (Capitol Hill, D.C. neighborhoods), use **Washington, DC**.

The **`location`** field must always be a geocodable proper-name string (city, venue, street, park) — never a sentence, headline fragment, quote clause, or narrative phrase.

## Institutions and school sports

- An organization named **without** a specific site (headquarters, campus, building, address) is not a location ("The ACLU protested"). Agencies, unions, and associations qualify only when the story places an event at their **building or property**.
- **Small businesses** named in a real-world context are often relevant; **large corporate HQs** are usually not unless an event occurred there ("Target Corp. objected" — omit; "employees gathered at Target headquarters" — keep).
- **High school sports:** schools and contest locations mentioned in prep coverage should be **included**.
- **Venue does not replace schools:** when a shared stadium or city hosts a tournament (`at Slammers Stadium, Joliet`), emit the venue **and every participating school** as separate rows. Do not stop after the venue.
- **Scoreboards and game summaries** (`St. Louis Park 57 Hopkins 54`, `Belvidere 55, Woodstock 53`), **scheduled lines** (`Hinsdale Adventist at Calvary Christian`, `Wolcott at Rochelle Zell`), and **state-tournament / bracket score lists** (`Title: St. Rita 12, Triad 11`; `Semifinals` / `St. Rita 2, East Peoria 1`; `Third place: Naperville Central vs. Mount Carmel, 9`; `East Peoria 7, Crystal Lake South 6, third place`): each school-named token names a **school campus**, not the homonymous city and not a pro/college team. Emit **every participating school** as separate **`place`** rows — both sides of each matchup. Labels like `Title:`, `Semifinals`, `Third place:`, and `CLASS 3A` / `CLASS 4A` are bracket metadata — omit as locations, but **do not** suppress the school names on those lines. Set `components.place.name` to the **full conventional school name** (`St. Rita High School`, `Maine South High School`, `Rochelle Zell Jewish High School`) and `location` to a geocodable string with city and state when inferable. **Never** emit the bare scoreline token (`Belvidere`, `Smith`, `Park`, `East Peoria`) as `location` or `place.name`, never put a school name in `components.city`, never use `other` for these tokens, and never emit standalone `city` rows for tokens that are only school names. Do not omit the away team.
- These scoreboard exceptions apply only to **school/prep** coverage — they never authorize extracting pro teams, conferences, leagues, classes, or divisions as places.

## Regions and deduplication

- Prefer **specific** geographies; omit vague "store, Minneapolis, MN" when clearer objects cover the same area.
- **Named regions** ("Southwest Missouri," "the Pacific Northwest") can be relevant; when you include a sub-region, also include the **containing** city/state/county objects when the text supports them ("Northern Arizona" and "Arizona").
- **One object per place**: each distinct real-world location appears **once**, with every verbatim snippet collected in its `mentions` array. When the same place appears at multiple levels of detail, keep the **most detailed** instance and drop redundant broader duplicates.
- **Streets as components**: a street already represented inside an **intersection** or **span** is not also a separate `street_road` row.
- When a story opens with a `"CITY — …"` dateline, emit a separate **`city`** row for the dateline city when editorially relevant.

## Type classification

Classify each included location with one type:

- **place**: A **named** physical site people could find on a map — building, campus, business, landmark, park, stadium, **named bridge**. Never an event title, hearing name, or activity label. Natural features use **natural**, not place. Treat a **named bridge** as place when it is a landmark or venue; use **span** only for an explicit roadway segment between two endpoints.
- **address**: A street address with a house number. Journalistic **block references** ("6500 block of South Hermitage Avenue," "500 block of Portland Ave.") also use this type — but **`location` must be the normalized mailing-style address**, never the verbatim "block of" phrase (see **Block addresses** below). If a place also includes an address, extract only the address as this type. Streets without a house or block number are not addresses.
- **intersection_road**: An intersection of two non-highway roads. You may infer the intersection from context elsewhere in the article.
- **intersection_highway**: An intersection where at least one component is an interstate or highway ("I-94 and Selby Avenue").
- **street_road**: A single street, road, or highway without address context ("Hennepin Avenue," "I-35").
- **span**: A stretch of road between two points ("I-35 between Pine City and Hinckley"). Requires a road plus **both** endpoints; a road with one reference point uses another type.
- **neighborhood**: Explicit neighborhood names, name only ("North Loop", not "North Loop neighborhood").
- **region_city**: A described area within a city that is not a named place or neighborhood ("South Minneapolis," "the Chicago lakefront"), or named transit lines ("the Green Line"). Also extract the city as a separate object. Applies to sub-county areas too ("western Hennepin County, MN").
- **city**: The name of a city.
- **county**: The name of a county.
- **region_state**: A region within a state ("Northern Wisconsin") or a large city plus surroundings ("the Chicago area," "the East Bay"). Also extract the state separately.
- **state**: A state.
- **region_national**: A region of the United States ("the South").
- **country**: A country.
- **political_district**: A **numbered or ordinally identified** political boundary used as geography — congressional districts, state house/senate districts, city wards, numbered precincts. Use only when the story treats the district as a **jurisdiction** (elections, representation, redistricting) and the text references a **formal district with a stable number** ("8th Congressional District," "Ward 15"). Never use it for colloquial regions, counties, neighborhoods, or **athletic/scholastic conferences, classes, and brackets** — those competition labels are omitted entirely (see Hard stops).
- **natural**: A specific named natural feature (river, lake, mountain range). General natural regions ("the California coast") are regions.
- **other**: Anything that fits no category above.

## Formatting rules

- Return **geocodable strings**, filling in context the story supports: "Minnetonka" → "Minnetonka, MN". States and countries stand alone ("Minnesota," not "Minnesota, MN").
- **International cities**: format as **`{{City}}, {{Country}}`** ("Paris, France," "Toronto, Canada") — never a US state code. US cities use **`{{City}}, {{ST}}`**.
- **Washington, DC vs Washington state**: the federal capital is **`Washington, DC`**; Washington-state geography uses **`WA`** ("Seattle, WA," "Spokane, WA"). Never swap them.
- **Street-type spelling**: for `street_road`, `intersection_road`, `intersection_highway`, and `span` strings, spell out street types in full (**Street**, **Avenue**, **Boulevard**, **Road**, **Highway**) — "103rd Street, Chicago, IL," not "103rd St., Chicago, IL". **Exception**: `address` strings may use conventional mailing abbreviations ("7603 N. Main St., Springfield, IL").
- **Block addresses (critical)** — When the story cites a block ("6500 block of South Hermitage Avenue," "200 block of Smith St."), classify as **`address`** but **normalize before output**. Strip **"block of"** entirely; use the block number as the house number; abbreviate street types (**Ave**, **St**, **Blvd**, **Rd**); include city and state when inferable. Set **`location`**, **`components.full`**, and **`components.address`** to the normalized form — never the journalistic phrase.

  | Story wording | Output `location` |
  |---------------|-------------------|
  | 6500 block of South Hermitage Avenue | `6500 S Hermitage Ave, Chicago, IL` |
  | 200 block of Smith Street | `200 Smith St., Minneapolis, MN` |
  | 500 block of Portland Ave. | `500 Portland Ave., Minneapolis, MN` |

  Wrong: `6500 block of South Hermitage Avenue, Chicago, IL`. Right: `6500 S Hermitage Ave, Chicago, IL`.
- **Neighborhoods and regions**: include city and state in `location` when inferable (`Longfellow, Minneapolis, MN`; `South Minneapolis, Minneapolis, MN`). For every **`region_city`** or **`region_state`**, also emit the parent **`city`** or **`state`** as a **separate row**.
- **Intersections**: format as `Road A and Road B, City, ST` with street types spelled out in full (`Main Street and 2nd Street, Chicago, IL`; `I-94 and Selby Avenue, Minneapolis, MN`). You may infer an intersection from context elsewhere in the article even when the story does not state it in one string.
- **Spans**: include the road plus **both** endpoints and city/state when inferable (`Lake Street from Nicollet Avenue to 28th Avenue, Minneapolis, MN`; `I-35 between Pine City and Hinckley, MN`). A road with only one endpoint is not a span.
- For a street-number range ("7603–7619 N. Main St."), keep only the first number.
- Natural places return the name plus state when possible ("Chicago River, IL").
- Omit non-geocodable details ("eastbound lanes," vague "metro").
- Imprecise incident locations ("Highway 61 near Grand Marais") return only the town ("Grand Marais, MN").
- Lists of places ("Freeborn, Faribault, … counties all received snow") become separate objects — but only those that are editorially relevant.
- Include as much inferable geographic detail as the story supports: "Memorial Hospital" later placed in Minneapolis → "Memorial Hospital, Minneapolis, MN". Non-proper-noun sites too: "Monticello nuclear power plant" → "Nuclear power plant, Monticello, MN".
- Expand shorthand names, especially schools: "Park" meaning St. Louis Park High School, "Crete-Monee" → "Crete-Monee High School". Prep scoreline tokens that look like city names (`Belvidere`, `Woodstock`) expand to the full school name, not the municipality.
- For `street_road`, prefer road + city + state ("Interstate 55, Springfield, IL"); fall back to road + state, then road alone for multi-state roads.

## Component extraction

Separate each location into components where possible:

- **full**: The full geocodable string ("Minneapolis, MN"; "Longfellow, Minneapolis, MN").
- **type**: The type from the list above.
- **place**: Only for named places — businesses, landmarks, **schools**, **bridges**:
  - **name**: The place name ("Dogwood Coffee," "Hopkins High School," "Stone Arch Bridge").
  - **natural**: True when the place is a natural feature unlikely to have a street address.
  - **addressable**: True when the place likely has a findable street address (business, building, school, landmark). **Named bridges and similar named crossings** are **`addressable: true`** — they geocode as POIs even without a mailing address. False otherwise.
- **street_road**: Only for street_road types:
  - **name**: The street name.
  - **boundary**: A geocodable string for the most specific boundary containing the segment, inferred from context.
- **span**: Only for span types:
  - **start**: Object with **type** (`city` or `intersection`) and **location** (geocodable string, e.g. "Hennepin Avenue and West 26th Street, Minneapolis, MN" or "Pine City, MN").
  - **end**: Same shape as start.
- **address**: The street address ("100 Fake St.").
- **neighborhood**: The neighborhood name ("Upper West Side").
- **city**: The city name ("Milwaukee").
- **county**: The county name ("Boone County").
- **state**: Object with **name** ("California") and **abbr** ("CA").
- **country**: Object with **name** ("United States") and **abbr** (ISO code, "US").
- **district**: Only for **political_district** locations:
  - **kind**: One of `ward`, `us_house`, `state_senate`, `state_house`, `city_council`, `precinct`, `other`.
  - **number**: The district or ward number as digits ("8", "15", "4-2"). Infer digits from ordinals when possible.
  - **ordinal**: Optional spoken ordinal ("Eighth").
  - **scope**: One of `federal`, `state`, `county`, `city`.

Do not infer information beyond these rules, except **country**, which you should include whenever reasonably inferable (usually US). Return empty objects or strings for components that do not apply.

## Editorial role (nature)

Set exactly one primary **`nature`** per location:

- **primary** — Where the main news event happens: crime scene, construction site, game venue, key meeting place.
- **secondary** — A consequential supporting location (hospital after a crash).
- **subject** — The place is the focus of coverage: venue profile, restaurant review, list item.
- **context** — Background or non-event reference (policy backdrop, regional characterization).
- **historical** — Cited for past events, precedent, or historical comparison ("similar floods in 1927"); matters as history, not the current scene.
- **person** — Tied to a person: where they were quoted, hometown, employer campus.
- **unknown** — Only when none of the above applies.

Optionally include **`nature_secondary_tags`**: an array of additional labels from the same vocabulary when a place clearly plays more than one role.

`description` remains the human-readable sentence; `nature` is the controlled vocabulary.

## Mentions in the story (`mentions`)

Every location object includes a **`mentions`** array. Each element is an object with exactly one key, **`text`**: a verbatim sentence or clause from the story (prefer a full sentence or paragraph for context).

1. Include **every** editorial mention of the same real-world place, even repeats ("Ohio" in the lede and again later → two mention objects).
2. Never use plain strings; always objects with `text`.
3. Set **`original_text`** to the first mention's `text` (identical string to `mentions[0].text`).

Example (braces doubled so they are literal in this template):

```json
"mentions": [
  {{ "text": "Ohio lawmakers advanced the bill Tuesday." }},
  {{ "text": "Back in Ohio, the governor said he would sign it." }}
],
"original_text": "Ohio lawmakers advanced the bill Tuesday."
```

## Required fields

- **original_text**: the paragraph the location was extracted from, verbatim (must match `mentions[0].text`).
- **description**: 1–2 concise, journalistic sentences explaining why this geography matters, written as if describing the events for residents of that place. Do not reference the broader story.
- **nature** (string) and optionally **nature_secondary_tags** (array).

## Geocode hints (`geocode_hints`)

Include a string field **`geocode_hints`** on every location: short, actionable prose from the story **not already obvious** from `location`, `components`, or `original_text` — material that disambiguates duplicate names, narrows vague geography, or relates this mention to other sites in the article.

1. Be concise — one or two sentences, under ~400 characters.
2. Add information; don't repeat the verbatim quote.
3. Use `""` when nothing beyond the structured fields is needed.

Examples:

- `"Story identifies this as the East Lake St. café location; mayor spoke outside after the rally, not the roasting warehouse mentioned earlier."`
- `"Industrial pocket east of the river where overnight truck queues were described two paragraphs above."`

## Street-level kind (`address_place_kind`)

For each location whose type is **address**, **intersection_road**, **intersection_highway**, **street_road**, or **span**, add a top-level string field **`address_place_kind`**:

- **`public_named`** — A named business, landmark, civic building, school, hospital, or other identifiable public or semi-public place a member of the public could realistically **enter** as customer, patron, patient, student, or guest — even when the string looks like an address.
- **`private_residence`** — Legacy value name; do **not** read it as "homes only." Use it for anything that is **not** a named public venue: private homes, apartments, anonymous residential blocks (generic "N00 block of …" reading as housing), road or highway intersections cited as crime/crash scenes with no named landmark, PO boxes and mail-only addresses, generic parking lots or stretches of pavement. Prefer `public_named` only when the text clearly identifies a specific business, institution, or landmark there.
- **`unknown`** — You cannot tell from the article; prefer this over guessing.

Base the judgment on `original_text`, `description`, and full story context. For all other types (city, neighborhood, place, natural, etc.), **omit** `address_place_kind` entirely.

## Output format

**IMPORTANT**: Return ONLY valid JSON. Do not include any explanatory text before or after the JSON.

## Text to Analyze

{text}
