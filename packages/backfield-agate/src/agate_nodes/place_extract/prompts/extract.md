# Location Extraction Service

Extract **editorially relevant, literal, physical locations** from the text provided at the end of this prompt. Do **not** be maximalist: omit places that are only figurative, institutional shorthand, overly generic, or otherwise not useful as real-world geography for this story.

## Editorial relevance (apply before extracting)

**Include** locations that matter to the narrative as geography, for example:
- Where key events occurred, or where affected places are described (venues, parks, public spaces residents would recognize).
- Where sources or characters are **from**, or biographical context (lived, worked, grew up, went to school) when tied to a real place.
- Scene-setting or dateline-style places when they indicate where reporting or events occur.
- **Lawmaker districts**: e.g. for "Joe Smith, R-Maple Grove," include **Maple Grove, MN** as a relevant place.

**Exclude** (do not output) mentions that are not literal geography for this story, including:
- **Metonyms** (e.g. "Washington" for the federal government; "City Hall" for city government; a city name for a sports team). **Exception:** in **high school / prep scorelines**, tokens that name **schools** follow the **scoreboard / school** rules under **Institutions**—do not drop them as “city for team” metonyms when they are functioning as **school** names.
- **Synecdoche, metaphor, idiom, cliché, hyperbole, allegory**, or **historical/cultural** uses where the place is not the physical setting.
- **Generic or ambiguous** sites when a specific location cannot be identified (e.g. "Target, Minneapolis, MN" without a specific store; unnamed "bank" or "gas station" unless the story pins down a distinct site).
- **Countries and continents** as standalone items when they are too broad to geocode usefully (e.g. "United States," "North America") unless the story truly hinges on that geography at country scale.
- **One object per place**: each distinct real-world location should appear **once** in the output as a single location object. If the same place is mentioned in multiple sentences or paragraphs, include **every** verbatim snippet in that object’s **`mentions`** array (see below)—do not omit later mentions. If the same place appears at multiple levels of detail (e.g. a city inside an intersection), keep the **most detailed** instance and omit redundant broader or narrower duplicates that repeat the same site.
- **Streets as components**: if a street is already represented inside an **intersection** or **span**, do not also emit it as a separate **street_road** object for the same coverage.
- **Events, proceedings, and activities with place-like names** — Do **not** output a location when the mention is really **what happened** or **what kind of gathering** it is, not a **mappable site**. Examples: **government or court proceedings** named after a body ("U.S. Senate Judiciary Committee Hearing," "House Ways and Means markup"), **generic program phases** ("training camp," "minicamp," "OTAs," "organized team activities") when the story means the **period or activity**, not a **specific named facility**; **ceremonies or sessions** without a named room, building, campus, park, or address. If the article **does** anchor the event at a **named venue, campus, arena, courthouse wing, or street address**, extract **that** geography (and any city/state/dateline already implied)—**not** the hearing or camp **title** as a **`place`**.
- **Dateline and lede text as `place` rows** — When a story opens with `"CITY — …"`, emit a separate **`city`** row for the dateline city when editorially relevant. **Never** emit the headline clause, program pitch, policy description, or whole lede paragraph as a **`place`** `location` string.
- **Narrative and policy phrasing** — Do **not** emit phrases that describe what a program does, a pilot’s goals, or abstract civic activity as a **`place`** (e.g. "helping residents take a more direct role in neighborhood improvements").
- **Speaker attributions and quote clauses** — Do **not** emit sentences or clauses whose subject is a person or office (`"Mayor X said…"`, `"City Council President Y said the pilot will…"`) as **`place`** rows. Extract **named venues** mentioned inside those clauses (e.g. **North Commons Park**, **East Lake Library**) instead.
- **Generic facility categories** — Do **not** emit bare generic nouns (`libraries`, `recreation centers`, `community spaces`, `schools`, `parks`) unless the text names a **specific** branch, campus, building, or park (e.g. **East Lake Library** yes; **libraries** no).

