"""Compact PlaceExtract prompt instructions appended after extract.md."""

from __future__ import annotations

from agate_nodes.place_extract.compact_codes import COMPACT_CODE_LEGEND

COMPACT_OUTPUT_INSTRUCTIONS = """\
Return ONLY compact JSON with this shape:
{"locations": [["location", "type", "nature", "address_place_kind", "description", "geocode_hints"], ...]}

Rules for compact output:
- Apply all editorial inclusion, exclusion, typing, and formatting rules above —
  especially **Hard stops**.
- **Field 1 (location) is only for literal, mappable geography.** Never emit teams
  (`Chicago Bears`), athletic conferences, classes, or brackets (`Class 3a, IL`,
  `IHSA 4A`, `West Suburban Conference Silver`), events or camp titles
  (`NFL Scouting Combine`), organizations with inferred headquarters, or narrative
  phrases. When unsure, omit the row.
- **Block addresses:** never emit "block of" in `location`. Normalize journalistic
  block references to mailing-style addresses (`6500 block of South Hermitage Avenue`
  → `6500 S Hermitage Ave, Chicago, IL`).
- **Intersections and spans:** use full street-type words and include city/state
  (`Main Street and 2nd Street, Chicago, IL`; `Lake Street from Nicollet Avenue to
  28th Avenue, Minneapolis, MN`).
- **Neighborhoods and regions:** include city/state in `location` when inferable
  (`Longfellow, Minneapolis, MN`); emit parent city/state rows for region types.
- Each location is ONE JSON array with EXACTLY six string fields in this order:
  1. location — full geocodable string per the rules above
  2. type — short type code (see legend below)
  3. nature — short nature code (see legend below)
  4. address_place_kind — short kind code for street-level types; use "" for all other types
  5. description — one brief sentence on the location's role in the story
  6. geocode_hints — concise disambiguation/context for downstream geocoding; use "" when not needed
- Do NOT use full enum names (e.g. intersection_highway) or objects with keys.
- Do NOT include components, mentions, original_text, nature_secondary_tags, or any other fields.
- Output every distinct editorially relevant location from the article.
- If none, return {"locations": []}.
- When a neighborhood already appears inside a location string (e.g. "River North, Chicago, IL"),
  do not also emit a standalone neighborhood row for that same neighborhood.
- When the story is datelined or clearly based in a local anchor city, emit that city as its own
  city row even if it also appears inside longer location strings elsewhere.
- Prefer the same location-string granularity you would use in full mode (e.g. "Ragadan, Chicago, IL"
  rather than "Ragadan, Uptown, Chicago, IL") unless an extra segment is needed to geocode or
  disambiguate.
- Scheduled scoreboard lines without scores ("Team A at Team B") and final score lines ("Team A 55, Team B 53"): emit **both** teams as separate **`pl` / place** rows with expanded school names plus city/state. Never use **`ot` / other** for school tokens, never bare tokens (`Belvidere`, `Smith`) as `location`, and never put a school name in the city component.

""" + COMPACT_CODE_LEGEND
