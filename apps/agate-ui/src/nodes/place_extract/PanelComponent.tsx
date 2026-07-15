// Auto-injected metadata for PlaceExtract
const nodeMetadata = {
  "type": "PlaceExtract",
  "name": "PlaceExtract",
  "label": "Place Extract",
  "description": "Extract editorially relevant, geocodable place information from text.",
  "category": "extraction",
  "icon": "Map",
  "color": "bg-purple-500",
  "requiredUpstreamNodes": [],
  "inputs": [
    {
      "id": "text",
      "label": "Text",
      "type": "string",
      "required": true
    }
  ],
  "outputs": [
    {
      "id": "text",
      "label": "Text",
      "type": "string"
    },
    {
      "id": "locations",
      "label": "Locations",
      "type": "array"
    }
  ],
  "defaultParams": {
    "model": "",
    "aiModelConfigId": null,
    "prompt_file": "prompts/extract.md",
    "prompt": "# Location Extraction Service\n\nExtract **editorially relevant, literal, physical locations** from the text at the end of this prompt. Return only valid JSON.\n\nDo **not** be maximalist. Include a location only when it matters to the story as real-world geography:\n\n- Where key events occurred, or affected places readers would recognize (venues, parks, public spaces).\n- Where sources or characters are **from**, or biographical context (lived, worked, grew up, went to school) tied to a real place.\n- Scene-setting or dateline places when they indicate where reporting or events occur.\n- **Lawmaker districts**: for \"Joe Smith, R-Maple Grove,\" include **Maple Grove, MN**.\n\n## Hard stops — the place test\n\nApply this test to **every row before you emit it**: *is `location` a literal, mappable, physical place that a reader could find on a map?* If not — or if you are unsure — **omit the row**. A missing row is always better than a location record for a team, conference, event, organization, or phrase. Being geocodable is not enough: the string must name **real geography in this story**.\n\nNever emit as a location:\n\n| Category | Examples | Extract instead (only when the story supports it) |\n|----------|----------|---------------------------------------------------|\n| Sports team, game, league, division, or era | `Chicago Bears`, `1969 Bears`, `Bears-Packers game`, `Game 7`, `home opener`, `Team USA`, `World Series`, `American League Central`, `Eastern Conference`, `American Basketball Association` | The stadium, arena, school campus, or city where the action is anchored. **Exception:** in **prep / IHSA scorelines and tournament results**, school-named tokens (`St. Rita`, `Maine South`, `East Peoria`) are **school campuses**, not pro/college teams — extract them per **Institutions and school sports** |\n| Athletic conference, class, or bracket | `Class 3A`, `Class 3a, IL`, `IHSA 4A`, `West Suburban Conference Silver`, `Division 2`, sectional/regional/supersectional brackets | Nothing — these are competition labels, never geography of any type; **still extract every named school and venue on the same lines** |\n| Event, proceeding, or activity title | `U.S. Senate Judiciary Committee Hearing`, `training camp`, `minicamp`, `OTAs`, `NFL Scouting Combine`, `Chicago Sky training camp`, `Lake Shore Tournament` | The named venue (`Lucas Oil Stadium`, `McCormick Place`) or campus when the article names one |\n| Metonym for an institution | `Washington` meaning Congress or federal agencies, `City Hall` meaning city government, a city name meaning its team | `Washington, DC` only when action is anchored in the capital city; `City Hall` only as a physical meeting site |\n| Person with appended geography | `Brandon Johnson, Chicago, IL`, `J.B. Pritzker, IL`, `Donald Trump, Georgia, US` | Only independently relevant real geography |\n| Organization with inferred headquarters | `American Medical Association, IL`, `Department of Homeland Security, US`, `National Science Foundation, US` | The building or property only when an event occurs there |\n| Demographic or identity-based area label | `Black neighborhoods, Chicago, IL`, `Latino communities`, `immigrant neighborhoods` | A **named** neighborhood when the story names one (`Austin, Chicago, IL`) |\n| Broad descriptive macro-area | `Commercial Corridors of Chicago, IL`, `Chicago and Nearby Parts of Wisconsin and Indiana Region, IL`, `Smaller Counties, IL`, `Forty States, US`, `metro area`, `the community`, `city limits` | Named cities, counties, or regions that are each independently relevant |\n| Venue interior or subpart | `dugout`, `visitor's bullpen`, `Section 112`, `press box`, `bleachers`, `concession stand`, `end zone` | The parent venue (`Wrigley Field`, `United Center`) |\n| Narrative, policy, or attribution phrasing | headline clauses, lede paragraphs, `\"helping residents take a more direct role in neighborhood improvements\"`, `\"Mayor X said…\"` | Named venues mentioned inside those clauses (`North Commons Park`, `East Lake Library`) |\n| Generic facility category | `libraries`, `recreation centers`, `community spaces`, `schools`, `parks` with no specific name | The named branch, campus, building, or park |\n| Generic or ambiguous site | unnamed `bank`, `gas station`, `Target, Minneapolis, MN` with no specific store | The specific site when the story pins one down |\n| Figurative or historical-cultural use | synecdoche, metaphor, idiom, hyperbole, places cited only as cultural reference | The place only when it is the physical setting |\n| Standalone country or continent, too broad to matter | `United States`, `North America` as incidental framing | Keep only when the story truly hinges on country-scale geography |\n\n**Washington disambiguation:** **Washington, DC** is the federal capital (postal **DC**, never **WA**). **Washington state** geography uses **WA** (`Seattle, WA`). When \"Washington\" alone means Congress, the White House, or federal agencies with no local scene, **omit**. When the story anchors action in the capital city (Capitol Hill, D.C. neighborhoods), use **Washington, DC**.\n\nThe **`location`** field must always be a geocodable proper-name string (city, venue, street, park) — never a sentence, headline fragment, quote clause, or narrative phrase.\n\n## Institutions and school sports\n\n- An organization named **without** a specific site (headquarters, campus, building, address) is not a location (\"The ACLU protested\"). Agencies, unions, and associations qualify only when the story places an event at their **building or property**.\n- **Small businesses** named in a real-world context are often relevant; **large corporate HQs** are usually not unless an event occurred there (\"Target Corp. objected\" — omit; \"employees gathered at Target headquarters\" — keep).\n- **High school sports:** schools and contest locations mentioned in prep coverage should be **included**.\n- **Venue does not replace schools:** when a shared stadium or city hosts a tournament (`at Slammers Stadium, Joliet`), emit the venue **and every participating school** as separate rows. Do not stop after the venue.\n- **Scoreboards and game summaries** (`St. Louis Park 57 Hopkins 54`, `Belvidere 55, Woodstock 53`), **scheduled lines** (`Hinsdale Adventist at Calvary Christian`, `Wolcott at Rochelle Zell`), and **state-tournament / bracket score lists** (`Title: St. Rita 12, Triad 11`; `Semifinals` / `St. Rita 2, East Peoria 1`; `Third place: Naperville Central vs. Mount Carmel, 9`; `East Peoria 7, Crystal Lake South 6, third place`): each school-named token names a **school campus**, not the homonymous city and not a pro/college team. Emit **every participating school** as separate **`place`** rows — both sides of each matchup. Labels like `Title:`, `Semifinals`, `Third place:`, and `CLASS 3A` / `CLASS 4A` are bracket metadata — omit as locations, but **do not** suppress the school names on those lines. Set `components.place.name` to the **full conventional school name** (`St. Rita High School`, `Maine South High School`, `Rochelle Zell Jewish High School`) and `location` to a geocodable string with city and state when inferable. **Never** emit the bare scoreline token (`Belvidere`, `Smith`, `Park`, `East Peoria`) as `location` or `place.name`, never put a school name in `components.city`, never use `other` for these tokens, and never emit standalone `city` rows for tokens that are only school names. Do not omit the away team.\n- These scoreboard exceptions apply only to **school/prep** coverage — they never authorize extracting pro teams, conferences, leagues, classes, or divisions as places.\n\n## Regions and deduplication\n\n- Prefer **specific** geographies; omit vague \"store, Minneapolis, MN\" when clearer objects cover the same area.\n- **Named regions** (\"Southwest Missouri,\" \"the Pacific Northwest\") can be relevant; when you include a sub-region, also include the **containing** city/state/county objects when the text supports them (\"Northern Arizona\" and \"Arizona\").\n- **One object per place**: each distinct real-world location appears **once**, with every verbatim snippet collected in its `mentions` array. When the same place appears at multiple levels of detail, keep the **most detailed** instance and drop redundant broader duplicates.\n- **Streets as components**: a street already represented inside an **intersection** or **span** is not also a separate `street_road` row.\n- When a story opens with a `\"CITY — …\"` dateline, emit a separate **`city`** row for the dateline city when editorially relevant.\n\n## Type classification\n\nClassify each included location with one type:\n\n- **place**: A **named** physical site people could find on a map — building, campus, business, landmark, park, stadium, **named bridge**. Never an event title, hearing name, or activity label. Natural features use **natural**, not place. Treat a **named bridge** as place when it is a landmark or venue; use **span** only for an explicit roadway segment between two endpoints.\n- **address**: A street address with a house number. Journalistic **block references** (\"6500 block of South Hermitage Avenue,\" \"500 block of Portland Ave.\") also use this type — but **`location` must be the normalized mailing-style address**, never the verbatim \"block of\" phrase (see **Block addresses** below). If a place also includes an address, extract only the address as this type. Streets without a house or block number are not addresses.\n- **intersection_road**: An intersection of two non-highway roads. You may infer the intersection from context elsewhere in the article.\n- **intersection_highway**: An intersection where at least one component is an interstate or highway (\"I-94 and Selby Avenue\").\n- **street_road**: A single street, road, or highway without address context (\"Hennepin Avenue,\" \"I-35\").\n- **span**: A stretch of road between two points (\"I-35 between Pine City and Hinckley\"). Requires a road plus **both** endpoints; a road with one reference point uses another type.\n- **neighborhood**: Explicit neighborhood names, name only (\"North Loop\", not \"North Loop neighborhood\").\n- **region_city**: A described area within a city that is not a named place or neighborhood (\"South Minneapolis,\" \"the Chicago lakefront\"), or named transit lines (\"the Green Line\"). Also extract the city as a separate object. Applies to sub-county areas too (\"western Hennepin County, MN\").\n- **city**: The name of a city.\n- **county**: The name of a county.\n- **region_state**: A region within a state (\"Northern Wisconsin\") or a large city plus surroundings (\"the Chicago area,\" \"the East Bay\"). Also extract the state separately.\n- **state**: A state.\n- **region_national**: A region of the United States (\"the South\").\n- **country**: A country.\n- **political_district**: A **numbered or ordinally identified** political boundary used as geography — congressional districts, state house/senate districts, city wards, numbered precincts. Use only when the story treats the district as a **jurisdiction** (elections, representation, redistricting) and the text references a **formal district with a stable number** (\"8th Congressional District,\" \"Ward 15\"). Never use it for colloquial regions, counties, neighborhoods, or **athletic/scholastic conferences, classes, and brackets** — those competition labels are omitted entirely (see Hard stops).\n- **natural**: A specific named natural feature (river, lake, mountain range). General natural regions (\"the California coast\") are regions.\n- **other**: Anything that fits no category above.\n\n## Formatting rules\n\n- Return **geocodable strings**, filling in context the story supports: \"Minnetonka\" → \"Minnetonka, MN\". States and countries stand alone (\"Minnesota,\" not \"Minnesota, MN\").\n- **International cities**: format as **`{{City}}, {{Country}}`** (\"Paris, France,\" \"Toronto, Canada\") — never a US state code. US cities use **`{{City}}, {{ST}}`**.\n- **Washington, DC vs Washington state**: the federal capital is **`Washington, DC`**; Washington-state geography uses **`WA`** (\"Seattle, WA,\" \"Spokane, WA\"). Never swap them.\n- **Street-type spelling**: for `street_road`, `intersection_road`, `intersection_highway`, and `span` strings, spell out street types in full (**Street**, **Avenue**, **Boulevard**, **Road**, **Highway**) — \"103rd Street, Chicago, IL,\" not \"103rd St., Chicago, IL\". **Exception**: `address` strings may use conventional mailing abbreviations (\"7603 N. Main St., Springfield, IL\").\n- **Block addresses (critical)** — When the story cites a block (\"6500 block of South Hermitage Avenue,\" \"200 block of Smith St.\"), classify as **`address`** but **normalize before output**. Strip **\"block of\"** entirely; use the block number as the house number; abbreviate street types (**Ave**, **St**, **Blvd**, **Rd**); include city and state when inferable. Set **`location`**, **`components.full`**, and **`components.address`** to the normalized form — never the journalistic phrase.\n\n  | Story wording | Output `location` |\n  |---------------|-------------------|\n  | 6500 block of South Hermitage Avenue | `6500 S Hermitage Ave, Chicago, IL` |\n  | 200 block of Smith Street | `200 Smith St., Minneapolis, MN` |\n  | 500 block of Portland Ave. | `500 Portland Ave., Minneapolis, MN` |\n\n  Wrong: `6500 block of South Hermitage Avenue, Chicago, IL`. Right: `6500 S Hermitage Ave, Chicago, IL`.\n- **Neighborhoods and regions**: include city and state in `location` when inferable (`Longfellow, Minneapolis, MN`; `South Minneapolis, Minneapolis, MN`). For every **`region_city`** or **`region_state`**, also emit the parent **`city`** or **`state`** as a **separate row**.\n- **Intersections**: format as `Road A and Road B, City, ST` with street types spelled out in full (`Main Street and 2nd Street, Chicago, IL`; `I-94 and Selby Avenue, Minneapolis, MN`). You may infer an intersection from context elsewhere in the article even when the story does not state it in one string.\n- **Spans**: include the road plus **both** endpoints and city/state when inferable (`Lake Street from Nicollet Avenue to 28th Avenue, Minneapolis, MN`; `I-35 between Pine City and Hinckley, MN`). A road with only one endpoint is not a span.\n- For a street-number range (\"7603–7619 N. Main St.\"), keep only the first number.\n- Natural places return the name plus state when possible (\"Chicago River, IL\").\n- Omit non-geocodable details (\"eastbound lanes,\" vague \"metro\").\n- Imprecise incident locations (\"Highway 61 near Grand Marais\") return only the town (\"Grand Marais, MN\").\n- Lists of places (\"Freeborn, Faribault, … counties all received snow\") become separate objects — but only those that are editorially relevant.\n- Include as much inferable geographic detail as the story supports: \"Memorial Hospital\" later placed in Minneapolis → \"Memorial Hospital, Minneapolis, MN\". Non-proper-noun sites too: \"Monticello nuclear power plant\" → \"Nuclear power plant, Monticello, MN\".\n- Expand shorthand names, especially schools: \"Park\" meaning St. Louis Park High School, \"Crete-Monee\" → \"Crete-Monee High School\". Prep scoreline tokens that look like city names (`Belvidere`, `Woodstock`) expand to the full school name, not the municipality.\n- For `street_road`, prefer road + city + state (\"Interstate 55, Springfield, IL\"); fall back to road + state, then road alone for multi-state roads.\n\n## Component extraction\n\nSeparate each location into components where possible:\n\n- **full**: The full geocodable string (\"Minneapolis, MN\"; \"Longfellow, Minneapolis, MN\").\n- **type**: The type from the list above.\n- **place**: Only for named places — businesses, landmarks, **schools**, **bridges**:\n  - **name**: The place name (\"Dogwood Coffee,\" \"Hopkins High School,\" \"Stone Arch Bridge\").\n  - **natural**: True when the place is a natural feature unlikely to have a street address.\n  - **addressable**: True when the place likely has a findable street address (business, building, school, landmark). **Named bridges and similar named crossings** are **`addressable: true`** — they geocode as POIs even without a mailing address. False otherwise.\n- **street_road**: Only for street_road types:\n  - **name**: The street name.\n  - **boundary**: A geocodable string for the most specific boundary containing the segment, inferred from context.\n- **span**: Only for span types:\n  - **start**: Object with **type** (`city` or `intersection`) and **location** (geocodable string, e.g. \"Hennepin Avenue and West 26th Street, Minneapolis, MN\" or \"Pine City, MN\").\n  - **end**: Same shape as start.\n- **address**: The street address (\"100 Fake St.\").\n- **neighborhood**: The neighborhood name (\"Upper West Side\").\n- **city**: The city name (\"Milwaukee\").\n- **county**: The county name (\"Boone County\").\n- **state**: Object with **name** (\"California\") and **abbr** (\"CA\").\n- **country**: Object with **name** (\"United States\") and **abbr** (ISO code, \"US\").\n- **district**: Only for **political_district** locations:\n  - **kind**: One of `ward`, `us_house`, `state_senate`, `state_house`, `city_council`, `precinct`, `other`.\n  - **number**: The district or ward number as digits (\"8\", \"15\", \"4-2\"). Infer digits from ordinals when possible.\n  - **ordinal**: Optional spoken ordinal (\"Eighth\").\n  - **scope**: One of `federal`, `state`, `county`, `city`.\n\nDo not infer information beyond these rules, except **country**, which you should include whenever reasonably inferable (usually US). Return empty objects or strings for components that do not apply.\n\n## Editorial role (nature)\n\nSet exactly one primary **`nature`** per location:\n\n- **primary** — Where the main news event happens: crime scene, construction site, game venue, key meeting place.\n- **secondary** — A consequential supporting location (hospital after a crash).\n- **subject** — The place is the focus of coverage: venue profile, restaurant review, list item.\n- **context** — Background or non-event reference (policy backdrop, regional characterization).\n- **historical** — Cited for past events, precedent, or historical comparison (\"similar floods in 1927\"); matters as history, not the current scene.\n- **person** — Tied to a person: where they were quoted, hometown, employer campus.\n- **unknown** — Only when none of the above applies.\n\nOptionally include **`nature_secondary_tags`**: an array of additional labels from the same vocabulary when a place clearly plays more than one role.\n\n`description` remains the human-readable sentence; `nature` is the controlled vocabulary.\n\n## Mentions in the story (`mentions`)\n\nEvery location object includes a **`mentions`** array. Each element is an object with exactly one key, **`text`**: a verbatim sentence or clause from the story (prefer a full sentence or paragraph for context).\n\n1. Include **every** editorial mention of the same real-world place, even repeats (\"Ohio\" in the lede and again later → two mention objects).\n2. Never use plain strings; always objects with `text`.\n3. Set **`original_text`** to the first mention's `text` (identical string to `mentions[0].text`).\n\nExample (braces doubled so they are literal in this template):\n\n```json\n\"mentions\": [\n  {{ \"text\": \"Ohio lawmakers advanced the bill Tuesday.\" }},\n  {{ \"text\": \"Back in Ohio, the governor said he would sign it.\" }}\n],\n\"original_text\": \"Ohio lawmakers advanced the bill Tuesday.\"\n```\n\n## Required fields\n\n- **original_text**: the paragraph the location was extracted from, verbatim (must match `mentions[0].text`).\n- **description**: 1–2 concise, journalistic sentences explaining why this geography matters, written as if describing the events for residents of that place. Do not reference the broader story.\n- **nature** (string) and optionally **nature_secondary_tags** (array).\n\n## Geocode hints (`geocode_hints`)\n\nInclude a string field **`geocode_hints`** on every location: short, actionable prose from the story **not already obvious** from `location`, `components`, or `original_text` — material that disambiguates duplicate names, narrows vague geography, or relates this mention to other sites in the article.\n\n1. Be concise — one or two sentences, under ~400 characters.\n2. Add information; don't repeat the verbatim quote.\n3. Use `\"\"` when nothing beyond the structured fields is needed.\n\nExamples:\n\n- `\"Story identifies this as the East Lake St. café location; mayor spoke outside after the rally, not the roasting warehouse mentioned earlier.\"`\n- `\"Industrial pocket east of the river where overnight truck queues were described two paragraphs above.\"`\n\n## Street-level kind (`address_place_kind`)\n\nFor each location whose type is **address**, **intersection_road**, **intersection_highway**, **street_road**, or **span**, add a top-level string field **`address_place_kind`**:\n\n- **`public_named`** — A named business, landmark, civic building, school, hospital, or other identifiable public or semi-public place a member of the public could realistically **enter** as customer, patron, patient, student, or guest — even when the string looks like an address.\n- **`private_residence`** — Legacy value name; do **not** read it as \"homes only.\" Use it for anything that is **not** a named public venue: private homes, apartments, anonymous residential blocks (generic \"N00 block of …\" reading as housing), road or highway intersections cited as crime/crash scenes with no named landmark, PO boxes and mail-only addresses, generic parking lots or stretches of pavement. Prefer `public_named` only when the text clearly identifies a specific business, institution, or landmark there.\n- **`unknown`** — You cannot tell from the article; prefer this over guessing.\n\nBase the judgment on `original_text`, `description`, and full story context. For all other types (city, neighborhood, place, natural, etc.), **omit** `address_place_kind` entirely.\n\n## Output format\n\n**IMPORTANT**: Return ONLY valid JSON. Do not include any explanatory text before or after the JSON.\n\n## Text to Analyze\n\n{text}\n",
    "output_format_file": "prompts/_output_format.json",
    "output_mode": "compact",
    "llmTimeout": 600,
    "output_format": "{\n  \"locations\": [\n    {\n      \"location\": \"100 Fake St., Minneapolis, MN\",\n      \"type\": \"address_intersection\",\n      \"address_place_kind\": \"unknown\",\n      \"original_text\": \"The car crash occurred on the 100 block of Fake St.\",\n      \"mentions\": [\n        { \"text\": \"The car crash occurred on the 100 block of Fake St.\" }\n      ],\n      \"description\": \"A car crash happened at the 100 block of Fake St.\",\n      \"nature\": \"primary\",\n      \"nature_secondary_tags\": [],\n      \"geocode_hints\": \"\",\n      \"components\": {\n        \"place\": {},\n        \"street_road\": {},\n        \"span\": {},\n        \"address\": \"100 Fake St.\",\n        \"neighborhood\": \"\",\n        \"city\": \"Minneapolis\",\n        \"county\": \"\",\n        \"state\": {\n          \"name\": \"Minnesota\",\n          \"abbr\": \"MN\"\n        },\n        \"country\": {\n          \"name\": \"United States\",\n          \"abbr\": \"US\"\n        }\n      }\n    },\n    {\n      \"location\": \"Joe's Department Store, Chicago, IL\",\n      \"type\": \"place\",\n      \"original_text\": \"Bob Smith, who visiting at Joe's Department Store in Chicago, said he supported better agriculture policy.\",\n      \"description\": \"Bob Smith, a farmer who supports better agriculture policy, was visiting at Joe's Department Store in Chicago.\",\n      \"nature\": \"person\",\n      \"nature_secondary_tags\": [],\n      \"geocode_hints\": \"Named Chicago retail store visited during agriculture-policy discussion; no street given—likely need directory or chain locator context.\",\n      \"components\": {\n        \"place\": {\n          \"name\": \"Joe's Department Store\",\n          \"natural\": false,\n          \"addressable\": true\n        },\n        \"street_road\": {},\n        \"span\": {},\n        \"address\": \"\",\n        \"neighborhood\": \"\",\n        \"city\": \"Chicago\",\n        \"county\": \"\",\n        \"state\": {\n          \"name\": \"Illinois\",\n          \"abbr\": \"IL\"\n        },\n        \"country\": {\n          \"name\": \"United States\",\n          \"abbr\": \"US\"\n        }\n      }\n    },\n    {\n      \"location\": \"8th Ave S., Chicago, IL\",\n      \"type\": \"street_road\",\n      \"address_place_kind\": \"public_named\",\n      \"original_text\": \"The robberies occurred in several places along 8th Ave S. in Chicago\",\n      \"description\": \"8th Ave S. was the location of several robberies\",\n      \"nature\": \"primary\",\n      \"nature_secondary_tags\": [],\n      \"geocode_hints\": \"South Side corridor referenced as a pattern of robberies along the avenue in Chicago.\",\n      \"components\": {\n        \"place\": {},\n        \"street_road\": {\n          \"name\": \"8th Ave. S.\",\n          \"boundary\": \"Chicago, IL\"\n        },\n        \"span\": {},\n        \"address\": \"8th Ave S.\",\n        \"neighborhood\": \"\",\n        \"city\": \"Chicago\",\n        \"county\": \"\",\n        \"state\": {\n          \"name\": \"Illinois\",\n          \"abbr\": \"IL\"\n        },\n        \"country\": {\n          \"name\": \"United States\",\n          \"abbr\": \"US\"\n        }\n      }\n    },\n    {\n      \"location\": \"Phoenix, AZ\",\n      \"type\": \"city\",\n      \"original_text\": \"It was warmer in Phoenix than in Minneapolis this week.\",\n      \"description\": \"Phoenix was warmer than Minneapolis during the week of July 5.\",\n      \"nature\": \"context\",\n      \"nature_secondary_tags\": [],\n      \"geocode_hints\": \"\",\n      \"components\": {\n        \"place\": {},\n        \"street_road\": {},\n        \"span\": {},\n        \"address\": \"\",\n        \"neighborhood\": \"\",\n        \"city\": \"Phoenix\",\n        \"county\": \"\",\n        \"state\": {\n          \"name\": \"Arizona\",\n          \"abbr\": \"AZ\"\n        },\n        \"country\": {\n          \"name\": \"United States\",\n          \"abbr\": \"US\"\n        }\n      }\n    },\n    {\n      \"location\": \"Hennepin Ave. between W. 26th St. and W. 28th St., Minneapolis, MN\",\n      \"type\": \"span\",\n      \"address_place_kind\": \"public_named\",\n      \"original_text\": \"The parade will happen on Hennepin Ave. between W. 26th St. and W. 28th St.\",\n      \"description\": \"A parade is happening along this stretch of Hennepin Ave. in Minneapolis.\",\n      \"nature\": \"primary\",\n      \"nature_secondary_tags\": [\"context\"],\n      \"geocode_hints\": \"Parade route segment on Hennepin between W. 26th and W. 28th St. in Minneapolis.\",\n      \"components\": {\n        \"place\": {},\n        \"street_road\": {},\n        \"span\": {\n          \"start\": {\n            \"type\": \"intersection\",\n            \"location\": \"Hennepin Ave. and W. 26th St., Minneapolis, MN\"\n          },\n          \"end\": {\n            \"type\": \"intersection\",\n            \"location\": \"Hennepin Ave. and W. 28th St., Minneapolis, MN\"\n          }\n        },\n        \"address\": \"\",\n        \"neighborhood\": \"\",\n        \"city\": \"Minneapolis\",\n        \"county\": \"\",\n        \"state\": {\n          \"name\": \"Minnesota\",\n          \"abbr\": \"MN\"\n        },\n        \"country\": {\n          \"name\": \"United States\",\n          \"abbr\": \"US\"\n        }\n      }\n    },\n    {\n      \"location\": \"Hopkins High School, Minnetonka, MN\",\n      \"type\": \"place\",\n      \"original_text\": \"St. Louis Park 57 Hopkins 54\",\n      \"description\": \"Hopkins boys basketball score line; Hopkins here is the high school program, not the city of Hopkins, Minn.\",\n      \"nature\": \"primary\",\n      \"nature_secondary_tags\": [],\n      \"geocode_hints\": \"Prep scoreboard line; token expands to Hopkins High School (district serves Minnetonka area). Other team on the line is St. Louis Park High School.\",\n      \"components\": {\n        \"place\": {\n          \"name\": \"Hopkins High School\",\n          \"natural\": false,\n          \"addressable\": true\n        },\n        \"street_road\": {},\n        \"span\": {},\n        \"address\": \"\",\n        \"neighborhood\": \"\",\n        \"city\": \"Minnetonka\",\n        \"county\": \"\",\n        \"state\": {\n          \"name\": \"Minnesota\",\n          \"abbr\": \"MN\"\n        },\n        \"country\": {\n          \"name\": \"United States\",\n          \"abbr\": \"US\"\n        }\n      }\n    },\n    {\n      \"location\": \"Ohio\",\n      \"type\": \"state\",\n      \"original_text\": \"Ohio lawmakers advanced the bill Tuesday.\",\n      \"mentions\": [\n        { \"text\": \"Ohio lawmakers advanced the bill Tuesday.\" },\n        { \"text\": \"Back in Ohio, the governor said he would sign it.\" }\n      ],\n      \"description\": \"Ohio is central to the legislative story in the lede and again near the close.\",\n      \"nature\": \"primary\",\n      \"nature_secondary_tags\": [],\n      \"geocode_hints\": \"\",\n      \"components\": {\n        \"place\": {},\n        \"street_road\": {},\n        \"span\": {},\n        \"address\": \"\",\n        \"neighborhood\": \"\",\n        \"city\": \"\",\n        \"county\": \"\",\n        \"state\": {\n          \"name\": \"Ohio\",\n          \"abbr\": \"OH\"\n        },\n        \"country\": {\n          \"name\": \"United States\",\n          \"abbr\": \"US\"\n        }\n      }\n    }\n  ]\n}\n"
  }
};