**Institutions and organizations** (special case):
- If an organization is named **without** a specific site (headquarters, campus, building, address), **omit** it as a location (e.g. "The ACLU protested" — not a mappable place).
- **Agencies** (city/county/state departments, unions, associations): omit unless the story places an event at their **building or property**.
- **Small businesses** named in a real-world context are often relevant; **large corporate HQs** are usually irrelevant unless an event occurred there (contrast "Target Corp. objected" vs "employees gathered at Target headquarters").
- **High school sports and contests**: schools and contest-related locations mentioned in that context should be **included**.
- **Scoreboards and game summaries** (e.g. "St. Louis Park 57 Hopkins 54", "Belvidere 55, Woodstock 53", "Brother Rice 48 Marist 41"): short tokens refer to **school teams / campuses**, not the homonymous **cities** unless the article clearly means the municipality. For each side, use **`type`: `place`**, set **`components.place.name`** to the **full conventional school name** from your general knowledge when it is a well-known pairing (e.g. **Brother Rice High School**, **St. Louis Park High School**, **Hopkins High School**, **Belvidere High School**, **Woodstock High School**), and set **`location`** to a **geocodable string** (typically expanded school name plus **city and state** inferable from the story or from standard associations—e.g. Hopkins High School with **Minnetonka, MN** when that is the usual campus locale). **Do not** emit standalone **`city`** objects for those tokens when they are **only** school names in a scoreline. **Never** emit the bare scoreline token alone as `location` or `components.place.name` (`Belvidere`, `Woodstock`, `Smith`, `Park`).
- **Scheduled scoreboard lines without final scores** (e.g. "Hinsdale Adventist at Calvary Christian", "Wolcott at Rochelle Zell", "Beacon at Northtown"): treat **both** sides as **school teams / campuses**, not municipalities. Emit **two separate `place` rows**—one for the away team and one for the home team. Expand each to a conventional school name plus **city and state** when you know it (e.g. **Rochelle Zell Jewish High School, Deerfield, IL**). **Never** use **`other`** for these tokens, and **never** put a school name in **`components.city`**. Do **not** omit the away team when only the home team appears after **"at"**.

**Regions and ambiguity**:
- Prefer **specific** geographies. Omit vague "store, Minneapolis, MN" or "rooftop, St. Cloud, MN" when the same area is already covered by clearer objects.
- **Named regions** (e.g. "Southwest Missouri," "the Pacific Northwest," "Northern Arizona") can be relevant; when you include a sub-region, also include the **containing** city/state/county objects when the text supports them (e.g. "Northern Arizona" and "Arizona"; "South Los Angeles" and "Los Angeles").

## Overview

Geographic boundaries, streets, neighborhoods, regions, and **named** businesses and landmarks may appear when they pass the editorial rules above. If multiple distinct relevant places appear in a passage, extract each qualifying one.

Classify and format every **included** location according to the following rules.

## Classification Rules

### Type Classification

Classify each location by the type of geography it represents. Valid types are:

- **place**: A **named** physical site people could find on a map—a building, campus, business, landmark, park, stadium, **named bridge**, etc. **Not** an **event title, hearing name, or activity label** by itself (e.g. a string ending in **Hearing**, **Markup**, **Session**, or generic **training camp** when it describes the **event or phase**, not a venue—see **Exclude → Events, proceedings…**). For example: "Target Headquarters," "Roseville Mall," "White House," or **named bridges and crossings as landmarks** (e.g. "Stone Arch Bridge," "Mackinac Bridge"). Might contain a city or other geographic boundary information but does not contain an address. Natural places, such as lakes, rivers and mountains should be considered **natural** types, not **place**. **Bridges:** treat a **named bridge** as **place** when it is a venue or landmark; use **span** only when the article describes a **segment of roadway** between two explicit endpoints (see **span**).
- **address**: A street address, which must include a house number. This might include block numbers, such as "500 block of Portland Ave." If a place also includes an address, extract only the address and classify it as an "address." Streets or roads without some kind of house number are not addresses.
- **intersection_road**: An intersection of two non-highway roads, such as Main St. and 2nd St. Even if the story does not describe an intersection in a single string, you may infer it using other information in the article.
- **intersection_highway**: An intersection where one or both components is an interstate or highway, such as "I-94 and Selby Ave." or "Hwy. 20 and Hwy. 36"
- **street_road**: A single street, road or highway without other geographic information or context, such as an address. For example: "41st St. N.," "Hennepin Ave." or "I-35".
- **span**: A span of road between two points. For example: "I-35 between Pine City and Hinckley" or "Lake Street from Nicollet Avenue S. to 28th Avenue S.". A span requires both a road and two reference points marking the beginning and end. Just a road, or a road with only one reference point, should use other types as appropriate. **Do not** use **span** for a **named bridge** as a landmark unless the text explicitly frames a **stretch of road on the bridge** between two endpoints; otherwise use **place**.
- **neighborhood**: Explicit mentions of neighborhood names. Do not include the word "neighborhood" or any other descriptor in the output. Only the name. So "North Loop" not "North Loop neighborhood".
- **region_city**: A description of an area within a city that is not a named place or neighborhood, such as "South Minneapolis," or the "Chicago lakefront". It may also refer to named mass-transit lines, such as "The Green Line" light rail in Minneapolis. In all of these cases, also extract the city as a separate object. This can also apply to counties, such as "western Hennepin County, MN"
- **city**: The name of a city
- **county**: The name of a county in a state
- **region_state**: The name of a region or a general area being described within a state, such as Northern Wisconsin. In these cases, also extract the state as a separate object. Places that reference large cities and their surrounding areas, like "The Chicago Area" or "the East Bay" are region_states.
- **state**: A state
- **region_national**: The name of a region or a general area being described within the United States, such as the South.
- **country**: A country
- **political_district**: A **numbered or ordinally identified** political or administrative boundary used as geography in the story—**U.S. congressional districts**, state house or senate districts, **city wards** or council districts, voting **precincts** when identified by number, and similar. Use this type when the story is about **that district as a jurisdiction** (elections, representation, redistricting, who represents whom), not when a district name is only incidental color. **Do not** use it for broad colloquial regions ("the South"), entire **counties** (use **county**), generic **neighborhoods** (use **neighborhood**), or **region_city** blobs ("south side of Chicago" without a formal district number). When in doubt between **political_district** and **region_city**, prefer **political_district** only if the text clearly references a **formal district** with a **stable number or ordinal** (e.g. "8th Congressional District," "Ward 15," "Senate District 42").
- **natural**: A specific natural feature, such as a river, lake or mountain range. These are generally specific and named features. General descriptions of natural regions, like "the California coast" should be considered regions.
- **other**: Anything that doesn't fit into the categories above

