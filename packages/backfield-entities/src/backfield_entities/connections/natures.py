"""Preferred connection nature catalog (code registry).

See ``docs/architecture/connection-natures.md``. Org custom natures live in the DB;
this module is the global preferred set only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from backfield_entities.entities.location.types import ADDRESS_LIKE_LOCATION_TYPES

TemporalKind = Literal["static", "dynamic"]
EntityEndpoint = Literal["person", "organization", "location"]

# Location granularity (carried from taxonomy v1; extended for new natures).
LOCATED_AT_LOCATION_TYPES: frozenset[str] = frozenset(
    {
        "place",
        "address",
        "address_intersection",
        "intersection_road",
        "intersection_highway",
        "street_road",
    }
)
BASED_IN_LOCATION_TYPES: frozenset[str] = frozenset(
    {
        "place",
        "neighborhood",
        "city",
        "county",
        "region_city",
    }
)
OPERATES_OR_SERVES_LOCATION_TYPES: frozenset[str] = frozenset(
    {
        "neighborhood",
        "city",
        "county",
        "political_district",
        "state",
        "region_state",
        "region_city",
    }
)
FOUNDED_IN_LOCATION_TYPES: frozenset[str] = frozenset(
    {
        "neighborhood",
        "city",
        "county",
        "region_city",
    }
)
LIVES_IN_LOCATION_TYPES: frozenset[str] = frozenset(
    {
        "neighborhood",
        "city",
        "region_city",
    }
)
BORN_IN_LOCATION_TYPES: frozenset[str] = frozenset(
    {
        "neighborhood",
        "city",
        "county",
        "region_city",
    }
)
REPRESENTS_PERSON_LOCATION_TYPES: frozenset[str] = frozenset(
    {
        "political_district",
        "city",
        "county",
        "state",
        "region_state",
        "region_city",
    }
)
HOLDS_OFFICE_IN_LOCATION_TYPES: frozenset[str] = frozenset(
    {
        "political_district",
        "city",
        "county",
        "state",
        "region_state",
        "region_city",
        "neighborhood",
    }
)
OWNS_PROPERTY_IN_LOCATION_TYPES: frozenset[str] = frozenset(
    {
        "place",
        "address",
        "neighborhood",
        "city",
        "county",
        "region_city",
    }
)


@dataclass(frozen=True)
class NatureCrosswalk:
    schema_org: str | None = None
    wikidata: str | None = None
    ftm: str | None = None
    tac_kbp: str | None = None


@dataclass(frozen=True)
class NatureDef:
    """One preferred nature binding for a directed endpoint pair."""

    slug: str
    label: str
    inverse_label: str
    from_type: EntityEndpoint
    to_type: EntityEndpoint
    temporal_kind: TemporalKind
    auto_allowed: bool
    symmetric: bool = False
    aliases: tuple[str, ...] = ()
    location_types: frozenset[str] | None = None
    crosswalk: NatureCrosswalk = NatureCrosswalk()


def _n(
    slug: str,
    *,
    label: str,
    inverse_label: str,
    from_type: EntityEndpoint,
    to_type: EntityEndpoint,
    temporal_kind: TemporalKind,
    auto_allowed: bool,
    symmetric: bool = False,
    aliases: tuple[str, ...] = (),
    location_types: frozenset[str] | None = None,
    crosswalk: NatureCrosswalk | None = None,
) -> NatureDef:
    return NatureDef(
        slug=slug,
        label=label,
        inverse_label=inverse_label,
        from_type=from_type,
        to_type=to_type,
        temporal_kind=temporal_kind,
        auto_allowed=auto_allowed,
        symmetric=symmetric,
        aliases=aliases,
        location_types=location_types,
        crosswalk=crosswalk or NatureCrosswalk(),
    )


PREFERRED_NATURES: tuple[NatureDef, ...] = (
    # Person → Organization
    _n(
        "works_for",
        label="works for",
        inverse_label="employs",
        from_type="person",
        to_type="organization",
        temporal_kind="dynamic",
        auto_allowed=True,
        aliases=("employee_of", "employed_by", "works_at"),
        crosswalk=NatureCrosswalk(
            schema_org="worksFor",
            wikidata="P108",
            ftm="Employment",
            tac_kbp="per:employee_or_member_of",
        ),
    ),
    _n(
        "leads",
        label="leads",
        inverse_label="led by",
        from_type="person",
        to_type="organization",
        temporal_kind="dynamic",
        auto_allowed=True,
        aliases=("heads", "ceo_of", "director_of"),
        crosswalk=NatureCrosswalk(wikidata="P169", tac_kbp="per:top_member_employee_of"),
    ),
    _n(
        "board_member_of",
        label="board member of",
        inverse_label="has board member",
        from_type="person",
        to_type="organization",
        temporal_kind="dynamic",
        auto_allowed=True,
        aliases=("director_of_board",),
        crosswalk=NatureCrosswalk(ftm="Directorship"),
    ),
    _n(
        "member_of",
        label="member of",
        inverse_label="has member",
        from_type="person",
        to_type="organization",
        temporal_kind="dynamic",
        auto_allowed=True,
        crosswalk=NatureCrosswalk(
            schema_org="memberOf",
            wikidata="P463",
            ftm="Membership",
        ),
    ),
    _n(
        "founded",
        label="founded",
        inverse_label="founded by",
        from_type="person",
        to_type="organization",
        temporal_kind="static",
        auto_allowed=True,
        aliases=("founder_of",),
        crosswalk=NatureCrosswalk(
            schema_org="founder",
            wikidata="P112",
            tac_kbp="org:founded_by",
        ),
    ),
    _n(
        "owns",
        label="owns",
        inverse_label="owned by",
        from_type="person",
        to_type="organization",
        temporal_kind="dynamic",
        auto_allowed=True,
        aliases=("owner_of",),
        crosswalk=NatureCrosswalk(ftm="Ownership", wikidata="P127"),
    ),
    _n(
        "studied_at",
        label="studied at",
        inverse_label="alumnus of",
        from_type="person",
        to_type="organization",
        temporal_kind="static",
        auto_allowed=True,
        aliases=("alumni_of", "attended"),
        crosswalk=NatureCrosswalk(
            schema_org="alumniOf",
            wikidata="P69",
            tac_kbp="per:schools_attended",
        ),
    ),
    _n(
        "represents",
        label="represents",
        inverse_label="represented by",
        from_type="person",
        to_type="organization",
        temporal_kind="dynamic",
        auto_allowed=True,
        crosswalk=NatureCrosswalk(ftm="Representation"),
    ),
    _n(
        "candidate_for",
        label="candidate for",
        inverse_label="has candidate",
        from_type="person",
        to_type="organization",
        temporal_kind="dynamic",
        auto_allowed=True,
    ),
    _n(
        "donated_to",
        label="donated to",
        inverse_label="received donation from",
        from_type="person",
        to_type="organization",
        temporal_kind="static",
        auto_allowed=False,
    ),
    _n(
        "plays_for",
        label="plays for",
        inverse_label="has player",
        from_type="person",
        to_type="organization",
        temporal_kind="dynamic",
        auto_allowed=True,
        aliases=("athlete_for",),
        crosswalk=NatureCrosswalk(wikidata="P54"),
    ),
    _n(
        "coaches",
        label="coaches",
        inverse_label="coached by",
        from_type="person",
        to_type="organization",
        temporal_kind="dynamic",
        auto_allowed=True,
        aliases=("coach_of",),
        crosswalk=NatureCrosswalk(wikidata="P286"),
    ),
    _n(
        "sued_by",
        label="sued by",
        inverse_label="sued",
        from_type="person",
        to_type="organization",
        temporal_kind="dynamic",
        auto_allowed=True,
    ),
    # Person → Location
    _n(
        "represents",
        label="represents",
        inverse_label="represented by",
        from_type="person",
        to_type="location",
        temporal_kind="dynamic",
        auto_allowed=True,
        location_types=REPRESENTS_PERSON_LOCATION_TYPES,
    ),
    _n(
        "holds_office_in",
        label="holds office in",
        inverse_label="has officeholder",
        from_type="person",
        to_type="location",
        temporal_kind="dynamic",
        auto_allowed=True,
        aliases=("mayor_of", "governor_of", "officeholder_of"),
        location_types=HOLDS_OFFICE_IN_LOCATION_TYPES,
        crosswalk=NatureCrosswalk(wikidata="P39"),
    ),
    _n(
        "lives_in",
        label="lives in",
        inverse_label="resident",
        from_type="person",
        to_type="location",
        temporal_kind="dynamic",
        auto_allowed=True,
        aliases=("resides_in",),
        location_types=LIVES_IN_LOCATION_TYPES,
        crosswalk=NatureCrosswalk(
            schema_org="homeLocation",
            wikidata="P551",
            tac_kbp="per:cities_of_residence",
        ),
    ),
    _n(
        "born_in",
        label="born in",
        inverse_label="birthplace of",
        from_type="person",
        to_type="location",
        temporal_kind="static",
        auto_allowed=True,
        location_types=BORN_IN_LOCATION_TYPES,
        crosswalk=NatureCrosswalk(
            schema_org="birthPlace",
            wikidata="P19",
            tac_kbp="per:city_of_birth",
        ),
    ),
    _n(
        "died_in",
        label="died in",
        inverse_label="place of death of",
        from_type="person",
        to_type="location",
        temporal_kind="static",
        auto_allowed=True,
        location_types=BORN_IN_LOCATION_TYPES,
        crosswalk=NatureCrosswalk(wikidata="P20", tac_kbp="per:city_of_death"),
    ),
    _n(
        "native_of",
        label="native of",
        inverse_label="hometown of",
        from_type="person",
        to_type="location",
        temporal_kind="static",
        auto_allowed=True,
        aliases=("hometown", "from"),
        location_types=BORN_IN_LOCATION_TYPES,
        crosswalk=NatureCrosswalk(tac_kbp="per:origin"),
    ),
    _n(
        "owns_property_in",
        label="owns property in",
        inverse_label="property owned by",
        from_type="person",
        to_type="location",
        temporal_kind="dynamic",
        auto_allowed=False,
        location_types=OWNS_PROPERTY_IN_LOCATION_TYPES,
        crosswalk=NatureCrosswalk(ftm="Ownership"),
    ),
    # Person → Person
    _n(
        "spouse_of",
        label="spouse of",
        inverse_label="spouse of",
        from_type="person",
        to_type="person",
        temporal_kind="dynamic",
        auto_allowed=True,
        symmetric=True,
        aliases=("married_to",),
        crosswalk=NatureCrosswalk(schema_org="spouse", wikidata="P26", tac_kbp="per:spouse"),
    ),
    _n(
        "parent_of",
        label="parent of",
        inverse_label="child of",
        from_type="person",
        to_type="person",
        temporal_kind="static",
        auto_allowed=True,
        aliases=("child_of",),  # normalize to parent_of via swap at write time later
        crosswalk=NatureCrosswalk(wikidata="P40", tac_kbp="per:children"),
    ),
    _n(
        "sibling_of",
        label="sibling of",
        inverse_label="sibling of",
        from_type="person",
        to_type="person",
        temporal_kind="static",
        auto_allowed=True,
        symmetric=True,
        crosswalk=NatureCrosswalk(wikidata="P3373", tac_kbp="per:siblings"),
    ),
    _n(
        "family_of",
        label="family of",
        inverse_label="family of",
        from_type="person",
        to_type="person",
        temporal_kind="static",
        auto_allowed=True,
        symmetric=True,
        crosswalk=NatureCrosswalk(ftm="Family", tac_kbp="per:other_family"),
    ),
    _n(
        "works_with",
        label="works with",
        inverse_label="works with",
        from_type="person",
        to_type="person",
        temporal_kind="dynamic",
        auto_allowed=True,
        symmetric=True,
        crosswalk=NatureCrosswalk(schema_org="colleague"),
    ),
    _n(
        "reports_to",
        label="reports to",
        inverse_label="manages",
        from_type="person",
        to_type="person",
        temporal_kind="dynamic",
        auto_allowed=True,
    ),
    _n(
        "represents",
        label="represents",
        inverse_label="represented by",
        from_type="person",
        to_type="person",
        temporal_kind="dynamic",
        auto_allowed=True,
        aliases=("represented_by",),
        crosswalk=NatureCrosswalk(ftm="Representation"),
    ),
    _n(
        "succeeded",
        label="succeeded",
        inverse_label="succeeded by",
        from_type="person",
        to_type="person",
        temporal_kind="static",
        auto_allowed=True,
        crosswalk=NatureCrosswalk(wikidata="P1365"),
    ),
    _n(
        "appointed_by",
        label="appointed by",
        inverse_label="appointed",
        from_type="person",
        to_type="person",
        temporal_kind="static",
        auto_allowed=True,
    ),
    _n(
        "partner_of",
        label="partner of",
        inverse_label="partner of",
        from_type="person",
        to_type="person",
        temporal_kind="dynamic",
        auto_allowed=True,
        symmetric=True,
        aliases=("dating", "romantic_partner_of"),
    ),
    _n(
        "coaches",
        label="coaches",
        inverse_label="coached by",
        from_type="person",
        to_type="person",
        temporal_kind="dynamic",
        auto_allowed=True,
        crosswalk=NatureCrosswalk(wikidata="P286"),
    ),
    _n(
        "defeated",
        label="defeated",
        inverse_label="defeated by",
        from_type="person",
        to_type="person",
        temporal_kind="static",
        auto_allowed=True,
    ),
    _n(
        "endorsed",
        label="endorsed",
        inverse_label="endorsed by",
        from_type="person",
        to_type="person",
        temporal_kind="static",
        auto_allowed=True,
    ),
    _n(
        "supports",
        label="supports",
        inverse_label="supported by",
        from_type="person",
        to_type="person",
        temporal_kind="dynamic",
        auto_allowed=True,
    ),
    _n(
        "opposes",
        label="opposes",
        inverse_label="opposed by",
        from_type="person",
        to_type="person",
        temporal_kind="dynamic",
        auto_allowed=True,
    ),
    _n(
        "associate_of",
        label="associate of",
        inverse_label="associate of",
        from_type="person",
        to_type="person",
        temporal_kind="dynamic",
        auto_allowed=False,
        symmetric=True,
        crosswalk=NatureCrosswalk(ftm="Associate"),
    ),
    _n(
        "sued_by",
        label="sued by",
        inverse_label="sued",
        from_type="person",
        to_type="person",
        temporal_kind="dynamic",
        auto_allowed=True,
    ),
    # Organization → Organization
    _n(
        "parent_of",
        label="parent of",
        inverse_label="subsidiary of",
        from_type="organization",
        to_type="organization",
        temporal_kind="dynamic",
        auto_allowed=True,
        aliases=("subsidiary_of",),
        crosswalk=NatureCrosswalk(
            schema_org="subOrganization",
            wikidata="P749",
            tac_kbp="org:subsidiaries",
        ),
    ),
    _n(
        "member_of",
        label="member of",
        inverse_label="has member",
        from_type="organization",
        to_type="organization",
        temporal_kind="dynamic",
        auto_allowed=True,
        crosswalk=NatureCrosswalk(wikidata="P463", tac_kbp="org:member_of"),
    ),
    _n(
        "team_of",
        label="team of",
        inverse_label="fields team",
        from_type="organization",
        to_type="organization",
        temporal_kind="dynamic",
        auto_allowed=True,
    ),
    _n(
        "oversees",
        label="oversees",
        inverse_label="overseen by",
        from_type="organization",
        to_type="organization",
        temporal_kind="dynamic",
        auto_allowed=False,
    ),
    _n(
        "owns",
        label="owns",
        inverse_label="owned by",
        from_type="organization",
        to_type="organization",
        temporal_kind="dynamic",
        auto_allowed=True,
        crosswalk=NatureCrosswalk(ftm="Ownership", wikidata="P127"),
    ),
    _n(
        "acquired_by",
        label="acquired by",
        inverse_label="acquired",
        from_type="organization",
        to_type="organization",
        temporal_kind="static",
        auto_allowed=True,
    ),
    _n(
        "merged_with",
        label="merged with",
        inverse_label="merged with",
        from_type="organization",
        to_type="organization",
        temporal_kind="static",
        auto_allowed=True,
        symmetric=True,
    ),
    _n(
        "partnered_with",
        label="partnered with",
        inverse_label="partnered with",
        from_type="organization",
        to_type="organization",
        temporal_kind="dynamic",
        auto_allowed=True,
        symmetric=True,
    ),
    _n(
        "funded_by",
        label="funded by",
        inverse_label="funds",
        from_type="organization",
        to_type="organization",
        temporal_kind="dynamic",
        auto_allowed=True,
        crosswalk=NatureCrosswalk(schema_org="funder"),
    ),
    _n(
        "donated_to",
        label="donated to",
        inverse_label="received donation from",
        from_type="organization",
        to_type="organization",
        temporal_kind="static",
        auto_allowed=False,
    ),
    _n(
        "contracted_with",
        label="contracted with",
        inverse_label="contracted with",
        from_type="organization",
        to_type="organization",
        temporal_kind="dynamic",
        auto_allowed=True,
        symmetric=True,
    ),
    _n(
        "regulated_by",
        label="regulated by",
        inverse_label="regulates",
        from_type="organization",
        to_type="organization",
        temporal_kind="dynamic",
        auto_allowed=True,
    ),
    _n(
        "sued_by",
        label="sued by",
        inverse_label="sued",
        from_type="organization",
        to_type="organization",
        temporal_kind="dynamic",
        auto_allowed=True,
    ),
    _n(
        "competes_with",
        label="competes with",
        inverse_label="competes with",
        from_type="organization",
        to_type="organization",
        temporal_kind="dynamic",
        auto_allowed=True,
        symmetric=True,
    ),
    _n(
        "supports",
        label="supports",
        inverse_label="supported by",
        from_type="organization",
        to_type="organization",
        temporal_kind="dynamic",
        auto_allowed=True,
    ),
    _n(
        "opposes",
        label="opposes",
        inverse_label="opposed by",
        from_type="organization",
        to_type="organization",
        temporal_kind="dynamic",
        auto_allowed=True,
    ),
    _n(
        "affiliated_with",
        label="affiliated with",
        inverse_label="affiliated with",
        from_type="organization",
        to_type="organization",
        temporal_kind="dynamic",
        auto_allowed=False,
        symmetric=True,
        crosswalk=NatureCrosswalk(tac_kbp="org:political_religious_affiliation"),
    ),
    # Organization → Location
    _n(
        "located_at",
        label="located at",
        inverse_label="location of",
        from_type="organization",
        to_type="location",
        temporal_kind="dynamic",
        auto_allowed=True,
        location_types=LOCATED_AT_LOCATION_TYPES,
        crosswalk=NatureCrosswalk(schema_org="location"),
    ),
    _n(
        "based_in",
        label="based in",
        inverse_label="headquarters of",
        from_type="organization",
        to_type="location",
        temporal_kind="dynamic",
        auto_allowed=True,
        location_types=BASED_IN_LOCATION_TYPES,
        crosswalk=NatureCrosswalk(wikidata="P159", tac_kbp="org:city_of_headquarters"),
    ),
    _n(
        "operates_in",
        label="operates in",
        inverse_label="has operating org",
        from_type="organization",
        to_type="location",
        temporal_kind="dynamic",
        auto_allowed=True,
        location_types=OPERATES_OR_SERVES_LOCATION_TYPES,
    ),
    _n(
        "serves",
        label="serves",
        inverse_label="served by",
        from_type="organization",
        to_type="location",
        temporal_kind="dynamic",
        auto_allowed=True,
        location_types=OPERATES_OR_SERVES_LOCATION_TYPES,
    ),
    _n(
        "founded_in",
        label="founded in",
        inverse_label="founding place of",
        from_type="organization",
        to_type="location",
        temporal_kind="static",
        auto_allowed=True,
        location_types=FOUNDED_IN_LOCATION_TYPES,
    ),
    _n(
        "owns_property_in",
        label="owns property in",
        inverse_label="property owned by",
        from_type="organization",
        to_type="location",
        temporal_kind="dynamic",
        auto_allowed=False,
        location_types=OWNS_PROPERTY_IN_LOCATION_TYPES,
        crosswalk=NatureCrosswalk(ftm="Ownership"),
    ),
    # Organization → Person
    _n(
        "endorsed",
        label="endorsed",
        inverse_label="endorsed by",
        from_type="organization",
        to_type="person",
        temporal_kind="static",
        auto_allowed=True,
    ),
    _n(
        "sued_by",
        label="sued by",
        inverse_label="sued",
        from_type="organization",
        to_type="person",
        temporal_kind="dynamic",
        auto_allowed=True,
    ),
)


def _index_natures() -> tuple[
    dict[tuple[str, str, str], NatureDef],
    dict[tuple[str, str], frozenset[str]],
    dict[tuple[str, str], frozenset[str]],
    dict[str, str],
    dict[str, frozenset[str]],
    frozenset[tuple[str, str]],
]:
    by_key: dict[tuple[str, str, str], NatureDef] = {}
    auto_by_pair: dict[tuple[str, str], set[str]] = {}
    all_by_pair: dict[tuple[str, str], set[str]] = {}
    alias_to_slug: dict[str, str] = {}
    location_by_nature: dict[str, frozenset[str]] = {}
    pairs: set[tuple[str, str]] = set()

    for nature in PREFERRED_NATURES:
        key = (nature.slug, nature.from_type, nature.to_type)
        if key in by_key:
            raise ValueError(f"Duplicate nature binding: {key}")
        by_key[key] = nature
        pair = (nature.from_type, nature.to_type)
        pairs.add(pair)
        all_by_pair.setdefault(pair, set()).add(nature.slug)
        if nature.auto_allowed:
            auto_by_pair.setdefault(pair, set()).add(nature.slug)
        for alias in nature.aliases:
            alias_to_slug[alias.strip().lower()] = nature.slug
        alias_to_slug.setdefault(nature.slug, nature.slug)
        if nature.location_types is not None:
            # Last write wins when same slug has location rules on one pair only — OK.
            location_by_nature[nature.slug] = nature.location_types

    return (
        by_key,
        {k: frozenset(v) for k, v in auto_by_pair.items()},
        {k: frozenset(v) for k, v in all_by_pair.items()},
        alias_to_slug,
        location_by_nature,
        frozenset(pairs),
    )


(
    _NATURES_BY_KEY,
    _AUTO_NATURES_BY_PAIR,
    _ALL_NATURES_BY_PAIR,
    _ALIAS_TO_SLUG,
    _LOCATION_GRANULARITY_BY_NATURE,
    AUTO_LINK_ENDPOINT_PAIRS,
) = _index_natures()


def all_preferred_natures() -> tuple[NatureDef, ...]:
    return PREFERRED_NATURES


def nature_def(
    slug: str,
    from_type: str,
    to_type: str,
) -> NatureDef | None:
    return _NATURES_BY_KEY.get(
        (slug.strip().lower(), from_type.strip().lower(), to_type.strip().lower())
    )


def normalize_preferred_nature_slug(raw: str | None) -> str | None:
    if raw is None:
        return None
    stripped = raw.strip().lower()
    if not stripped:
        return None
    return _ALIAS_TO_SLUG.get(stripped, stripped)


def is_auto_link_endpoint_pair(from_entity_type: str, to_entity_type: str) -> bool:
    return (from_entity_type.strip().lower(), to_entity_type.strip().lower()) in (
        AUTO_LINK_ENDPOINT_PAIRS
    )


def auto_link_natures_for_pair(from_entity_type: str, to_entity_type: str) -> frozenset[str]:
    key = (from_entity_type.strip().lower(), to_entity_type.strip().lower())
    return _AUTO_NATURES_BY_PAIR.get(key, frozenset())


def preferred_natures_for_pair(from_entity_type: str, to_entity_type: str) -> frozenset[str]:
    key = (from_entity_type.strip().lower(), to_entity_type.strip().lower())
    return _ALL_NATURES_BY_PAIR.get(key, frozenset())


def allowed_location_types_for_auto_nature(nature: str) -> frozenset[str] | None:
    return _LOCATION_GRANULARITY_BY_NATURE.get(nature.strip().lower())


def person_location_forbidden_location_types() -> frozenset[str]:
    return ADDRESS_LIKE_LOCATION_TYPES


def temporal_kind_for_nature(
    slug: str,
    from_type: str,
    to_type: str,
) -> TemporalKind:
    row = nature_def(slug, from_type, to_type)
    if row is None:
        return "dynamic"
    return row.temporal_kind
