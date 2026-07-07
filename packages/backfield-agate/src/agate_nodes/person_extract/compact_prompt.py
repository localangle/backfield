"""Compact PersonExtract prompt instructions appended after extract.md."""

from __future__ import annotations

from agate_nodes.person_extract.compact_expand import PERSON_COMPACT_LEGEND

COMPACT_OUTPUT_INSTRUCTIONS = """\
Return ONLY compact JSON with this shape:
{"people": [
  [name, title, affiliation, pf, type_code, role_in_story, nature_code, mentions, extras?],
  ...
]}

IMPORTANT: Return each person as a JSON ARRAY using the positional schema below.
Ignore any earlier per-key object description in this prompt; emit arrays, not objects.

Rules for compact output:
- Apply all editorial inclusion, exclusion, typing, and formatting rules above —
  especially **Hard stops**.
- **Field 0 (`name`) is only for personal names.** Never emit role labels
  (`ICE agent`), agencies (`ATF`), boards (`Illinois Gaming Board`), companies or
  funds (`H&R Block`, `Engaged Capital`), schools, laws, media outlets, AI
  products (`Gemini AI`), places (`Buenos Aires`, `O'Hare Airport`), or
  legislatures (`General Assembly`). When unsure, omit the row.
- Each person is ONE JSON array with fields in this order:
  0. name — required string; personal name only (never a role or role-plus-agency phrase)
  1. title — role/position only; "" when none
  2. affiliation — institution name; "" when none
  3. pf — 0 or 1 for public_figure
  4. type_code — short type code (see legend); use "un" when unknown
  5. role_in_story — brief phrase
  6. nature_code — short nature code (see legend)
  7. mentions — array of [text, quote] pairs where quote is 0 or 1
  8. extras — optional object; omit entirely when empty (see legend)
- Do NOT emit sort_key, review fields, or nature_secondary_tags in the core array.
- Put review routing in extras.review only when review_handling is not "none".
- Put nature_secondary_tags in extras.st only when non-empty.
- Put surname_inferred_from_relative in extras.si as 1 only when true.
- If no people qualify, return {"people": []}.

""" + PERSON_COMPACT_LEGEND