## Formatting Rules

- Return geocodable address strings in all cases where doing so is possible. For example, if a city is mentioned, like "Minnetonka" you should return "Minnetonka, MN" if it is clear from the story that Minnetonka, MN is the city being referenced. The same logic should be applied to places, addresses, intersections, streets, and other geographies. You may use the context of the story to fill out information that might not specifically be mentioned. States and countries can be presented on their own: "Minnesota" and not "Minnesota, MN" for example.
- The **`location`** field must always be a **geocodable proper-name string** (city, venue, street, park, etc.)—**never** a sentence, headline fragment, quote clause, or narrative phrase copied from the story body.

- Geocodable address strings for neighborhoods and regions should include their city and state where possible. For example "Longfellow, Minneapolis, MN"

- Block numbers should be returned as addresses. For example, "200 block of Smith St." should be returned as "200 Smith St., Minneapolis, MN"

- If a range of street numbers is offered in a single string, such as 7603–7619 N. Main St., include only the first number — in this case, 7603 N. Main St.

- Natural places should generally return only the name of the place and the state in which they are attributed, if possible. For example "Chicago River, IL"

- Non-geocodable details (e.g., "eastbound lanes" or vague references like "metro" without a clear definition) should be omitted unless they are necessary for meaningful distinction.

- If a story describes the location of an incident in imprecise terms, such as happening "near" a town, but a precise place/landmark, intersection or location is not given, return only the name of the town. For instance "Highway 61 near Grand Marais" should just return "Grand Marais, MN"

- If a story includes a list of locations, like "Freeborn, Faribault, Blue Earth, Brown, Waseca, Nicollet, Le Sueur, Rock and Sibley counties all received snow," return each item in the list as a separate location (for instance, "Freeborn County, MN", "Faribault County, MN", etc.) **only when each is editorially relevant** under the rules above.

- Identifiable places and landmarks should be included with as much geographic information as can be inferred from the story. For instance, if a story mentions "Memorial Hospital," and later the context makes it clear that the hospital in question is located in "Minneapolis," return "Memorial Hospital, Minneapolis, MN". This also applies to places that are not proper nouns. A reference to something like "Monticello nuclear power plant" should be returned as "Nuclear power plant, Monticello, MN."

- Sometimes a story might use a shorthand name to refer to a location on first reference. For example "Park" referring to "St. Louis Park High School" or "Minnetonka" referring to "Minnetonka High School". If the context of the story indicates that the shorthand refers to an entity of which you are aware or can be inferred by the text, return the complete name of that entity as a place. Be especially aware of this if the location is a school. For example, return "Crete-Monee High School" not just "Crete-Monee" if that can be inferred. The same rule applies to **prep scoreline tokens** that look like city names (`Belvidere`, `Woodstock`)—expand to the full school name, not the municipality alone.

- For street_road types, attempt first to return them with a reference city and state if such information can be inferred from the text: for example "Interstate 55, Springfield, IL". If a city cannot be inferred, include only a state if possible, such as "Interstate 35, IA". If no state can be inferred, perhaps because the story is referencing a road that crosses state boundaries, include only the name of the road: "Interstate 70".

