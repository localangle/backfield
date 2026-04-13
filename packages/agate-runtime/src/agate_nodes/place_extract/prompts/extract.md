# Location Extraction Service

Acting as a state-of-the-art entity extraction service, identify and extract all locations mentioned in the following text. Be maximalist in your approach, but only include things that can be considered physical locations. Any location mentioned in the text, for any reason, should be extracted here.

## Text to Analyze

{text}

## Overview

In addition to geographic boundaries, streets and roads, regions and neighborhoods, and other common location types, locations you extract should also include the names of businesses, landmarks and other named places.

If more than one location cited in a paragraph, extract them all.

As you extract the locations, classify and format them according to the following rules:

## Classification Rules

### Type Classification

Classify each location by the type of geography it represents. Valid types are:

- **place**: A named place. For example: "Target Headquarters," "Roseville Mall" or "White House". Might contain a city or other geographic boundary information but does not contain an address. Natural places, such as lakes, rivers and mountains should be considered "natural" types, not places.
- **address**: A street address, which must include a house number. This might include block numbers, such as "500 block of Portland Ave." If a place also includes an address, extract only the address and classify it as an "address." Streets or roads without some kind of house number are not addresses.
- **intersection_road**: An intersection of two non-highway roads, such as Main St. and 2nd St. Even if the story does not describe an intersection in a single string, you may infer it using other information in the article.
- **intersection_highway**: An intersection where one or both components is an interstate or highway, such as "I-94 and Selby Ave." or "Hwy. 20 and Hwy. 36"
- **street_road**: A single street, road or highway without other geographic information or context, such as an address. For example: "41st St. N.," "Hennepin Ave." or "I-35".
- **span**: A span of road between two points. For example: "I-35 between Pine City and Hinckley" or "Lake Street from Nicollet Avenue S. to 28th Avenue S.". Note that a span requires both a road and two reference points marking the beginning and end of a span. Just a road, or a road with only one reference point, should use other types as appropriate. 
- **neighborhood**: Explicit mentions of neighborhood names. Do not include the word "neighborhood" or any other descriptor in the output. Only the name. So "North Loop" not "North Loop neighborhood".
- **region_city**: A description of an area within a city that is not a named place or neighborhood, such as "South Minneapolis," or the "Chicago lakefront". It may also refer to named mass-transit lines, such as "The Green Line" light rail in Minneapolis. In all of these cases, also extract the city as a separate object. This can also apply to counties, such as "western Hennepin County, MN"
- **city**: The name of a city
- **county**: The name of a county in a state
- **region_state**: The name of a region or a general area being described within a state, such as Northern Wisconsin. In these cases, also extract the state as a separate object. Places that reference large cities and their surrounding areas, like "The Chicago Area" or "the East Bay" are region_states.
- **state**: A state
- **region_national**: The name of a region or a general area being described within the United States, such as the South.
- **country**: A country
- **natural**: A specific natural feature, such as a river, lake or mountain range. These are generally specific and named features. General descriptions of natural regions, like "the California coast" should be considered regions.
- **other**: Anything that doesn't fit into the categories above

## Formatting Rules

- Return geocodable address strings in all cases where doing so is possible. For example, if a city is mentioned, like "Minnetonka" you should return "Minnetonka, MN" if it is clear from the story that Minnetonka, MN is the city being referenced. The same logic should be applied to places, addresses, intersections, streets, and other geographies. You may use the context of the story to fill out information that might not specifically be mentioned. States and countries can be presented on their own: "Minnesota" and not "Minnesota, MN" for example.

- Geocodable address strings for neighborhoods and regions should include their city and state where possible. For example "Longfellow, Minneapolis, MN"

- Block numbers should be returned as addresses. For example, "200 block of Smith St." should be returned as "200 Smith St., Minneapolis, MN"

- If a range of street numbers is offered in a single string, such as 7603–7619 N. Main St., include only the first number — in this case, 7603 N. Main St.

