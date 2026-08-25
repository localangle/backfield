# Connection nature catalog

**Status:** Shipped (Phase A). Companion to
[`knowledge-graph.md`](knowledge-graph.md) (D3). This is the curated **global preferred nature
catalog** in code (`backfield_entities/connections/natures.py`). Org custom natures remain a
DB escape hatch (`stylebook_connection_nature_custom`).

## Sources

No single established vocabulary covers news entity relationships cleanly, so this catalog is a
curated union of two that were built for exactly our text:

- **TAC KBP slot filling** (NIST): the standard relation inventory for news relation extraction
  (`per:employee_or_member_of`, `org:top_members_employees`, `per:cities_of_residence`,
  `org:parents`, …). Battle-tested against news corpora; maps almost one-to-one onto our
  person/org/location pairs.
- **FollowTheMoney (FtM)** (OCCRP Aleph / OpenSanctions): investigative-journalism ontology whose
  interstitial link entities (Employment, Directorship, Membership, Ownership, Family,
  Representation, Associate) are dated intervals — the same "edge with validity" shape as our
  target model.

**Schema.org** properties and **Wikidata** P-ids are carried as crosswalk identifiers for interop
(public API consumers, future export), not as the source of the list. Crosswalk values are
indicative; verify before publishing them in API docs.

## Conventions

- **Slugs** stay lowercase snake_case, matching existing natures where possible.
- **Canonical direction:** each nature declares one storage direction, read as
  `from —nature→ to` in subject–verb–object order. Do not define inverse slugs
  (`represented_by` is retired; store `represents`). UIs and APIs render the inverse label when
  displaying the edge from the other endpoint.
- **Tense convention:** present tense for ongoing states (`works_for`, `leads`); past tense for
  event-anchored facts (`founded`, `defeated`, `endorsed`, `acquired_by`).
- **Symmetric natures** (`spouse_of`, `works_with`, `partnered_with`, `competes_with`,
  `merged_with`, `sibling_of`, `family_of`): one edge per pair; normalize endpoint order at write
  time.
- **`temporal_kind`** (`static` | `dynamic`; see ADR D3b): static facts rarely close; dynamic
  facts are candidates for close / `as_of`. We do not use a separate `atemporal` kind — the few
  candidates (family) are treated as static.
- **`auto`**: whether machine inference may propose this nature. Manual-only natures appear in
  editor pickers but not in prompts (looser semantics that invite false merges).
- **Role nuance** (job titles, board seat names, "co-founder") lives in the edge
  `description` / role label, not in new slugs — the TAC `per:title` and FtM `role` equivalent.
- **Domain-specific natures policy:** add a beat-specific slug only when all three hold:
  (1) it is news-frequent, (2) the generic slug actively misleads or blocks a real query, and
  (3) a clean external crosswalk exists. Sports passes today (`plays_for`, `coaches`, `team_of`);
  education (`teaches_at`) is a plausible future add; crime/courts stays out (charge/event
  territory, not durable entity ties). Everything else in a domain uses the generic slugs
  (owners → `owns`, GMs and staff → `works_for` / `leads`).

## Validation against production data (Aug 2026)

A review of ~20K `stylebook_connections` rows on a production-shaped corpus informed the catalog:

- **Beat mix:** `sports_team` is the top organization type (1,463) and `athlete` the top person
  type (3,203, plus 485 coaches) — sports natures are justified. Schools/universities (~1,266)
  and government/courts/police orgs (~1,300) follow.