import { useEffect, useMemo, useState } from 'react'
import { NodePanelTabGate } from '@/components/node-panel/NodePanelTabContext'
import type { GraphPanelContext, ProjectAiModelOption } from '@/components/NodePanel'
import { getNodeOutputById, type NodeOutputLookupSpec } from '@/lib/nodeOutputs'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import {
  INVALID_AI_MODEL_SELECTION_VALUE as INVALID_SELECTION_VALUE,
  catalogToSelectOptions,
  hasExplicitAiModelChoice,
  resolvedAiModelSelectValue,
} from '@/lib/nodePanelAiModel'

const DEFAULTS = {
  model: '',
  aiModelConfigId: null as string | null,
}

const MODEL_KEYS = {
  configIdKey: 'aiModelConfigId',
  modelKey: 'model',
} as const

function resolvedModelSelectValue(
  params: Record<string, unknown>,
  catalog: ProjectAiModelOption[],
): string {
  return resolvedAiModelSelectValue(params, catalog, MODEL_KEYS)
}

function hasExplicitModelChoice(data: Record<string, unknown>): boolean {
  return hasExplicitAiModelChoice(data, MODEL_KEYS)
}

interface PlaceExtractPanelProps {
  node: any
  currentRun?: any
  editMode?: boolean
  setNodes?: (nodes: any) => void
  graphContext?: GraphPanelContext
  nodeOutputLookupSpec?: NodeOutputLookupSpec | null
}

