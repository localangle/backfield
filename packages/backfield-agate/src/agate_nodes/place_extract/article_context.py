"""Minimal article context for PlaceExtract compact component expansion."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from agate_nodes.place_extract.location_utils import (
    US_STATE_ABBR_BY_NAME,
    US_STATES,
    location_has_state_suffix,
    parse_city_state_pairs,
    split_location_parts,
    title_location,
)


@dataclass
class ArticleContext:
    text: str = ""
    anchor_city: str = ""
    anchor_state_name: str = ""
    anchor_state_abbr: str = ""
    city_state_pairs: dict[str, str] = field(default_factory=dict)

    def state_for_city(self, city: str) -> str:
        if not city:
            return self.anchor_state_abbr
        return self.city_state_pairs.get(city.lower(), self.anchor_state_abbr)


def _city_matches_in_text(text: str) -> list[str]:
    matches = [city for city, _abbr in parse_city_state_pairs(text)]
    matches.extend(
        title_location(match.strip())
        for match in re.findall(
            r"\bin\s+([A-Z][A-Za-z'.-]+\s+[A-Z][A-Za-z'.-]+)\b",
            text,
            flags=re.IGNORECASE,
        )
    )
    return matches


def _count_city_mentions(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for city, _abbr in parse_city_state_pairs(text):
        counts[city.lower()] = counts.get(city.lower(), 0) + 1
    for city in _city_matches_in_text(text):
        if city.lower() in US_STATE_ABBR_BY_NAME:
            continue
        counts[city.lower()] = counts.get(city.lower(), 0) + 1
    return counts


def extract_article_context(text: str) -> ArticleContext:
    """Infer dateline anchor city/state and city→state pairs from article text."""
    state_counts: dict[str, int] = {}
    city_state_counts: dict[tuple[str, str], int] = {}

    for city, abbr in parse_city_state_pairs(text):
        city_state_counts[(city.lower(), abbr)] = city_state_counts.get((city.lower(), abbr), 0) + 1
        state_counts[abbr] = state_counts.get(abbr, 0) + 1

    for abbr, name in US_STATES.items():
        if re.search(rf"\b{re.escape(name)}\b", text, flags=re.IGNORECASE):
            state_counts[abbr] = state_counts.get(abbr, 0) + 1

    anchor_city = ""
    dateline = re.match(r"^([A-Z][A-Za-z .'-]+)\s*[—–-]", text.strip())
    if dateline:
        anchor_city = title_location(dateline.group(1).strip())

    city_state_pairs: dict[str, str] = {}
    city_totals: dict[str, tuple[str, int]] = {}
    for (city_key, abbr), count in city_state_counts.items():
        city_state_pairs[city_key] = abbr
        previous = city_totals.get(city_key)
        if not previous or count > previous[1]:
            city_totals[city_key] = (title_location(city_key), count)

    if not anchor_city and city_totals:
        anchor_city = max(city_totals.values(), key=lambda item: item[1])[0]

    if not anchor_city:
        body = text.split("\n\n", 1)[1] if "\n\n" in text else text
        body_mentions = _count_city_mentions(body)
        paired = [
            (city_key, count)
            for city_key, count in body_mentions.items()
            if city_key in city_state_pairs
        ]
        if paired:
            anchor_city = title_location(max(paired, key=lambda item: item[1])[0])
        elif body_mentions:
            ranked = sorted(body_mentions.items(), key=lambda item: item[1], reverse=True)
            for city_key, _count in ranked:
                if city_key in city_state_pairs:
                    anchor_city = title_location(city_key)
                    break

    anchor_state_abbr = ""
    if anchor_city:
        anchor_state_abbr = city_state_pairs.get(anchor_city.lower(), "")
    if not anchor_state_abbr and state_counts:
        anchor_state_abbr = max(state_counts, key=state_counts.get)
    if anchor_city and anchor_state_abbr:
        city_state_pairs.setdefault(anchor_city.lower(), anchor_state_abbr)

    return ArticleContext(
        text=text,
        anchor_city=anchor_city,
        anchor_state_name=US_STATES.get(anchor_state_abbr, ""),
        anchor_state_abbr=anchor_state_abbr,
        city_state_pairs=city_state_pairs,
    )


def state_components(location: str, context: ArticleContext) -> dict[str, str]:
    """Resolve state name/abbr from a location string or article context."""
    parts = split_location_parts(location)
    if location_has_state_suffix(parts):
        abbr = parts[-1].upper()
        return {"name": US_STATES.get(abbr, ""), "abbr": abbr}
    if context.anchor_state_abbr:
        return {
            "name": context.anchor_state_name,
            "abbr": context.anchor_state_abbr,
        }
    return {"name": "", "abbr": ""}