- If a street is already listed as part of an intersection or a span, do not include it separately as a street_road.

## Component extraction

You should also separate each location into components where possible. The types of components you should capture are:

- **full**: The full geocodable string representing the location that you extract. For example, "Minneapolis, MN" or "Longfellow, Minneapolis, MN"
- **type**: The type of the location, from the list above.
- **place**: Only fill this out for named places—businesses, landmarks, **schools**, **bridges** (as landmarks or venues), and similar
  - **name**: The name of the place, for instance "Dogwood Coffee," "Hopkins High School," or "Stone Arch Bridge"
  - **natural**: Return True if the place represents a natural location that is unlikely to have a street address, such as North Cascades National Park, Island Lake, or the Mississippi River.
  - **addressable**: Return True if the place is likely to have a findable street address, such as a business, building, school or landmark. **Named bridges and similar named crossings / transport landmarks** (e.g. Marshall Avenue Bridge, Stone Arch Bridge) should be **`addressable: true`**: they geocode as distinct POIs even when the story gives no house-number line—do **not** set False only because there is no mailing-style address. Pay special attention to proper nouns, which often indicate addressable locations. Return False in all other cases.
- **street_road**: Only fill this out for street_road types, where a street or highway is named without a specific address.
  - **name**: The name of the street
  - **boundary**: A geocodable string representing the most specific neighborhood, city, county or state boundary that contains the segment of street or road in question, inferred by the context of the article.
- **span**: Only fill this out for span types, describing a section of road from one place to another. For example, "Hennepin Ave. from W. 26th St. to W. 28th St.
  - **start**: The starting point of the span. This is an object containing a "type" and "location" attribute.
    - **type**: Either city or intersection. City would be used in cases like "I-35 from Pine City to Duluth".
    - **location**: The intersection or city, formatted as a geocodable string. For example "Hennepin Ave. and W. 26th St., Minneapolis, MN." or "Pine City, MN"
  - **end**: The ending point of the span. Formatted the same as "start".
    - **type**: Either city or intersection.
    - **location**: The intersection or city, formatted as a geocodable string.
- **address**: The street address, if applicable. For example "100 Fake St."
- **neighborhood**: The name of the neighborhood, if applicable. For example "Upper West Side"
- **city**: The name of the city, if applicable. For example "Milwaukee"
- **county**: The name of the county, if applicable. For example "Boone County"
- **state**: The name of the state, if applicable.
  - **name**: The full name of the state. For example "California"
  - **abbr**: The postal abbreviation for the state. For example "CA"
- **country**: The name of the country, if applicable
  - **name**: The full name of the country. For example "United States"
  - **abbr**: The ISO 3166-1 country code for the country. For example "US"
- **district**: Only for **political_district** locations. Capture the **formal** identity so downstream systems can tell **District 7** from **District 8**.
  - **kind**: One of: `ward`, `us_house`, `state_senate`, `state_house`, `city_council`, `precinct`, `other`.
  - **number**: The district or ward **number** as in the story (digits preferred), e.g. `"8"`, `"15"`, `"4-2"` for split wards. If the story only uses ordinals ("Eighth Congressional District"), put digits in **number** when you can infer them; otherwise set **ordinal** to the spoken form and still set **number** if inferable.
  - **ordinal**: Optional spoken ordinal if useful (e.g. `"Eighth"`).
  - **scope**: One of: `federal`, `state`, `county`, `city`—whichever best matches the district's jurisdiction.

Do not infer additional information about the locations beyond what is instructed in your formatting rules. The exception of this is country, which you should always include if you can reasonably guess it (most of the time this will be US).

Return empty objects or strings in cases where a component does not apply to the geography in question.

## Editorial role (nature)

For **each** location object, set exactly one primary **`nature`** value describing how this place functions in the story:

- **primary** — Where the main news event (or events) happens: crime scene, construction site, weather-affected area, game venue, key meeting place, etc.
- **secondary** — A consequential but supporting location (e.g. hospital after a crash, secondary scene in a developing story).
- **subject** — The place is the focus of coverage: restaurant review, profile of a venue, or an item in a list (e.g. “10 best parks in San Francisco”).
- **context** — Referenced for background, history, or non-event context without being the main scene.
- **person** — Tied to a person: where they were quoted, hometown, identifying employer campus, etc.
- **unknown** — Use only when none of the above clearly applies.

Optionally include **`nature_secondary_tags`**: an array of zero or more **additional** labels drawn from the **same** vocabulary when a place clearly plays more than one role (e.g. primary scene plus **`context`**).

