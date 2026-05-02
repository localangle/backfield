Return only JSON: `{"location":"<one line>"}`.

Polish this **candidate** display line (US/Canada geography labels). Apply **general** publication rules:

- **Duplicate segments**: If two **adjacent** comma segments are the **same** placename (case-insensitive), keep **one** so the line is **City, ST** (or **Feature, City, ST**) without repeating the city.
- **Municipal / feature order**: When a comma segment is only a **generic placetype** (City, Town, Village, Borough, County) and the **next** segment is the **head toponym** that type modifies, with a valid **subdivision code** after, reorder to the usual **`<Toponym> <Type>, <Code>`** form **only if** those segments clearly name the **same** jurisdiction (do not merge different places such as a neighborhood vs its parent city).
- **Subdivision codes**: Any comma segment that is exactly **two letters** and is a US state, DC, or Canadian province/territory code must be **uppercase**.
- **Small words**: Lowercase joiners (**of, and, or, nor, for, so, yet, the, a, an, at, by, in, on, to, via, as**) inside a segment except the **first word** of that segment; keep a leading **The** when it is part of the official placename, not an article in the middle of a title.
- **Patronymic apostrophe**: After `'` in a personal-style placename token, capitalize the next letter; do not alter English contractions (**n't**, **'s**, **'re**, **'ve**, **'ll**, **'m**).

Do not invent geography; keep comma structure unless reorder rule above clearly applies.

Candidate:
{candidate}
