Return only JSON: `{"location":"<one line>"}`.

Polish this **candidate** display line (US/Canada geography labels). Apply **general** publication rules. Use **story excerpt** and **geocode hints** only to **disambiguate** the candidate (insert a missing neighborhood, fix order); do not invent geography.

**Extract row type:** `{location_type}`

- **Admin types (`city`, `town`, `village`, `county`, `state`, `region_state`, `region_national`, `country`, `political_district`):** Return the **candidate unchanged** except for casing, deduplication, and segment cleanup below. **Never** insert a neighborhood, district, or other child geography from the story—even when the excerpt mentions one (e.g. do not turn `Chicago, IL` into `South Shore, Chicago, IL`).
- **Neighborhood disambiguation** applies only when `type` is **`place`**, **`point`**, **`address`**, **`intersection_road`**, **`intersection_highway`**, **`street_road`**, **`region_city`**, or **`neighborhood`**, and only as described below.

- **Duplicate segments**: If two **adjacent** comma segments are the **same** placename (case-insensitive), keep **one** so the line is **City, ST** (or **Feature, City, ST**) without repeating the city.
- **Municipal / feature order**: When a comma segment is only a **generic placetype** (City, Town, Village, Borough, County) and the **next** segment is the **head toponym** that type modifies, with a valid **subdivision code** after, reorder to the usual `**<Toponym> <Type>, <Code>`** form **only if** those segments clearly name the **same** jurisdiction (do not merge different places such as a neighborhood vs its parent city).
- **Neighborhood disambiguation** (fine-grained types only; see admin rule above): If the candidate is **Feature, City, ST** where **Feature is not the city name itself** (e.g. a venue or street line), and the story or hints clearly name a **specific neighborhood or district** that identifies **which** instance in that city, insert that **actual placename** between feature and city (**Feature, (real name), City, ST**). **Do not** apply when the candidate is only **City, ST** (municipality row). Only when the name is **explicitly supported** by the excerpt or hints; otherwise leave the candidate unchanged. **Never** emit the literal words **Neighborhood** or **District** as a **standalone** comma segment—they are type labels, not place names. If the candidate already contains a bogus segment like `**, Neighborhood,`** or `**, District,**` (with no real toponym there), remove that segment.
- **Subdivision codes**: Any comma segment that is exactly **two letters** and is a US state, DC, or Canadian province/territory code must be **uppercase**.
- **Article/extract casing**: When the **candidate head** or **story excerpt** already uses intentional capitalization (schools, brands, **en-dash** names like **University of Wisconsin–Madison**, acronyms), **preserve that casing** for the named-place head. Do not downgrade a correctly cased head to generic title case.
- **Small words**: Lowercase joiners (**of, and, or, nor, for, so, yet, the, a, an, at, by, in, on, to, via, as**) inside a segment except the **first word** of that segment; keep a leading **The** when it is part of the official placename, not an article in the middle of a title.
- **Patronymic apostrophe**: After `'` in a personal-style placename token, capitalize the next letter; do not alter English contractions (**n't**, **'s**, **'re**, **'ve**, **'ll**, **'m**).
- **Acronyms**: Preserve **dotted initialisms** with **all letters uppercase** (**U.S.**, **D.C.**, **N.Y.**) **inside** a segment (e.g. **U.S. Senate**). Use **Ph.D.** (not **Ph.d.**). For **&** in short brand-style tokens (**AT&T**), capitalize **both** sides of **&**.
- **Trailing United States (country)**: When the **final** comma segment is the country, use `**US`** only—**no** periods (**not** `**U.S.`**), and **not** `**USA`**. **World macro-regions** (Middle East, Western Europe, etc.) must **not** be suffixed with `**, US`**—leave `**Middle East**` alone.

Story excerpt (may be truncated):
{story_context}

Geocode hints:
{geocode_hints}

Candidate:
{candidate}