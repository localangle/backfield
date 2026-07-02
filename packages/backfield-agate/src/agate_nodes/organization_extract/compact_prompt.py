"""Compact OrganizationExtract prompt instructions appended after extract.md."""

from __future__ import annotations

from agate_nodes.organization_extract.compact_expand import ORG_COMPACT_LEGEND

COMPACT_OUTPUT_INSTRUCTIONS = """\
Return ONLY compact JSON with this shape:
{"organizations": [[name, type_code, role_in_story, nature_code, mentions, extras?], ...]}

IMPORTANT: Return each organization as a JSON ARRAY using the positional schema below.
Ignore any earlier per-key object description in this prompt; emit arrays, not objects.

Rules for compact output:
- Apply all editorial inclusion, exclusion, typing, and formatting rules above.
- Each organization is ONE JSON array with fields in this order:
  0. name — required string; institution or group name only (never an individual person's name).
     In prep scorelines, never a bare token—expand to full school/team name per rules above.
  1. type_code — short type code (see legend); use "oth" for other
  2. role_in_story — brief phrase
  3. nature_code — short nature code (see legend)
  4. mentions — array of [text, quote] pairs where quote is 0 or 1; prefer full sentences or
     paragraphs containing the organization (not the name alone)
  5. extras — optional object; omit entirely when empty (see legend)
- Do NOT emit nature_secondary_tags or organization_boundary in the core array.
- Put organization_boundary in extras.b only for borderline cousin mentions.
- Put nature_secondary_tags in extras.st only when non-empty.
- If no organizations qualify, return {"organizations": []}.

""" + ORG_COMPACT_LEGEND
