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
    "prompt": "# Location Extraction Service\n\nExtract **editorially relevant, literal, physical locations** from the text provided at the end of this prompt. Do **not** be maximalist: omit places that are only figurative, institutional shorthand, overly generic, or otherwise not useful as real-world geography for this story.\n\n## Editorial relevance (apply before extracting)\n\n**Include** locations that matter to the narrative as geography, for example:\n- Where key events occurred, or where affected places are described (venues, parks, public spaces residents would recognize).\n- Where sources or characters are **from**, or biographical context (lived, worked, grew up, went to school) when tied to a real place.\n- Scene-setting or dateline-style places when they indicate where reporting or events occur.\n- **Lawmaker districts**: e.g. for \"Joe Smith, R-Maple Grove,\" include **Maple Grove, MN** as a relevant place.\n\n**Exclude** (do not output) mentions that are not literal geography for this story, including:\n- **Metonyms** (e.g. \"Washington\" for the federal government; \"City Hall\" for city government; a city name for a sports team). **Exception:** in **high school / prep scorelines**, tokens that name **schools** follow the **scoreboard / school** rules under **Institutions**—do not drop them as “city for team” metonyms when they are functioning as **school** names.\n- **Synecdoche, metaphor, idiom, cliché, hyperbole, allegory**, or **historical/cultural** uses where the place is not the physical setting.\n- **Generic or ambiguous** sites when a specific location cannot be identified (e.g. \"Target, Minneapolis, MN\" without a specific store; unnamed \"bank\" or \"gas station\" unless the story pins down a distinct site).\n- **Countries and continents** as standalone items when they are too broad to geocode usefully (e.g. \"United States,\" \"North America\") unless the story truly hinges on that geography at country scale.\n- **One object per place**: each distinct real-world location should appear **once** in the output as a single location object. If the same place is mentioned in multiple sentences or paragraphs, include **every** verbatim snippet in that object’s **`mentions`** array (see below)—do not omit later mentions. If the same place appears at multiple levels of detail (e.g. a city inside an intersection), keep the **most detailed** instance and omit redundant broader or narrower duplicates that repeat the same site.\n- **Streets as components**: if a street is already represented inside an **intersection** or **span**, do not also emit it as a separate **street_road** object for the same coverage.\n- **Events, proceedings, and activities with place-like names** — Do **not** output a location when the mention is really **what happened** or **what kind of gathering** it is, not a **mappable site**. Examples: **government or court proceedings** named after a body (\"U.S. Senate Judiciary Committee Hearing,\" \"House Ways and Means markup\"), **generic program phases** (\"training camp,\" \"minicamp,\" \"OTAs,\" \"organized team activities\") when the story means the **period or activity**, not a **specific named facility**; **ceremonies or sessions** without a named room, building, campus, park, or address. If the article **does** anchor the event at a **named venue, campus, arena, courthouse wing, or street address**, extract **that** geography (and any city/state/dateline already implied)—**not** the hearing or camp **title** as a **`place`**.\n\n**Institutions and organizations** (special case):\n- If an organization is named **without** a specific site (headquarters, campus, building, address), **omit** it as a location (e.g. \"The ACLU protested\" — not a mappable place).\n- **Agencies** (city/county/state departments, unions, associations): omit unless the story places an event at their **building or property**.\n- **Small businesses** named in a real-world context are often relevant; **large corporate HQs** are usually irrelevant unless an event occurred there (contrast \"Target Corp. objected\" vs \"employees gathered at Target headquarters\").\n- **High school sports and contests**: schools and contest-related locations mentioned in that context should be **included**.\n- **Scoreboards and game summaries** (e.g. \"St. Louis Park 57 Hopkins 54\", \"Brother Rice 48 Marist 41\"): short tokens refer to **school teams / campuses**, not the homonymous **cities** unless the article clearly means the municipality. For each side, use **`type`: `place`**, set **`components.place.name`** to the **full conventional school name** from your general knowledge when it is a well-known pairing (e.g. **Brother Rice High School**, **St. Louis Park High School**, **Hopkins High School**), and set **`location`** to a **geocodable string** (typically expanded school name plus **city and state** inferable from the story or from standard associations—e.g. Hopkins High School with **Minnetonka, MN** when that is the usual campus locale). **Do not** emit standalone **`city`** objects for those tokens when they are **only** school names in a scoreline.\n- **Scheduled scoreboard lines without final scores** (e.g. \"Hinsdale Adventist at Calvary Christian\", \"Wolcott at Rochelle Zell\", \"Beacon at Northtown\"): treat **both** sides as **school teams / campuses**, not municipalities. Emit **two separate `place` rows**—one for the away team and one for the home team. Expand each to a conventional school name plus **city and state** when you know it (e.g. **Rochelle Zell Jewish High School, Deerfield, IL**). **Never** use **`other`** for these tokens, and **never** put a school name in **`components.city`**. Do **not** omit the away team when only the home team appears after **\"at\"**.\n\n**Regions and ambiguity**:\n- Prefer **specific** geographies. Omit vague \"store, Minneapolis, MN\" or \"rooftop, St. Cloud, MN\" when the same area is already covered by clearer objects.\n- **Named regions** (e.g. \"Southwest Missouri,\" \"the Pacific Northwest,\" \"Northern Arizona\") can be relevant; when you include a sub-region, also include the **containing** city/state/county objects when the text supports them (e.g. \"Northern Arizona\" and \"Arizona\"; \"South Los Angeles\" and \"Los Angeles\").\n\n## Overview\n\nGeographic boundaries, streets, neighborhoods, regions, and **named** businesses and landmarks may appear when they pass the editorial rules above. If multiple distinct relevant places appear in a passage, extract each qualifying one.\n\nClassify and format every **included** location according to the following rules.\n\n## Classification Rules\n\n### Type Classification\n\nClassify each location by the type of geography it represents. Valid types are:\n\n- **place**: A **named** physical site people could find on a map—a building, campus, business, landmark, park, stadium, **named bridge**, etc. **Not** an **event title, hearing name, or activity label** by itself (e.g. a string ending in **Hearing**, **Markup**, **Session**, or generic **training camp** when it describes the **event or phase**, not a venue—see **Exclude → Events, proceedings…**). For example: \"Target Headquarters,\" \"Roseville Mall,\" \"White House,\" or **named bridges and crossings as landmarks** (e.g. \"Stone Arch Bridge,\" \"Mackinac Bridge\"). Might contain a city or other geographic boundary information but does not contain an address. Natural places, such as lakes, rivers and mountains should be considered **natural** types, not **place**. **Bridges:** treat a **named bridge** as **place** when it is a venue or landmark; use **span** only when the article describes a **segment of roadway** between two explicit endpoints (see **span**).\n- **address**: A street address, which must include a house number. This might include block numbers, such as \"500 block of Portland Ave.\" If a place also includes an address, extract only the address and classify it as an \"address.\" Streets or roads without some kind of house number are not addresses.\n- **intersection_road**: An intersection of two non-highway roads, such as Main St. and 2nd St. Even if the story does not describe an intersection in a single string, you may infer it using other information in the article.\n- **intersection_highway**: An intersection where one or both components is an interstate or highway, such as \"I-94 and Selby Ave.\" or \"Hwy. 20 and Hwy. 36\"\n- **street_road**: A single street, road or highway without other geographic information or context, such as an address. For example: \"41st St. N.,\" \"Hennepin Ave.\" or \"I-35\".\n- **span**: A span of road between two points. For example: \"I-35 between Pine City and Hinckley\" or \"Lake Street from Nicollet Avenue S. to 28th Avenue S.\". A span requires both a road and two reference points marking the beginning and end. Just a road, or a road with only one reference point, should use other types as appropriate. **Do not** use **span** for a **named bridge** as a landmark unless the text explicitly frames a **stretch of road on the bridge** between two endpoints; otherwise use **place**.\n- **neighborhood**: Explicit mentions of neighborhood names. Do not include the word \"neighborhood\" or any other descriptor in the output. Only the name. So \"North Loop\" not \"North Loop neighborhood\".\n- **region_city**: A description of an area within a city that is not a named place or neighborhood, such as \"South Minneapolis,\" or the \"Chicago lakefront\". It may also refer to named mass-transit lines, such as \"The Green Line\" light rail in Minneapolis. In all of these cases, also extract the city as a separate object. This can also apply to counties, such as \"western Hennepin County, MN\"\n- **city**: The name of a city\n- **county**: The name of a county in a state\n- **region_state**: The name of a region or a general area being described within a state, such as Northern Wisconsin. In these cases, also extract the state as a separate object. Places that reference large cities and their surrounding areas, like \"The Chicago Area\" or \"the East Bay\" are region_states.\n- **state**: A state\n- **region_national**: The name of a region or a general area being described within the United States, such as the South.\n- **country**: A country\n- **political_district**: A **numbered or ordinally identified** political or administrative boundary used as geography in the story—**U.S. congressional districts**, state house or senate districts, **city wards** or council districts, voting **precincts** when identified by number, and similar. Use this type when the story is about **that district as a jurisdiction** (elections, representation, redistricting, who represents whom), not when a district name is only incidental color. **Do not** use it for broad colloquial regions (\"the South\"), entire **counties** (use **county**), generic **neighborhoods** (use **neighborhood**), or **region_city** blobs (\"south side of Chicago\" without a formal district number). When in doubt between **political_district** and **region_city**, prefer **political_district** only if the text clearly references a **formal district** with a **stable number or ordinal** (e.g. \"8th Congressional District,\" \"Ward 15,\" \"Senate District 42\").\n- **natural**: A specific natural feature, such as a river, lake or mountain range. These are generally specific and named features. General descriptions of natural regions, like \"the California coast\" should be considered regions.\n- **other**: Anything that doesn't fit into the categories above\n\n## Formatting Rules\n\n- Return geocodable address strings in all cases where doing so is possible. For example, if a city is mentioned, like \"Minnetonka\" you should return \"Minnetonka, MN\" if it is clear from the story that Minnetonka, MN is the city being referenced. The same logic should be applied to places, addresses, intersections, streets, and other geographies. You may use the context of the story to fill out information that might not specifically be mentioned. States and countries can be presented on their own: \"Minnesota\" and not \"Minnesota, MN\" for example.\n\n- Geocodable address strings for neighborhoods and regions should include their city and state where possible. For example \"Longfellow, Minneapolis, MN\"\n\n- Block numbers should be returned as addresses. For example, \"200 block of Smith St.\" should be returned as \"200 Smith St., Minneapolis, MN\"\n\n- If a range of street numbers is offered in a single string, such as 7603–7619 N. Main St., include only the first number — in this case, 7603 N. Main St.\n\n- Natural places should generally return only the name of the place and the state in which they are attributed, if possible. For example \"Chicago River, IL\"\n\n- Non-geocodable details (e.g., \"eastbound lanes\" or vague references like \"metro\" without a clear definition) should be omitted unless they are necessary for meaningful distinction.\n\n- If a story describes the location of an incident in imprecise terms, such as happening \"near\" a town, but a precise place/landmark, intersection or location is not given, return only the name of the town. For instance \"Highway 61 near Grand Marais\" should just return \"Grand Marais, MN\"\n\n- If a story includes a list of locations, like \"Freeborn, Faribault, Blue Earth, Brown, Waseca, Nicollet, Le Sueur, Rock and Sibley counties all received snow,\" return each item in the list as a separate location (for instance, \"Freeborn County, MN\", \"Faribault County, MN\", etc.) **only when each is editorially relevant** under the rules above.\n\n- Identifiable places and landmarks should be included with as much geographic information as can be inferred from the story. For instance, if a story mentions \"Memorial Hospital,\" and later the context makes it clear that the hospital in question is located in \"Minneapolis,\" return \"Memorial Hospital, Minneapolis, MN\". This also applies to places that are not proper nouns. A reference to something like \"Monticello nuclear power plant\" should be returned as \"Nuclear power plant, Monticello, MN.\"\n\n- Sometimes a story might use a shorthand name to refer to a location on first reference. For example \"Park\" referring to \"St. Louis Park High School\" or \"Minnetonka\" referring to \"Minnetonka High School\". If the context of the story indicates that the shorthand refers to an entity of which you are aware or can be inferred by the text, return the complete name of that entity as a place. Be especially aware of this if the location is a school. For example, return \"Crete-Monee High School\" not just \"Crete-Monee\" if that can be inferred.\n\n- For street_road types, attempt first to return them with a reference city and state if such information can be inferred from the text: for example \"Interstate 55, Springfield, IL\". If a city cannot be inferred, include only a state if possible, such as \"Interstate 35, IA\". If no state can be inferred, perhaps because the story is referencing a road that crosses state boundaries, include only the name of the road: \"Interstate 70\".\n\n- If a street is already listed as part of an intersection or a span, do not include it separately as a street_road.\n\n## Component extraction\n\nYou should also separate each location into components where possible. The types of components you should capture are:\n\n- **full**: The full geocodable string representing the location that you extract. For example, \"Minneapolis, MN\" or \"Longfellow, Minneapolis, MN\"\n- **type**: The type of the location, from the list above.\n- **place**: Only fill this out for named places—businesses, landmarks, **schools**, **bridges** (as landmarks or venues), and similar\n  - **name**: The name of the place, for instance \"Dogwood Coffee,\" \"Hopkins High School,\" or \"Stone Arch Bridge\"\n  - **natural**: Return True if the place represents a natural location that is unlikely to have a street address, such as North Cascades National Park, Island Lake, or the Mississippi River.\n  - **addressable**: Return True if the place is likely to have a findable street address, such as a business, building, school or landmark. **Named bridges and similar named crossings / transport landmarks** (e.g. Marshall Avenue Bridge, Stone Arch Bridge) should be **`addressable: true`**: they geocode as distinct POIs even when the story gives no house-number line—do **not** set False only because there is no mailing-style address. Pay special attention to proper nouns, which often indicate addressable locations. Return False in all other cases.\n- **street_road**: Only fill this out for street_road types, where a street or highway is named without a specific address.\n  - **name**: The name of the street\n  - **boundary**: A geocodable string representing the most specific neighborhood, city, county or state boundary that contains the segment of street or road in question, inferred by the context of the article.\n- **span**: Only fill this out for span types, describing a section of road from one place to another. For example, \"Hennepin Ave. from W. 26th St. to W. 28th St.\n  - **start**: The starting point of the span. This is an object containing a \"type\" and \"location\" attribute.\n    - **type**: Either city or intersection. City would be used in cases like \"I-35 from Pine City to Duluth\".\n    - **location**: The intersection or city, formatted as a geocodable string. For example \"Hennepin Ave. and W. 26th St., Minneapolis, MN.\" or \"Pine City, MN\"\n  - **end**: The ending point of the span. Formatted the same as \"start\".\n    - **type**: Either city or intersection.\n    - **location**: The intersection or city, formatted as a geocodable string.\n- **address**: The street address, if applicable. For example \"100 Fake St.\"\n- **neighborhood**: The name of the neighborhood, if applicable. For example \"Upper West Side\"\n- **city**: The name of the city, if applicable. For example \"Milwaukee\"\n- **county**: The name of the county, if applicable. For example \"Boone County\"\n- **state**: The name of the state, if applicable.\n  - **name**: The full name of the state. For example \"California\"\n  - **abbr**: The postal abbreviation for the state. For example \"CA\"\n- **country**: The name of the country, if applicable\n  - **name**: The full name of the country. For example \"United States\"\n  - **abbr**: The ISO 3166-1 country code for the country. For example \"US\"\n- **district**: Only for **political_district** locations. Capture the **formal** identity so downstream systems can tell **District 7** from **District 8**.\n  - **kind**: One of: `ward`, `us_house`, `state_senate`, `state_house`, `city_council`, `precinct`, `other`.\n  - **number**: The district or ward **number** as in the story (digits preferred), e.g. `\"8\"`, `\"15\"`, `\"4-2\"` for split wards. If the story only uses ordinals (\"Eighth Congressional District\"), put digits in **number** when you can infer them; otherwise set **ordinal** to the spoken form and still set **number** if inferable.\n  - **ordinal**: Optional spoken ordinal if useful (e.g. `\"Eighth\"`).\n  - **scope**: One of: `federal`, `state`, `county`, `city`—whichever best matches the district's jurisdiction.\n\nDo not infer additional information about the locations beyond what is instructed in your formatting rules. The exception of this is country, which you should always include if you can reasonably guess it (most of the time this will be US).\n\nReturn empty objects or strings in cases where a component does not apply to the geography in question.\n\n## Editorial role (nature)\n\nFor **each** location object, set exactly one primary **`nature`** value describing how this place functions in the story:\n\n- **primary** — Where the main news event (or events) happens: crime scene, construction site, weather-affected area, game venue, key meeting place, etc.\n- **secondary** — A consequential but supporting location (e.g. hospital after a crash, secondary scene in a developing story).\n- **subject** — The place is the focus of coverage: restaurant review, profile of a venue, or an item in a list (e.g. “10 best parks in San Francisco”).\n- **context** — Referenced for background, history, or non-event context without being the main scene.\n- **person** — Tied to a person: where they were quoted, hometown, identifying employer campus, etc.\n- **unknown** — Use only when none of the above clearly applies.\n\nOptionally include **`nature_secondary_tags`**: an array of zero or more **additional** labels drawn from the **same** vocabulary when a place clearly plays more than one role (e.g. primary scene plus **`context`**).\n\n`description` remains the human-readable sentence; **`nature`** is the controlled vocabulary for filtering and analytics.\n\n## Mentions in the story (`mentions`)\n\nEvery location object must include a **`mentions`** array. Each element is a JSON object with exactly one key:\n\n- **`text`**: string — verbatim text from the story for that mention (sentence or clause; do not combine unrelated sentences).\n\n**Rules:**\n\n1. Include **every** editorial mention of that same real-world place in the article, even when the wording repeats (e.g. \"Ohio\" in the lede and again near the end → two separate mention objects).\n2. Do **not** use plain strings in the array; always use objects with **`text`**.\n3. Set **`original_text`** to the **first** mention’s `text` (same string as `mentions[0].text`) for backward compatibility.\n\nExample (brace characters shown doubled so they are literal in the prompt template):\n\n```json\n\"mentions\": [\n  {{ \"text\": \"Ohio lawmakers advanced the bill Tuesday.\" }},\n  {{ \"text\": \"Back in Ohio, the governor said he would sign it.\" }}\n],\n\"original_text\": \"Ohio lawmakers advanced the bill Tuesday.\"\n```\n\n## Required Fields\n\nReturn the paragraph from which the location was extracted and return it as \"original_text\" (must match `mentions[0].text` when `mentions` is present). Ensure these are copied verbatim from the story.\n\nReturn a brief description of the nature of the location and its importance in the story under a \"description\" attribute.\n\nInclude **`nature`** (string, one of the values above) and optionally **`nature_secondary_tags`** (array of strings).\n\nThe description should:\n\n1. **Be concise and clear**\n2. **Explain why this geography is relevant** to the overall narrative\n3. **Sound natural and journalistic**\n4. **Be brief** (1-2 sentences maximum)\n\nGenerally, write this as though you are describing the events of the story for residents of the area in question. Do not make reference to the broader story. Only describe the events, localized for the audience of the geography in question.\n\n## Geocode hints (`geocode_hints`)\n\nFor **every** location object, include a string field **`geocode_hints`**.\n\nPurpose: give downstream geocoding agents **short, actionable prose** from the story that is **not already obvious** from `location`, `components`, or `original_text` alone—material that helps **disambiguate** duplicate names (which branch, which corridor), narrow **vague** geography (“north industrial pocket east of the river”), relate this mention to **other sites or zones** elsewhere in the article, or capture framing that pins the intended real-world site.\n\nGuidelines:\n\n1. **Be concise** — typically one or two sentences, or a few comma-separated clauses; prefer staying under ~400 characters.\n2. **Add information**, don’t copy the verbatim quote; pull **glue** from other sentences when it helps the geocoder choose the right feature.\n3. Use **`\"\"`** (empty string) when nothing beyond `original_text` and structured fields is needed.\n\nIllustrative examples (your output still follows the JSON schema):\n\n- `\"Story identifies this as the East Lake St. café location; mayor spoke outside after the rally, not the roasting warehouse mentioned earlier.\"`\n- `\"Industrial pocket east of the river where overnight truck queues were described two paragraphs above.\"`\n- `\"County fairgrounds hosting the livestock auction the same weekend as the storm damage.\"`\n\n## Street-level: public named place vs non-public site (`address_place_kind`)\n\nFor each location whose **`type`** is one of **address**, **address_intersection** (if you use that label), **intersection_road**, **intersection_highway**, **street_road**, or **span**, add a top-level string field **`address_place_kind`** with exactly one of:\n\n- **`public_named`** — A named business, landmark, civic building, school, hospital, retail site, or other **identifiable public or semi-public** place the story maps to real-world geography (even when the string looks like an address)—somewhere a member of the public could realistically **enter** as a customer, patron, patient, student, or guest.\n- **`private_residence`** — The JSON value name is legacy; **do not read it as “homes only.”** Use it whenever the geography is **not** a named public venue the public would walk into in that role. **Include** private **homes, apartments, residential lots**, and **anonymous residential blocks** (including generic “N00 block of …” when it reads as housing). **Also include** **road or highway intersections** (or similar corners) when the story cites them as the scene of a **crime, crash, or other incident** but **no** named store, office, or landmark applies; **PO boxes** and other **mail-only** addresses; **generic parking lots, stretches of pavement, or any site that is not a building** (or named campus) **a person could enter as a member of the public**—customer, patron, patient, etc. Prefer **`public_named`** only when the text clearly identifies a **specific** business, institution, or landmark at that location.\n- **`unknown`** — You cannot tell from the article; prefer this over guessing.\n\nBase the judgment on **`original_text`**, **`description`**, and the **full story context**, not only `components`.\n\nFor **all other types** (city, neighborhood, `place`, natural, etc.), **omit** `address_place_kind` entirely.\n\n## Output Format\n\n**IMPORTANT**: Return ONLY valid JSON. Do not include any explanatory text before or after the JSON.\n\n## Text to Analyze\n\n{text}\n",
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
  const latestData = nodeOutput || null

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