function formatSamplePlaceTitle(location: {
  location?: unknown
  original_text?: string
}): string {
  const loc = location.location
  if (typeof loc === 'string') {
    return loc
  }
  if (loc && typeof loc === 'object' && 'full' in loc) {
    const full = (loc as { full?: unknown }).full
    if (typeof full === 'string' && full.length > 0) {
      return full
    }
  }
  return typeof location.original_text === 'string' ? location.original_text : ''
}

export default function PlaceExtractPanel({
  node,
  editMode,
  setNodes,
  currentRun,
  graphContext,
  nodeOutputLookupSpec,
}: PlaceExtractPanelProps) {
  const merged = {
    ...DEFAULTS,
    ...(nodeMetadata.defaultParams || {}),
    ...(node.data || {}),
  }
  const paramsRecord = merged as Record<string, unknown>

  const projectId = graphContext?.projectId ?? null
  const [catalogRows, setCatalogRows] = useState<ProjectAiModelOption[]>([])
  const [catalogLoading, setCatalogLoading] = useState(false)
  const [catalogError, setCatalogError] = useState<string | null>(null)

  useEffect(() => {
    const fetcher = graphContext?.fetchProjectAiModels
    if (projectId == null || fetcher == null) {
      setCatalogRows([])
      setCatalogError(null)
      setCatalogLoading(false)
      return
    }
    let cancelled = false
    setCatalogLoading(true)
    setCatalogError(null)
    void fetcher(['text', 'json'])
      .then((rows) => {
        if (!cancelled) {
          setCatalogRows(rows)
          setCatalogLoading(false)
        }
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setCatalogRows([])
          setCatalogError(e instanceof Error ? e.message : 'Could not load models.')
          setCatalogLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [projectId, graphContext?.fetchProjectAiModels])

  const modelSelectOptions = useMemo(() => catalogToSelectOptions(catalogRows), [catalogRows])

  const resolvedUnderlying = resolvedModelSelectValue(paramsRecord, catalogRows)
  const selectionValid =
    resolvedUnderlying !== '' && modelSelectOptions.some((o) => o.selectValue === resolvedUnderlying)

  const showInvalidPersisted =
    Boolean(editMode && setNodes && projectId != null && catalogRows.length > 0 && !catalogLoading) &&
    hasExplicitModelChoice((node.data || {}) as Record<string, unknown>) &&
    !selectionValid

  const radixSelectValue = selectionValid
    ? resolvedUnderlying
    : showInvalidPersisted
      ? INVALID_SELECTION_VALUE
      : undefined

  useEffect(() => {
    if (!editMode || !setNodes || catalogLoading || catalogRows.length === 0) return
    const data = (node.data || {}) as Record<string, unknown>
    if (hasExplicitModelChoice(data)) return
    const first = modelSelectOptions[0]
    if (!first) return
    const providerModelId = first.providerModelId
    const cid = first.configId ?? null
    setNodes((nds: any[]) =>
      nds.map((n: any) =>
        n.id === node.id
          ? {
              ...n,
              data: {
                ...(n.data || {}),
                model: providerModelId,
                aiModelConfigId: cid,
              },
            }
          : n,
      ),
    )
  }, [
    editMode,
    setNodes,
    catalogLoading,
    catalogRows,
    modelSelectOptions,
    node.id,
    node.data,
  ])

  const isDisabled = !(editMode && setNodes)

  const handleModelChange = (selectValue: string) => {
    if (!setNodes || selectValue === INVALID_SELECTION_VALUE) return
    const row = modelSelectOptions.find((o) => o.selectValue === selectValue)
    const providerModelId = row?.providerModelId ?? selectValue
    const configId = row?.configId
    setNodes((nds: any[]) =>
      nds.map((n: any) =>
        n.id === node.id
          ? {
              ...n,
              data: {
                ...(n.data || {}),
                model: providerModelId,
                aiModelConfigId: configId ?? null,
              },
            }
          : n,
      ),
    )
  }

  const displayModelLabel =
    modelSelectOptions.find((o) => o.selectValue === resolvedUnderlying)?.label ??
    (showInvalidPersisted
      ? 'Previous model unavailable'
      : resolvedUnderlying !== ''
        ? String(paramsRecord.model ?? resolvedUnderlying)
        : '—')

  const nodeOutput = getNodeOutputById(
    currentRun?.node_outputs as Record<string, unknown> | undefined,
    node.id,
    nodeOutputLookupSpec ?? undefined,
  )
  const latestData = (nodeOutput as { locations?: unknown[] } | null | undefined) || null

  return (
    <>
      <NodePanelTabGate tab="info">
        <div className="space-y-2">
          <Label className="text-sm font-medium">Input placeholders</Label>
          <p className="text-sm text-muted-foreground mt-1">
            Pull fields from upstream JSON into the prompt using these tokens:
          </p>
          <ul className="list-disc list-inside text-xs mt-2 space-y-1 text-muted-foreground">
            <li>
              <code className="bg-muted px-1 rounded">{'{text}'}</code> — plain text or the{' '}
              <code className="bg-muted px-1 rounded">text</code> field from JSON input
            </li>
            <li>
              <code className="bg-muted px-1 rounded">{'{url}'}</code> —{' '}
              <code className="bg-muted px-1 rounded">url</code> field
            </li>
            <li>
              <code className="bg-muted px-1 rounded">{'{results.images}'}</code> — nested paths
              (e.g. <code className="bg-muted px-1 rounded">results.images</code>)
            </li>
            <li>
              <code className="bg-muted px-1 rounded">{'{results.caption}'}</code> — one field from
              each item in an array
            </li>
            <li>
              <code className="bg-muted px-1 rounded">{'{results.caption, id}'}</code> — multiple
              fields per array element
            </li>
            <li>
              <code className="bg-muted px-1 rounded">{'{raw}'}</code> — entire input object as JSON
            </li>
          </ul>
        </div>
      </NodePanelTabGate>

      <NodePanelTabGate tab="settings">
        <div>
          <Label className="text-sm font-medium">Extraction model</Label>
          {editMode && setNodes ? (
            <>
              {(projectId == null || graphContext?.fetchProjectAiModels == null) && (
                <p className="text-xs text-muted-foreground mt-2">
                  Save this flow under a project to choose models your organization enabled for
                  this project.
                </p>
              )}
              {projectId != null && catalogLoading && (
                <p className="text-xs text-muted-foreground mt-2">Loading models…</p>
              )}
              {catalogError != null && catalogError !== '' ? (
                <p className="text-xs text-destructive mt-2">{catalogError}</p>
              ) : null}
              {!catalogLoading &&
                !catalogError &&
                projectId != null &&
                graphContext?.fetchProjectAiModels != null &&
                modelSelectOptions.length === 0 && (
                  <p className="text-xs text-muted-foreground mt-2">
                    No models available for this project yet. Ask an administrator to enable
                    models for your organization, then turn them on for this project in project
                    settings if needed.
                  </p>
                )}
              {showInvalidPersisted && (
                <p className="text-xs text-muted-foreground mt-2">
                  The saved model is no longer available. Choose another model below.
                </p>
              )}
              <Select
                value={radixSelectValue}
                onValueChange={handleModelChange}
                disabled={isDisabled || modelSelectOptions.length === 0}
              >
                <SelectTrigger className="h-8 text-xs mt-2">
                  <SelectValue placeholder="Choose a model" />
                </SelectTrigger>
                <SelectContent>
                  {showInvalidPersisted ? (
                    <SelectItem disabled value={INVALID_SELECTION_VALUE}>
                      Saved model unavailable
                    </SelectItem>
                  ) : null}
                  {modelSelectOptions.map((m) => (
                    <SelectItem key={`pe-${m.selectValue}`} value={m.selectValue}>
                      {m.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground mt-1">
                Set available models in your organization settings.
              </p>
            </>
          ) : (
            <>
              <div className="flex justify-between items-center p-2 bg-muted rounded mt-2">
                <span className="text-muted-foreground">Extraction model</span>
                <span className="font-medium text-xs">{displayModelLabel}</span>
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                Set available models in your organization settings.
              </p>
            </>
          )}
        </div>
      </NodePanelTabGate>

      <NodePanelTabGate tab="prompts">
        <div>
          <Label className="text-sm font-medium">Prompt</Label>
          {editMode && setNodes ? (
            <Textarea
              value={node.data?.prompt || nodeMetadata.defaultParams?.prompt || ''}
              onChange={(e) => {
                setNodes((nds: any[]) =>
                  nds.map((n: any) =>
                    n.id === node.id ? { ...n, data: { ...n.data, prompt: e.target.value } } : n,
                  ),
                )
              }}
              placeholder="Enter custom prompt"
              className="mt-2 min-h-[200px] px-3 py-2 text-xs border border-input bg-background rounded-md focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 font-mono"
            />
          ) : (
            <div className="mt-2 p-2 bg-muted rounded max-h-48 overflow-y-auto">
              <pre className="text-xs whitespace-pre-wrap font-mono">
                {node.data?.prompt || nodeMetadata.defaultParams?.prompt || 'Using default prompt'}
              </pre>
            </div>
          )}
          <p className="text-xs text-muted-foreground mt-1">Edit extraction prompt.</p>
        </div>
      </NodePanelTabGate>

      <NodePanelTabGate tab="outputs">
        <div className="space-y-4">
          <div>
            <Label className="text-sm font-medium">Output format</Label>
            <Textarea
              readOnly
              value={nodeMetadata.defaultParams?.output_format?.trim() || ''}
              placeholder="Run node sync (apps/agate-ui) after changing prompts/_output_format.json"
              className="mt-2 min-h-[120px] px-3 py-2 text-xs border border-input bg-muted/50 rounded-md font-mono cursor-default"
              spellCheck={false}
            />
            <p className="text-xs text-muted-foreground mt-1">For reference only.</p>
          </div>

          {latestData && latestData.locations && (
            <div className="border-t pt-4">
              <Label className="text-sm font-medium">Latest run</Label>
              <div className="mt-2 space-y-2">
                <div className="text-xs text-muted-foreground">
                  <div>Places found: {latestData.locations.length}</div>
                </div>

                {latestData.locations.length > 0 && (
                  <div>
                    <Label className="text-xs font-medium">Sample places</Label>
                    <div className="mt-1 space-y-1 max-h-32 overflow-y-auto">
                      {latestData.locations.slice(0, 3).map((location: any, index: number) => (
                        <div key={index} className="text-xs p-2 bg-muted rounded">
                          <div className="font-medium">{formatSamplePlaceTitle(location)}</div>
                          {location.description && (
                            <div className="text-muted-foreground">{location.description}</div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </NodePanelTabGate>
    </>
  )
}
