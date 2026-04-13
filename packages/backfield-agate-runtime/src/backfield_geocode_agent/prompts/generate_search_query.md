# Search Query Generation

You are tasked with generating a brief, effective web search query to find the physical address of a place mentioned in a news article.

## Objective

Create a search query that will help find the specific address of the place mentioned in the original text context.

## Guidelines

- Keep the query concise (under 10 words when possible)
- Include the place name and location context
- If the location context includes information that might differentiate one location of a business or place from another — describing it as "near" or "by" something or "on" street, for example — include that context in the search query
- Focus on finding the physical address, not general information
- Use terms that are likely to appear on business websites, directories, or news articles
- Avoid overly specific details that might limit results

## Input

**Place Name:** {place_name}
**Location Context:** {location_context}
**Original Text:** {original_text}

## Output

Return ONLY the search query as a plain string, no quotes or formatting.

## Examples

**Input:**
- Place Name: Dogwood Coffee
- Location Context: Minneapolis, MN
- Original Text: The incident occurred at the Dogwood Coffee on East Lake St. in Minneapolis.

**Output:**
Dogwood Coffee East Lake Street Minneapolis address

**Input:**
- Place Name: Central Park
- Location Context: New York, NY
- Original Text: The protest took place at Central Park near the Bethesda Fountain.

**Output:**
Central Park Bethesda Fountain New York address

