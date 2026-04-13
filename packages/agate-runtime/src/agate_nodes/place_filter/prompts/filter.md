# Location Filtering Service

You will be given the text of a news article along with a JSON object containing locations that have been extracted from it. Your job is to classify whether the location is relevant based on the following criteria.

## Text to Analyze:
{text}

## Locations to Filter:
{locations}

## Relevant Locations

Relevant locations are literal, physical locations that are relevant to the events of the story. Examples include: places where key news events took place, where sources or characters are from, places described for detail or scene-setting, places mentioned for context and datelines at the beginnings of stories that indicate a reporter travelled there.

Other cases where locations should be marked as relevant include:

- **Areas represented by lawmakers** should also always be considered relevant. For instance, in the case of Joe Smith, R-Maple Grove, the location "Maple Grove, MN" is always relevant.
- **Places that are affected by policy issues, decisions or the events** described within a story, particularly if it is a place that residents of a town or neighborhood might commonly visit, such as a performing arts venue, park, sports venue, etc.
- **Places that provide biographical context** about people in a story, such as where they live, work, grew up or went to school.

## Irrelevant Locations

Irrelevant locations are locations that are mentioned in the story but are not relevant to the events or context of the story itself. Categories of irrelevant locations include, but are not limited to:

- **Metonyms**: For example, "Washington" when it is used as a reference to the U.S. government, "City Hall" when it is used as a reference to city government, or a city name like "Chicago" when it is used as a stand-in for a professional or college sports team, like the Chicago Bears.
- **Synecdoche**: Places that represent a larger entity or a subset (e.g., "Hollywood" for the U.S. film industry, "Silicon Valley" for the tech industry).
- **Metaphor**: Places used to draw comparisons or symbolic meanings (e.g., "Fort Knox" to represent something highly secure or valuable).
- **Idiomatic expressions**: Common phrases or idioms where the place isn't meant literally (e.g., "Main Street" symbolizing everyday people or small businesses).
- **Historical or cultural references**: Places mentioned in a way that invokes historical or cultural connotations rather than their current geographical reality (e.g., "Rome wasn't built in a day").
- **Colloquialisms and slang**: Locations used in informal expressions or slang that have non-literal meanings (e.g., "The Big Apple" for New York City in a cultural sense rather than just the geographic city).
- **Allegory or symbolism**: Places used to convey a broader theme or idea, like "Eden" representing paradise, not a literal location.
- **Hyperbole**: Exaggerated references to places for emphasis (e.g., "a trip to Timbuktu" to indicate somewhere very remote, not the actual city in Mali).
- **Clichés**: Overused phrases involving places that don't carry their literal meaning (e.g., "all roads lead to Rome" as a cliché for many paths leading to the same result).
- **Generic locations**: References to unnamed and generic places that could possibly refer to more than one location, such as "Bank, Minneapolis, MN" or "Gas station, Wadena, MN"
- **Duplicate locations**: Each location should only appear in the output once.
- **Countries and continents**: Mentions of countries or continents, including the U.S. or North America, are generally irrelevant. They are too broad to be useful.
- **Ambiguous chains**: If it is likely that the place has multiple locations, but the story does not contain enough information to identify a specific location, mark it as irrelevant. For example "Target, Minneapolis, MN"

## Institutions

The names of businesses, organizations and institutions are a special case. They may be relevant or irrelevant depending on their context.

Generally, if an institution is mentioned without direct geographic context, it should be considered irrelevant. For example, "The ACLU protested the ruling" or "Joe Smith, the president of the ACLU" refers to the ACLU as an institution, not a physical location. These should be marked irrelevant. "The protest took place at ACLU headquarters" references a specific place and therefore would be relevant.

City, county and state agencies, such as the Minnesota Department of Education or St. Paul Public Works, should generally not be marked as relevant unless key news events are noted to have taken place at their headquarters, buildings or properties. The same is true of membership organizations like unions and professional associations.

The locations of small businesses that are referenced are typically relevant. The headquarters of large companies are generally not, unless an event took place there. For example, in a case like "Target Corp. objected to the policy," Target should be listed as irrelevant. In a case like "employees gathered at Target headquarters," it should be considered relevant.

An exception to all of this is high school sports and other contests. High schools and locations that are mentioned in reference to sports or other contests should always be considered relevant.

## Duplicate Locations

Locations that are duplicative should be marked irrelevant. In the case of locations that are mentioned multiple times, mark the most detailed instance as relevant and less detailed instances as irrelevant.

In the case of region types, keep both the region and any state, city, county or other geography it refers to or includes. For example "Northern Arizona" should keep both "Northern Arizona" and "Arizona". The same is true with cities, like "South Los Angeles" and "Los Angeles".

If a street is already listed as part of an intersection or a span, its constituent streets_road objects should be marked as irrelevant. 

## Ambiguous Locations

Locations that refer to generic or ambiguous places, such as "store, Minneapolis, MN" or "rooftop, St. Cloud, MN" should be marked as irrelevant — especially if the city, state and other more specific geographic information described therein are accounted for by another object. City, state and national regions, such as "Southwest Missouri" or "the Pacific Northwest" should be considered relevant. 