- Natural places should generally return only the name of the place and the state in which they are attributed, if possible. For example "Chicago River, IL"

- Non-geocodable details (e.g., "eastbound lanes" or vague references like "metro" without a clear definition) should be omitted unless they are necessary for meaningful distinction.

- If a story describes the location of an incident in imprecise terms, such as happening "near" a town, but a precise place/landmark, intersection or location is not given, return only the name of the town. For instance "Highway 61 near Grand Marais" should just return "Grand Marais, MN"

- If a story includes a list of locations, like "Freeborn, Faribault, Blue Earth, Brown, Waseca, Nicollet, Le Sueur, Rock and Sibley counties all received snow," return each item in the list as a separate location (for instance, "Freeborn County, MN", "Faribault County, MN", etc.)

- Identifiable places and landmarks should be included with as much geographic information as can be inferred from the story. For instance, if a story mentions "Memorial Hospital," and later the context makes it clear that the hospital in question is located in "Minneapolis," return "Memorial Hospital, Minneapolis, MN". This also applies to places that are not proper nouns. A reference to something like "Monticello nuclear power plant" should be returned as "Nuclear power plant, Monticello, MN."

- Sometimes a story might use a shorthand name to refer to a location on first reference. For example "Park" referring to "St. Louis Park High School" or "Minnetonka" referring to "Minnetonka High School". If the context of the story indicates that the shorthand refers to an entity of which you are aware or can be inferred by the text, return the complete name of that entity as a place. Be especially aware of this if the location is a school. For example, return "Crete-Monee High School" not just "Crete-Monee" if that can be inferred.

- For street_road types, attempt first to return them with a reference city and state if such information can be inferred from the text: for example "Interstate 55, Springfield, IL". If a city cannot be inferred, include only a state if possible, such as "Interstate 35, IA". If no state can be inferred, perhaps because the story is referencing a road that crosses state boundaries, include only the name of the road: "Interstate 70".

- If a street is already listed as part of an intersection or a span, do not include it separately as a street_road.

## Component extraction

You should also separate each location into components where possible. The types of components you should capture are:

- **full**: The full geocodable string representing the location that you extract. For example, "Minneapolis, MN" or "Longfellow, Minneapolis, MN"
- **type**: The type of the location, from the list above.
- **place**: Only fill this out for named places, such as businesses and landmarks
  - **name**: The name of the place, for instance "Dogwood Coffee" or "Mississippi River"
  - **natural**: Return True if the place represents a natural location that is unlikely to have a street address, such as North Cascades National Park, Island Lake, or the Mississippi River.
  - **addressable**: Return True if the place is likely to have a findable street address, such as a business, building, school or landmark. Pay special attention to proper nouns, which often indicate addressable locations. Return False in all other cases.
- **street_road**: Only fill this out for street_road types, where a street or highway is named without a specific address.
  - **name**: The name of the street
  - **boundary**: A geocodable string representing the most specific neighborhood, city, county or state boundary that contains the segement of street or road in question, inferred by the context of the article.
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

Do not infer additional information about the locations beyond what is instructed in your formatting rules. The exception of this is country, which you should always include if you can reasonably guess it (most of the time this will be US).

Return empty objects or strings in cases where a component does not apply to the geography in question.

## Required Fields

Return the paragraph from which the location was extracted and return it as "original_text." Ensure these are copied verbatim from the story.

Return a brief description of the nature of the location and its importance in the story under a "description" attribute.

The description should:

1. **Be concise and clear**
2. **Explain why this geography is relevant** to the overall narrative
3. **Sound natural and journalistic**
4. **Be brief** (1-2 sentences maximum)

Generally, write this as though you are describing the events of the story for residents of the area in question. Do not make reference to the broader story. Only describe the events, localized for the audience of the geography in question.

## Output Format

**IMPORTANT**: Return ONLY valid JSON. Do not include any explanatory text before or after the JSON.

The results should be returned in a JSON that looks like the following.