`description` remains the human-readable sentence; **`nature`** is the controlled vocabulary for filtering and analytics.

## Mentions in the story (`mentions`)

Every location object must include a **`mentions`** array. Each element is a JSON object with exactly one key:

- **`text`**: string — verbatim text from the story for that mention (sentence or clause; do not combine unrelated sentences). Prefer a full sentence or paragraph when that gives clearer context.

**Rules:**

1. Include **every** editorial mention of that same real-world place in the article, even when the wording repeats (e.g. "Ohio" in the lede and again near the end → two separate mention objects).
2. Do **not** use plain strings in the array; always use objects with **`text`**.
3. Set **`original_text`** to the **first** mention’s `text` (same string as `mentions[0].text`) for backward compatibility.

Example (brace characters shown doubled so they are literal in the prompt template):

```json
"mentions": [
  {{ "text": "Ohio lawmakers advanced the bill Tuesday." }},
  {{ "text": "Back in Ohio, the governor said he would sign it." }}
],
"original_text": "Ohio lawmakers advanced the bill Tuesday."
```

## Required Fields

Return the paragraph from which the location was extracted and return it as "original_text" (must match `mentions[0].text` when `mentions` is present). Ensure these are copied verbatim from the story.

Return a brief description of the nature of the location and its importance in the story under a "description" attribute.

Include **`nature`** (string, one of the values above) and optionally **`nature_secondary_tags`** (array of strings).

The description should:

1. **Be concise and clear**
2. **Explain why this geography is relevant** to the overall narrative
3. **Sound natural and journalistic**
4. **Be brief** (1-2 sentences maximum)

Generally, write this as though you are describing the events of the story for residents of the area in question. Do not make reference to the broader story. Only describe the events, localized for the audience of the geography in question.

## Geocode hints (`geocode_hints`)

For **every** location object, include a string field **`geocode_hints`**.

Purpose: give downstream geocoding agents **short, actionable prose** from the story that is **not already obvious** from `location`, `components`, or `original_text` alone—material that helps **disambiguate** duplicate names (which branch, which corridor), narrow **vague** geography (“north industrial pocket east of the river”), relate this mention to **other sites or zones** elsewhere in the article, or capture framing that pins the intended real-world site.

Guidelines:

1. **Be concise** — typically one or two sentences, or a few comma-separated clauses; prefer staying under ~400 characters.
2. **Add information**, don’t copy the verbatim quote; pull **glue** from other sentences when it helps the geocoder choose the right feature.
3. Use **`""`** (empty string) when nothing beyond `original_text` and structured fields is needed.

Illustrative examples (your output still follows the JSON schema):

- `"Story identifies this as the East Lake St. café location; mayor spoke outside after the rally, not the roasting warehouse mentioned earlier."`
- `"Industrial pocket east of the river where overnight truck queues were described two paragraphs above."`
- `"County fairgrounds hosting the livestock auction the same weekend as the storm damage."`

## Street-level: public named place vs non-public site (`address_place_kind`)

For each location whose **`type`** is one of **address**, **address_intersection** (if you use that label), **intersection_road**, **intersection_highway**, **street_road**, or **span**, add a top-level string field **`address_place_kind`** with exactly one of:

- **`public_named`** — A named business, landmark, civic building, school, hospital, retail site, or other **identifiable public or semi-public** place the story maps to real-world geography (even when the string looks like an address)—somewhere a member of the public could realistically **enter** as a customer, patron, patient, student, or guest.
- **`private_residence`** — The JSON value name is legacy; **do not read it as “homes only.”** Use it whenever the geography is **not** a named public venue the public would walk into in that role. **Include** private **homes, apartments, residential lots**, and **anonymous residential blocks** (including generic “N00 block of …” when it reads as housing). **Also include** **road or highway intersections** (or similar corners) when the story cites them as the scene of a **crime, crash, or other incident** but **no** named store, office, or landmark applies; **PO boxes** and other **mail-only** addresses; **generic parking lots, stretches of pavement, or any site that is not a building** (or named campus) **a person could enter as a member of the public**—customer, patron, patient, etc. Prefer **`public_named`** only when the text clearly identifies a **specific** business, institution, or landmark at that location.
- **`unknown`** — You cannot tell from the article; prefer this over guessing.

Base the judgment on **`original_text`**, **`description`**, and the **full story context**, not only `components`.

For **all other types** (city, neighborhood, `place`, natural, etc.), **omit** `address_place_kind` entirely.

## Output Format

**IMPORTANT**: Return ONLY valid JSON. Do not include any explanatory text before or after the JSON.

## Text to Analyze

{text}