- **Largest null-nature gap:** person→location office-holding ("mayor of Chicago", "governor of
  Illinois", "Sheriff of Cook County") → `holds_office_in`.
- **Editors invent natures when the catalog lacks them:** 342 manual `plays_for` org→org edges
  are really team→school ties → `team_of`; confirms the org custom-nature +
  `equivalent_to` design.
- **Recurring null person→person:** appointments (`appointed_by`), romantic partners
  (`partner_of`), coach→athlete (`coaches` on the person→person pair).
- **`owns` confirmed** by repeated null person→org ownership descriptions.
- **Correctly out of scope:** crime/court and emergency flows ("detention hearing at",
  "pronounced dead at", medical-examiner attributions) are event-shaped, not durable ties;
  media attribution ("AP is credited as the source") is article metadata. These stay out of the
  catalog.
- **Cleanup flagged for Phase A migration:** 25 `represented_by` rows (inverse normalization);
  a handful of weak "is associated with" null-nature edges and at least one edge whose
  description states no relationship exists — the redesigned writer should reject
  no-relationship descriptions outright.

## Catalog

### Person → Organization

| Slug | Temporal | Auto | Crosswalk | Notes |
|------|----------|------|-----------|-------|
| `works_for` | dynamic | yes | TAC `per:employee_or_member_of`; FtM Employment; schema `worksFor`; WD P108 | Employment, incl. government employers |
| `leads` | dynamic | yes | TAC `per:top_member_employee_of`; WD P169/P488 | Decision-making authority over the whole org (CEO, chief, superintendent, mayor→city) |
| `board_member_of` | dynamic | yes | FtM Directorship | School boards, nonprofit boards, commissions; distinct from `leads` |
| `member_of` | dynamic | yes | FtM Membership; schema `memberOf`; WD P463/P102 | Party, union, congregation, team (sports `member_of` stays here) |
| `founded` | static | yes | TAC `org:founded_by` (inverse); schema `founder`; WD P112 | |
| `owns` | dynamic | yes | FtM Ownership; TAC `org:shareholders` (inverse); WD P127 (inverse) | Owner/major shareholder |
| `studied_at` | static | yes | TAC `per:schools_attended`; schema `alumniOf`; WD P69 | |
| `represents` | dynamic | yes | FtM Representation | Lawyer, agent, spokesperson for the org |
| `candidate_for` | dynamic | yes | — | Declared candidacy for an office/body; close when race ends |
| `donated_to` | static | manual first | — | Campaign/charitable giving; auto later only with strong evidence rules |
| `plays_for` | dynamic | yes | WD P54 | Athlete on a team roster; preferred over `member_of` for sports teams |
| `coaches` | dynamic | yes | WD P286 | Coaching staff of a team; preferred over `works_for`/`leads` for coaches |

### Person → Location

| Slug | Temporal | Auto | Crosswalk | Notes |
|------|----------|------|-----------|-------|
| `represents` | dynamic | yes | — | Elected representation of a district or constituency |
| `holds_office_in` | dynamic | yes | WD P39 (adapted) | Executive/appointed office over a jurisdiction (mayor, governor, sheriff). Largest null-nature gap in production data |
| `lives_in` | dynamic | yes | TAC `per:cities_of_residence`; schema `homeLocation`; WD P551 | Never address-like locations (existing rule) |
| `born_in` | static | yes | TAC `per:city_of_birth`; schema `birthPlace`; WD P19 | |
| `died_in` | static | yes | TAC `per:city_of_death`; WD P20 | |
| `native_of` | static | yes | TAC `per:origin` (adapted) | "Grew up in", hometown framing distinct from current residence |
| `owns_property_in` | dynamic | manual first | FtM Ownership→Asset | Landlords/developers; high evidence bar before auto |

### Person → Person

| Slug | Temporal | Auto | Crosswalk | Notes |
|------|----------|------|-----------|-------|
| `spouse_of` | dynamic | yes | TAC `per:spouse`; schema `spouse`; WD P26 | Symmetric |
| `parent_of` | static | yes | TAC `per:children` (inverse `per:parents`); WD P40 | Canonical direction parent→child |
| `sibling_of` | static | yes | TAC `per:siblings`; WD P3373 | Symmetric |
| `family_of` | static | yes | TAC `per:other_family`; FtM Family | Symmetric catch-all beyond the three above |
| `works_with` | dynamic | yes | schema `colleague` | Symmetric |
| `reports_to` | dynamic | yes | — | |
| `represents` | dynamic | yes | FtM Representation | Attorney/agent/spokesperson for a person (replaces `represented_by`) |
| `succeeded` | static | yes | WD P1365 | Took over a role from |
| `appointed_by` | static | yes | — | Appointee is `from`; core government news (frequent in null-nature data) |
| `partner_of` | dynamic | yes | — | Romantic partner short of marriage; symmetric |
| `coaches` | dynamic | yes | WD P286 | Coach→athlete (also person→org for team staff) |
| `defeated` | static | yes | — | Election/contest outcome |
| `endorsed` | static | yes | — | Election endorsements |
| `supports` | dynamic | yes | — | Ongoing public backing |
| `opposes` | dynamic | yes | — | Ongoing public opposition |
| `associate_of` | dynamic | manual only | FtM Associate | Documented association that fits nothing else; too mushy for auto |

### Organization → Organization

| Slug | Temporal | Auto | Crosswalk | Notes |
|------|----------|------|-----------|-------|
| `parent_of` | dynamic | yes | TAC `org:subsidiaries`/`org:parents`; schema `subOrganization`; WD P749 (inverse) | Canonical direction parent→subsidiary |
| `member_of` | dynamic | yes | TAC `org:member_of`/`org:members`; WD P463 | Leagues, coalitions, chambers (team→league) |
| `team_of` | dynamic | yes | — | Sports team → school/institution that fields it. Production data has 342 manual `plays_for` org→org edges with exactly this meaning; migrate them here |
| `oversees` | dynamic | manual first | — | Agency administers/oversees a program or system; promote to auto once evidence rules are proven |
| `owns` | dynamic | yes | FtM Ownership; TAC `org:shareholders`; WD P127 | |
| `acquired_by` | static | yes | — | Event-anchored; acquired org is `from` |
| `merged_with` | static | yes | — | Symmetric |
| `partnered_with` | dynamic | yes | — | Symmetric |
| `funded_by` | dynamic | yes | schema `funder` (inverse) | Grants, sponsorships, subsidies |
| `donated_to` | static | manual first | — | Directed giving (PACs, foundations) |
| `contracted_with` | dynamic | yes | — | |
| `regulated_by` | dynamic | yes | — | |
| `sued_by` | dynamic | yes | — | Defendant is `from`; also allowed on person↔org pairs (below) |
| `competes_with` | dynamic | yes | — | Symmetric |
| `supports` / `opposes` | dynamic | yes | — | Positions on issues/other orgs |
| `affiliated_with` | dynamic | manual only | TAC `org:political_religious_affiliation` (adapted) | Loose formal affiliation; too mushy for auto |

### Organization → Location

| Slug | Temporal | Auto | Crosswalk | Notes |
|------|----------|------|-----------|-------|
| `located_at` | dynamic | yes | schema `location` | Specific site/address (existing granularity rules apply) |
| `based_in` | dynamic | yes | TAC `org:city_of_headquarters`; WD P159 | HQ locality |
| `operates_in` | dynamic | yes | — | |
| `serves` | dynamic | yes | — | Service area |
| `founded_in` | static | yes | — | |
| `owns_property_in` | dynamic | manual first | FtM Ownership→RealEstate | |

### Cross-pair extensions (new endpoint pairs)

| Slug | Pairs | Temporal | Auto | Notes |
|------|-------|----------|------|-------|
| `endorsed` | org→person | static | yes | Newspaper/union endorses candidate |
| `sued_by` | person→org, org→person, person→person | dynamic | yes | Litigation is inherently cross-type |
| `donated_to` | person→org, org→org | static | manual first | Campaign finance |

## Migration from current natures

See the full **Existing-data migration plan** in
[`knowledge-graph.md`](knowledge-graph.md#existing-data-migration-plan). Nature-specific notes:

- Every existing auto nature keeps its slug except **`represented_by`**, which normalizes to
  `represents` with endpoints swapped (canonical-direction rule).
- Org→org **`plays_for`** (manual team→school pattern in production) remaps to **`team_of`**.
- Existing type-granularity constraints (e.g. `located_at` location types, person→location
  address ban) carry over unchanged onto the registry entries.
- Subsumption pairs generalize with the catalog: `leads` > `works_for` > `member_of`;
  `located_at` > `based_in`; `plays_for` > `member_of` and `coaches` > `works_for` for sports
  teams.
- The current prompt rule mapping athletes to `member_of` a `sports_team` retargets to
  `plays_for` (and coaches to `coaches`).
- Do **not** auto-remap null-nature descriptions to new slugs (`holds_office_in`, `owns`, …)
  in the first cut — forward inference + optional offline suggest queue later.

## Registry entry shape

Each catalog entry in code carries:

```text
slug, label, inverse_label, endpoint_pairs, temporal_kind,
symmetric, auto_allowed, aliases (synonyms normalized at inference),
location_type_constraints (where applicable),
crosswalk: {schema_org, wikidata, ftm, tac_kbp}
```

Counts: roughly 45 natures across 8 endpoint pairs — larger than today's ~30 but curated, with
manual-only flags keeping the mushiest relations out of prompts.
