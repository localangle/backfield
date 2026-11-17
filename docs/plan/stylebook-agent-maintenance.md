# Agent-driven Stylebook maintenance (planning)

**Status:** Planning. First case study (duplicate places) is complete; endpoints are not built.
This is product intent plus evidence from a real cleanup, not a runtime contract. Re-derive exact
schemas when implementation starts.

## Goal

Let agents (first Cursor agents, later external agents over MCP tools) maintain the Stylebook:
find problems, decide what is safe, apply fixes, and leave an audit trail. The method is to run
real cleanups with a coding agent first, record where the existing tools fall short, and only then
design the API that other agents will call.

This document covers the first case: **places that clearly refer to the same real-world place**.

## Case study: consolidating duplicate places

Scope: one Stylebook (`cpm-stylebook`), location canonicals only. Applied locally on 2026-11-16.

| Measure | Value |
|---|---|
| Place canonicals before / after | 21,033 / 17,186 |
| Canonicals consolidated | 3,846 in about 2,970 groups (about 560 by shared geography or identical label, 619 by same address or same name nearby (tiers C and D), 18 districts by parsed district number, about 60 by reordered words and larger same-label distances, about 30 by reading mention text or outside knowledge, and 1,770 in 1,311 groups by agreement of two independent model readers, [section 10](#10-letting-models-adjudicate)) |
| Linked mentions moved to survivors | about 3,150 (total linked mentions unchanged at 19,231) |
| Aliases carried forward | 2,553 through pass 15 (not re-tallied for the model-adjudicated pass; see the run ledger) |
| Connections rewired / deduplicated | 221 / 277 through pass 15 |
| Activity rows written | one per merged-away canonical, all `actor_type = "agent"` |
| Left alone on purpose | about 2,600 canonicals in 980 clusters (see below) |

Seven passes were needed, because each round of review exposed a candidate gap
(see [Detection gaps](#detection-gaps)):

1. The existing finder's candidates.
2. Candidates it cannot see: accent and punctuation variants.
3. A trailing parenthetical, and a long qualifier on one side.
4. Same street address and stored point with similar names (`30 N. LaSalle` vs `30 N. LaSalle St.`),
   plus splitting groups that one odd member used to block.
5. Leftovers that became clear once pass 4 removed their blockers.
6. Same address with no stored point on one side, and the same name within 250 m (tiers C and D
   below). Prompted by `95th/Dan Ryan station`, `Above and Beyond Food Pantry`, and the Lincoln
   Library pair.
7. Three merges decided by reading mention text, for cases no rule can settle (below).

The planner still proposes a handful of groups at any moment, and they keep coming back: a few are
canonicals that ingest created minutes after the previous pass (see
[Findings](#1-most-duplicates-are-manufactured-by-ingest)), and one fails for a data reason (see
[Findings](#9-data-integrity-findings)). Pair counts in the next table are higher than pass 1's
because the candidate set is broader, not because there are more problems.

### What "clearly the same place" meant

The planner starts from the existing finder's candidate pairs, then gathers evidence for every
pair in a cluster and classifies it.

| Verdict | Rule | Outcome |
|---|---|---|
| **A: same geocode** | Same place kind, near-identical stored geography (about 5 m), one label's qualifiers are a subset of the other's (`…, Chicago, IL` vs `…, Rosemoor, Chicago, IL`), and every extra qualifier is a known area (a neighborhood or city in this Stylebook) or a street address. A parenthetical on one side only (`Pulaski station (Blue Line)`) is detail; different parentheticals on both sides are a conflict | Merge |
| **B: same label** | Same place kind, labels identical after folding accents, quotes, punctuation, spacing; at least one qualifier; stored geography within 250 m or missing on one side | Merge |
| **C: same address** | Same place kind, same street address (starts with a house number, not a copy of the name), same state, and primary names that match once generic words (`the`, `office`, `building`, `station`, `theater`/`theatre`, `St.`/`Saint`) are removed. The stored point must be identical, or missing on one side (the stored address is then the evidence). Remaining differences must be a near-identical word (typo, accent, plural, apostrophe), or at most 6 characters of added or dropped words | Merge |
| **D: same name nearby** | Same place kind, same cleaned name (as in C) with at least two distinctive words, and stored points within 250 m. With no point on one side, the cleaned names must be exactly equal and the two street addresses must not differ. Extra qualifiers must be known areas or addresses | Merge |
| **E: evidence** | Decided by reading the mention text for each canonical, for cases a rule cannot settle | Merge, recorded as evidence-based |
| **Conflict** | Different place kind, qualifiers that disagree (`Brownsville, TN` vs `TX`), or stored points far apart (`BP, Chicago` 7–15 km) | Keep separate |
| **Unsure** | Qualifiers compatible but no shared geography to confirm, or the extra qualifier is not a known area or address and may name a different site (`Gene & Georgetti, Midway International Airport`, `O'Hare, Terminal 5`) | Keep separate, needs evidence |

A merged group requires **every pair inside it** to pass A, B, or C. A connected group with one odd
member is split into subgroups where every pair passes; the odd member is left for review. Holding
the whole group instead (the first version) blocked 40 identical `Griffin Museum of Science and
Industry` canonicals because one of them had no geography and another had a different address.
Survivor ties are broken toward the shorter primary name, which prefers `13th Floor Haunted House,
Schiller Park, IL` over `13th Floor Add 2Haunted House Chicago, Chicago, IL`.

What tier C refuses, and why (found by probing the data and reading the first proposal):

| Pair | Why it stays separate |
|---|---|
| `Monroe Harbor` / `Montrose Harbor` | Different harbors; a bad geocode put them on one point. Raw character similarity is 0.92. A changed word must be nearly the same word, not just a similar string. |
| `Legends South` / `Legends South A3`, `Magos Tacos y Tamales` / `… 2`, `AMC River East 21` / `AMC River East` | An added or dropped number can be a unit, phase, or branch. |
| `St. Philip Neri School` / `… School Gym`, `Northwestern Pritzker School of Law` / `… Atrium`, `Silver Springs…` / `Big Lake at Silver Springs…` | The longer name is a part of the place. |
| `Navy Pier` / `Spirit of Navy Pier` | The same address, but one is a ship. |
| `Jackson Station` / `Jackson CTA station` | Two CTA stations are called Jackson; the labels do not say which. Held for a person. |
| `BP`, in five canonicals | A chain. One geocode for the name is weak evidence that the mentions mean one station. Held for a person. |
| `Auburn Gresham Center, Auburn Gresham` / `Englewood Center, Englewood` | Cleaning dropped every word that appeared in a qualifier, which shrank both names to `center`. Only city, state, and country words may be dropped. |
| `Auditorium Building` / `Auditorium Theater`, `Millennium Park` / `Millennium Park Station`, `Hamlin Park` / `Hamlin Park Theater` | Dropping generic words (`building`, `theater`, `station`) makes a building, venue, or station look the same as the place around it. Two different descriptors conflict; the park cases were held for a person. |
| `Chicago Public Library, South Chicago Branch` / `Chicago Public Library`; `CTA Chicago Station` / `CTA` | The same cleaned name, but the street addresses differ. With no stored point, equal names alone are not evidence. |
| `Ogden International School` / `Ogden International High School`, `Unity Christian School` / `…High School`, `University of Chicago Laboratory High School` / `…Laboratory Schools` | Different school levels are often different campuses. |
| `Deer Grove East Forest Preserve` / `Deer Grove Forest Preserve`, `Highmark Stadium` / `New Highmark Stadium` | A direction, `new`, or `old` marks one part or one generation of a place. |
| `Whole Foods` / `Whole Foods (planned)` | A store that does not exist yet. |
| `Obama Presidential Center` / `…Forum`, `Illinois State University` / `…Quad` | A building or feature inside the larger place. |
| `North Side` / `North Side, Andersonville`, `Financial District`, `CTA Blue Line` / `CTA Blue Line, Wicker Park`, `Lakefront Trail` | Vague regions and long lines. A point means little for them, so a nearby point is no evidence. |
| `Shell`, `Citgo`, `Zanies` | One-word names are too ambiguous for fuzzy matching. They still merge when labels are identical. |

**Identical stored geography is not proof by itself.** A first draft of pass 3 merged pairs with
identical geography and differing neighborhood qualifiers. Reading the proposal showed it would
have merged separate branches of the same business: `Smoke Daddy` (Wicker Park vs Wrigleyville),
`The Chicago Diner` (Lake View vs Logan Square), `Social Security Administration office` (Lincoln
Square vs Kenwood). The name-only geocode had put both branches on one point. Conflicting
qualifiers outweigh matching geography, so those pairs now stay separate. This is the main reason
rules alone are not enough and agents need the evidence package below.

Survivor choice, in order: has geography, has the most editorial data (curated aliases, metadata,
connections), has the most linked mentions, oldest. The merge never copies geography, so a survivor
without it would silently discard the others'.

### What was left alone

| Class | Pairs | Why it was not merged | What would settle it |
|---|---|---|---|
| Qualifiers disagree | 977 | Often different places (`Stockton, CA` vs `IL`, `Vatican City, WA` vs `FL`), different branches of one business, or a sign of a bad label | Mention context; whether one label is a mistake |
| Different place kind | 212 | The planner treats a kind difference as a conflict. The product's own merge guard is looser: it allows 169 of these pairs because the labels name the same thing. Some are one place with the wrong kind (`115 Bourbon Street`, address vs place); others are different places that share a name (`Lincoln Park` the neighborhood vs the park, 1.4 km apart) | A kind-compatibility table plus geography or mention evidence; a "fix the kind, then merge" action |
| Points far apart | 160 | Same name, different sites (`BP`, `Navy Pier` 321 m, `Pacific Ocean`) | Address text, mention context |
| Unsure | 149 | Compatible labels, but geography is missing on at least one side (of the 380 unsure at the first pass: 269 had it on one side only, 65 on neither, 46 on both), or both exist and are close but could be different buildings (`Kennedy-King College` vs `…, U Building`). Also two stations that look identical: `35th/White Sox Red Line Station` (a CTA Red Line station) and `35th Street station, Rate Field` (a Metra station) are different stations. The labels and geography look alike; the mention text separates them | Geography of the linked mentions; address; mention snippets |
| Extra qualifier may be a different site | 122 | One label adds something that is not a known area or address (a terminal, a campus, a sub-building) | Mention snippets; address |
| Held for a person | 3 groups | `Los Angeles, CA` has the right label but no geography; `Los Ángeles, CA` has geography but the wrong label (needs a field-by-field merge). The five `BP` canonicals and the two `Jackson` stations pass the rules but need a person (see tier C) | Field-by-field merge (see below); mention evidence |
| Failed to merge | 1 group | The two `Monona Bay` canonicals; one linked mention is in an invalid state (see [Findings](#9-data-integrity-findings)) | Fix the mention, then merge |

Full per-pair evidence was written to a scratch ledger for each class; the product should persist
the same thing (see [Evidence package](#evidence-package)).

## Findings

### 1. Most duplicates are manufactured by ingest

- 252 of 811 exact-label duplicate groups were created less than 10 seconds apart; 369 within a
  minute. The example in the original screenshot was three canonicals created in 9 seconds, two
  with the same address and point. This is concurrent workers each deciding to create a new place.
- Duplicates feed back into ingest: an exact alias match with more than one surviving candidate
  defers (`ambiguous_exact_canonical_match`), so every duplicate also adds review work.

- The Stylebook was still growing during this work. 10,503 canonicals were created on 2026-11-13
  and about 2,200 to 2,400 a day after that; 4,444 had been created by mid-afternoon on the day of
  the cleanup, and 80 of those already had a same-label sibling. Duplicates also reappeared within
  minutes of a pass (the `Abraham Lincoln National Cemetery` pair was created after the first
  passes). The cleanup is a snapshot.

Cleanup alone will see the duplicates return. Prevention belongs in the spec.

### 2. The merge operation loses data in ways a UI user would not notice

Verified against the code and, where noted, against rolled-back runs on real data.

| Gap | Effect | Evidence |
|---|---|---|
| Relinking the last linked mention prunes the empty source canonical and soft-closes its open connections **before** merge rewires connections. Rewiring does not filter on closed state. | Connections are moved but closed. | Rolled-back test: 8 of 46 source connections closed with the stock merge, 0 when rewired first |
| Aliases are only refreshed for linked mentions. The rest cascade-delete with the source. | Old wordings stop resolving; ingest can mint the duplicate again. | At least 110 curated aliases sat on first-pass sources |
| A source with no alias row for its own label (older imported records) loses that label. | Same as above. | 2 rows needed backfill |
| A survivor that already holds the merged-away wording as an ingest-derived alias keeps it untrusted. Exact lookups ignore ingest-derived aliases. | The wording stops resolving after the merge, so ingest can mint the duplicate again. | 4 labels (8 alias rows) after pass 6; fixed by upgrading the existing alias to a reviewed-merge alias |
| Geography and metadata are not copied. | Survivor choice silently loses them. | Survivor-selection audit; metadata cascades with the source |
| No field-level choice (label from A, geography from B). | Some pairs cannot be merged correctly. | `Los Angeles` / `Los Ángeles` |
| `session.delete(source)` after the prune already deleted it. | Harmless SQLAlchemy warning on every multi-source merge. | Seen on dry runs |
| Activity is written with `actor_type = "user"` by the endpoint. | Agent and human merges are indistinguishable. | Activity supports `"agent"`; endpoint hard-codes `"user"` |
| Semantic reindex is queued from the API layer, not the shared library. | A caller that uses the library directly skips it. | `stylebook_api/semantic_reindex.py` |
| No persisted record that an old ID now means another. | Webhooks announce `merged_into`; clients that only pull get a 404. | Event contract has `merged_into`; no tombstone table |

### 3. Detection gaps

- The duplicate finder joins on the exact lowercase primary name. Accents, curly vs straight
  apostrophes, hyphens, slashes, and spacing hide duplicates (`Café`/`Cafe`, `Children’s`/`Children's`,
  `La Porte`/`LaPorte`, `Beverly/Morgan Park`/`Beverly-Morgan Park`). 90 groups, 72 of them clean
  merges, were invisible to the existing check.
- The finder also requires the full label to be at least 0.72 similar. A trailing parenthetical or a
  long qualifier drops similarity below that even when the name is the same
  (`Clinton station (Green Line), Chicago, IL` vs `Clinton station, Near West Side, Chicago, IL`
  scores 0.64). The planner now strips parentheticals from the name and groups by name plus final
  qualifier with no similarity cutoff. That found the `35th-Bronzeville-IIT station` pair and 64
  other groups.
- Names that differ in the first word or two hide duplicates that share an address entirely.
  `13th Floor Haunted House, Schiller Park, IL` and `13th Floor Add 2Haunted House Chicago,
  Chicago, IL` (a mangled name and the wrong city), `30 N. LaSalle` and `30 N. LaSalle St.`, and
  `33 Realty` and `33 Realty offices` all have the same street address and the same stored point,
  but different primary names, so no name-based candidate rule sees them. 3,999 same-kind pairs share a street
  address and point. Most are not duplicates (`City Hall` and `Mayor's Press Room` at one address,
  the many `Navy Pier` venues), so the rule needs a name test as well: pass 4 merged 205 groups
  where the names match apart from generic words and small typos.
- Geography alone finds a lot, and little of it is safe. 4,292 same-kind canonicals share a point
  within about 5 m of another; 3,655 of those fall outside the finder's clusters, and only 1,283 of
  those have high name overlap. A shared point is weak evidence by itself (see the
  [`Smoke Daddy` example](#what-clearly-the-same-place-meant)). Recommendation: generate spatial
  candidates only with name overlap, and send them to the evidence step instead of auto-merging.
- Cleanup judgments sometimes need to read the text. `35th Street station, Rate Field` (Metra) and
  `35th/White Sox Red Line Station` (CTA) look like the same station and are not. The merge
  decision for pairs like this needs the mention snippets and a human or agent that reads them.
- The finder's output is a flat cluster. It does not say which members are safe to merge, which
  are different places, or why. That judgment is what the planner added.
- A cleanup check has never been run through the UI on this Stylebook (no check-run rows), so
  counts shown to users are computed on demand.

### 4. What this means for lookups

Merging changes how ingest resolves names. Verified after the run for all 3,846 merged-away labels,
each checked against the canonical that finally absorbed it. Merges chain: a pass 1 survivor can be a
pass 4 source, so a check against the original survivor reports false misses.

| Resolution path | Labels |
|---|---|
| Final survivor's own label matches after folding accents and punctuation | 1,039 |
| Trusted alias carried forward | 886 |
| Ambiguous: another, unmerged canonical holds the same wording | 25 |
| Not resolved | 0 (4 were unresolved after pass 6 until the alias fix above) |

Design points:

- Exact lookups only trust aliases whose provenance is not `substrate_ingest`. Aliases carried over
  by a reviewed merge are written as `stylebook_cleanup_merge` so they count. Existing survivor
  aliases are never overwritten, which means a wording the survivor already held as an ingest alias
  stays untrusted and resolves through the label path instead. That works today but is easy to break.
- Duplicates that remain make the same wording ambiguous, which defers and queues review work.
  Merging reduces deferrals; it does not remove the cause.
- `location_merge_pair_blocked` is not a reliable safety net for mixed kinds. It blocks only
  deny-listed kind pairs and lets through any pair whose labels "share obvious identity", so it
  allowed 169 of the 182 mixed-kind pairs, including ones that are different places
  (`Lincoln Park` neighborhood vs park). A UI user can make those merges today. The agent API needs
  its own kind-compatibility rules and evidence, and the UI merge should share them.

### 5. What rules cannot settle

Three cases were merged by reading the mention text, and the evidence was decisive each time:

| Pair | What the mentions showed |
|---|---|
| `Above and Beyond, West Garfield Park` / `Above and Beyond Free Food Pantry` | One mention is a Spanish article ("la despensa Above and Beyond en West Garfield Park … comida enlatada gratuitos") that translates the English sentence about the pantry. A bare name next to a descriptive one is exactly where the same-address rule stops, because `Navy Pier` and `Spirit of Navy Pier` look the same. |
| Two `Abraham Lincoln National Cemetery, Elwood, IL` with points 1.7 km apart | Both sets of mentions are Veterans events at the one national cemetery in Elwood. One canonical has a name-only point; the other has the address of a road along the site. A cemetery this size can have two defensible points. |
| `Abraham Lincoln Presidential Library and Museum` | The same institution; the longer label is its formal name. One of the two street addresses has a digit typo (`112` vs `212` North 6th Street). |

The same-label-far-apart class is larger than this one case: 37 same-kind pairs with the same
label are 250 m to 3 km apart. Some are one large site (`Grant Park`, `McCormick Place`,
`University of Chicago`, `Waukegan High School`). Others are chains (`Jewel-Osco`, `Big Shoulders
Coffee`, `St. Mary's Catholic Church`) that really are several places. Distance cannot tell them
apart, so these need the mention text. The planner left all of them alone except the cemetery.

This is the strongest argument for the [evidence package](#evidence-package): each of these
decisions was easy once the text was on screen, and impossible before.

### 6. A second cleanup mode: addresses that are named places

An address and a named place at the same address are one place with two names, but only
sometimes. This is a different problem from the name-based tiers: the names differ by design, and
the address canonicals have no stored point (none of the 55 does), so neither the name test nor the
250 m rule applies. The only evidence is the geocoded street address, compared after normalizing
`W.`/`West` and `St.`/`Street`.

What the data showed:

- 96 canonicals are address-like (55 of kind address, 41 place canonicals whose label is a street
  address). 52 of them have at least one named place at the same address, in 131 pairs. The count
  is only trustworthy if the label itself matches its own geocoded street. Names that merely start
  with a number (`40 Acres Fresh Market`, `559 Park`, `1700 Theater`) must not count as addresses.
- Only 18 had exactly one named place at the address. The other 86 pairs involve two or more
  places, such as `3120 S. Halsted St.` (two police station names, probably one building),
  `4612 W. 59th St.` (three Midway terminal names, duplicates of each other), and `5959 N.
  Sheridan Rd.` (a Park District property and a congregation, different things).
- An address is also a legitimate subject for a mention. Merging it into one of several tenants
  would send every future mention of the bare address to that tenant.

Rule applied: merge only when exactly one named place sits at the address **and** the mention text
ties the address to the place. That means the address's own mentions name the place, or the
place's mention contains the street address. The named place always survives, and the address
wording is carried forward as a trusted alias.

Result: 18 candidates, 5 merged (`2869 S. Archer Ave.` into the bank, `3406 N. Harlem Ave.` into
Elite Sports Cards, `60 E. Van Buren St.` into the CHA headquarters, `834 W. Armitage Ave.` into
Armitage Avenue Methodist Church, `501 N. Ogden Ave.` into Twisted Spoke). Findings:

- `30 N. LaSalle` and `Former Chicago Stock Exchange` share an address but are different
  structures: the mentions describe the 44-story building built after the Stock Exchange
  building was demolished. A shared address does not mean a shared building.
- 12 candidates had no mentions on the address side and no co-occurrence of address and name anywhere
  in the mention text. After you approved outside knowledge as evidence, 6 more merged where the
  match is well known: the South Carolina Statehouse (`1100 Gervais St.`), Dusty Groove, Lincolnwood
  Town Center, the Apparel Center, Guinness Open Gate Brewery, and The Re-Up (whose mention puts it
  at 59th and Racine, and Racine is 1200 W.). 6 were held: `Wrigley Rooftops`, `Camry Lot`, `Pershing
  Terminal`, `Barrett Park`, `Western Works`, and the planned Madison Street complex. These are
  orphans on both sides, with no mentions and nothing in the data to corroborate them, and the person
  or agent doing the review did not know them well enough to decide. A wrong merge sends every future
  mention of the address to the wrong place, so they stay held. This is the limit of outside
  knowledge: it works for famous places and fails for the long tail, which is where an evidence package
  or a lookup against an external source would have to take over.
- The product's merge allows an address-to-place merge with no extra step.

Open questions for a product version: how to record public knowledge as evidence (the Apparel
Center is at 350 N. Orleans; accepted for the Rate Field renames, not yet for the 12 held address cases) and whether multi-place addresses should instead surface the places
to each other as possible duplicates.

### 7. A third mode: structured entities named in many ways (political districts)

Districts are the case where fuzzy name matching is the wrong tool. `9th Congressional District,
Illinois`, `Congressional District 9, IL`, `Illinois’s 9th Congressional District, IL`, and
`U.S. House District 9, Illinois` share almost no words in the same order, but they are one
identity: (kind, state, number). The catalog has three structured fields for exactly this
(`district_kind`, `district_number`, `district_key`) and **all 371 district canonicals leave them
empty**, so nothing can group them.

What was done: a parser turns a label into a key for the wording it explicitly understands (U.S.
House, Illinois House and Senate, Cook County Board of Commissioners). A pair groups only when the
label's key equals the key parsed from its own geocoded address. Anything else is held. Of 371
districts, 251 parsed. 18 groups merged (34 canonicals removed, 44 mentions relinked), including
the six wordings of the 9th Congressional District and the six of the 2nd.

Findings that generalize:

- **The label's state beats the stored state.** `Illinois's 9th Congressional District` is tagged
  TN, FL, WA, DE, CA, NC, and MI on different canonicals. The geocoder resolved the name to some
  other place with an "Illinois" or a number in it. Grouping by the stored state would have split
  one district into eight.
- **Survivor = the imported boundary.** Hand-imported districts carry a boundary of tens of
  thousands of points; the geocoded ones are 5-point estimate boxes. The ranking must count only
  real shapes (the stored GeoJSON is over about 1 KB), then linked mentions. Comparing JSON length
  naively let a larger box beat a record with 6 linked mentions.
- **Geometry is invisible to most checks for the imported records.** 1,495 canonicals (1,108
  cities, 90 counties, 58 neighborhoods, 239 districts) hold their real shape only in the stored
  GeoJSON; the geometry column the geographic checks read is empty. For the 239 districts that is
  the whole batch imported on 2026-11-13. Duplicate detection, geographic search, and the
  planner's point tests cannot see these shapes. The repository already has a one-off script for
  this (`scripts/rebind_location_postgis_geometry.py`); it has not been run.
- **Hold when label and address disagree.** `Illinois Senate District 26` has the address `Ward
  26`; `Congressional District 18, IL` has `18th District, Chicago`; `Ward 12, Chicago` has the
  address `State House District 12`. These are mis-geocodes, not duplicates, and need a repair
  action rather than a merge.
- **District numbers have a vintage.** Illinois had an 18th district until the 2022 map and has
  17 now. A merged label names a district number, not a map year; mentions from older articles
  can refer to boundaries the stored shape does not match. A product version should say so.
- **Parsing belongs at ingest too.** Filling the key fields when a district is created would let the
  existing exact-lookup path resolve every future wording to the right canonical, with no cleanup.

Still unparsed: Chicago wards, police districts, school board districts, TIF districts, and court
districts. There were no duplicates among the ones checked, so a parser for each was not worth
building yet.

### 8. Words in a different order, and renamed places

Two more gaps came from the same screen: `Rate Field` twice, and `Rate Field` next to `Guaranteed Rate
Field`.

**Identical labels that were too far apart.** The two `Rate Field` canonicals were 324 m apart, one
geocoded to `3326 S. Wentworth` and one to `333 W. 35th`. The same-label rule stopped at 250 m, which
cannot hold a stadium. Of 29 same-label place pairs 250 m to 1 km apart, all 21 that were under 500 m
were one large site or one relocated business when read by hand (McCormick Place, Grant Park,
Northwestern, Millennium Station, Prairie Avenue Bookshop). Between 500 m and 1 km the group mixes the
same park with different chains (`Big Shoulders Coffee`) and different buildings (`State of Illinois
Building`: 115 S. LaSalle vs 555 W. Monroe). The rule now allows identical labels up to 500 m. Beyond
that, mention text decides.

**Same words, different order.** About 120 place groups share the same words in another order
(`Festival Hall at Navy Pier` / `Navy Pier Festival Hall`, `Macy's State Street` / `State Street
Macy's`, `Cafe Brauer` / `Brauer Cafe`, `National Museum of Public Housing` / `National Public
Housing Museum`). The name test now accepts two or more equal words in any order, after the usual
cleanup, and the candidate buckets ignore order. The point and address evidence still decides: with no
stored point on either side, only an exact same-order match merges. A crude word-bag test is not
enough. The first probe dropped `Chicago` and `Illinois` and paired `University of Chicago` with
`University of Illinois at Chicago`; `Lake County, IN` and `Lake County, IL` also share every word. The
state qualifier and the locality-only word dropping are what prevent those. Reordering inside the
qualifiers (`Regenstein Center, Nichols Hall` / `Nichols Hall, Regenstein Center`) is not handled.

**Renames.** `Guaranteed Rate Field` is the same stadium as `Rate Field` under its earlier sponsor name
(one article reads "Guaranteed Rate Field (which will have a new name — Rate Field)"). No name rule
should catch this: the added word is 10 characters, over the 6-character limit, and `Navy Pier` against
`Spirit of Navy Pier` shows why that limit exists. The mentions settled it, and the earlier name now
resolves to the surviving canonical as a trusted alias. Related canonicals at the same site show
three different decisions:

| Canonical | Why it was left |
|---|---|
| `Rate Field Conference and Learning Center` | A venue inside the stadium at the same address, not the stadium. |
| `35th Street station, Rate Field` | A transit station beside the stadium. |
| `Old Comiskey Park` / `Comiskey Park` | Merged after you accepted outside knowledge as evidence. Every `Comiskey Park` mention describes the demolished 1910 park, and the two share one stored point. The survivor is `Old Comiskey Park` (it has a street address and cannot be mistaken for the current park); `Comiskey Park` stays as a trusted alias. |
| `U.S. Cellular Field` | Merged into `Rate Field` on the same basis. It is the current park's 2003 to 2015 name; the record had no point or address. |

Renames need an evidence package: the mention text and dates for each name, so that a person or agent
can see a name change in the text.

### 9. Data-integrity findings

Found while cleaning; not caused by it.

- **Invalid mention state.** 4 location mentions are marked `pending` while still pointing at a
  canonical. The relink code refuses that state, which is right, but it fails the whole group:
  the two `Monona Bay` canonicals cannot merge until the mention is fixed. A cleanup check should
  report these rows instead of leaving them to surface as merge failures.
- **Canonicals with no mentions.** About 4,100 of 13,700 place canonicals have no linked mention.
  Some are expected (seeded geography, curated entries), but others are ingest leftovers: 37 of the
  40 identical `Griffin Museum of Science and Industry` canonicals had none. A separate check for
  "empty canonicals with no curated data" is worth specifying; this work did not remove them.
- **Group-level failure handling.** A failed group rolls back cleanly (each group is its own
  transaction). The apply step needs to report it by group, with the reason, so a caller can
  retry or escalate.

### 10. Letting models adjudicate

Rules kept failing on the same shape of case: one place, many names. `Stevenson High School` and
`Adlai E. Stevenson High School`; the John Hancock tower under six labels and street addresses;
`Acero Tamayo` in five spellings. Each needs a threshold that would also merge things that must stay
apart (the 6-character added-words limit exists because of `Navy Pier` and `Spirit of Navy Pier`).
The direction taken: stop trying to make the first filter precise. Make it generous, and let models
decide.

**Candidate groups (recall first).** `build_adjudication_packets.py` groups place and address
canonicals by loose signals: the same normalized street address, points within 400 m with a
similar name, a shared rare word (a word in 25 or fewer canonicals, 8 or fewer for a stronger
signal), or identical labels up to 3 km apart. It produced 1,934 groups. Groups held back earlier
for a person's decision are left out.

**Evidence packet per group.** Each member's label, kind, stored address and point, mention count, up to
three short snippets from articles, whether it has curated metadata, the pairwise distances, and why it
was grouped.

**Two independent readers.** Every group went to two different models, each working alone from a
written rubric (`adjudication/RUBRIC.md`): same place means the same real-world thing, not a venue
inside it, a tenant at its address, a neighbor, or a different branch. Each returns the clusters it
would merge, any part-of relationships, a confidence, and whether it relied on outside knowledge.
Low-confidence merges become no merge.

**Consensus.** Two records merge only if both readers put them in the same cluster. Anything a
reader marked low or unsure is held. A pilot of 35 groups ended with the readers agreeing on 31;
all 19 agreed merges were right when read by hand, and the 4 disagreements stayed apart.

**Full run.**

| Measure | Value |
|---|---|
| Candidate groups adjudicated | 1,934, in 20 chunks, 40 reader runs |
| Groups with no merge from either reader | 702 |
| Groups held (disagreement or low confidence) | 72 |
| Groups with agreed merges | 1,160, containing 1,317 clusters |
| Applied | 1,311 groups, 1,770 canonicals merged away |
| Clusters where both readers named identical members | 1,097 of 1,160 groups; the rest were overlaps where only the agreed subset merged |
| Held for a person | 3 groups where one name sits kilometres apart (`Immaculate Conception Church`, `Urban Prep Englewood Campus`, `O'Hare Terminal 5`): which location is right decides the survivor |

**What it caught that rules did not.** School name variants with invented first names
(`Edward H. Clark`, `George Rogers Clark` and `Michele Clark High School`, all at one address and
point), a school renamed or renumbered across years (`Goode STEM Academy` under eight labels), English
and Spanish names (`La Villita Community Church` / `Iglesia Comunitaria de La Villita`), a building and
the programs inside it known by one street address, and address records that are named places
(`3120 S. Halsted St.` / `Deering Police Station` / `9th District Police Station`).

**Reading what was agreed.** The 36 largest clusters (five or more members) were read by hand. All
were one place; the loosest were the `Clark` school group (shared point, invented given names) and the
immigration check-in office known by six labels. Clusters mixing place and address records (13) follow
the address-to-place rule from [section 6](#6-a-second-cleanup-mode-addresses-that-are-named-places).
Survivors were chosen the same way as before, with a stored shape first.

**Caveats.**

- Agreement between two models is evidence, not proof. Both can share a gap, such as a school's
  campus move. The merge is reversible from the backup and ledger, not from the product.
- The snippets are short, and the readers' reasons cite only them and outside knowledge. A product
  version should keep each reader's reason on the merge record so a person can audit it.
- The candidate groups come from one snapshot. Anything ingest has minted since needs another run.
- A survivor with a stored JSON `null` shape counted as having a shape in SQL but not in the apply
  check. Two groups were refused until the planner treated JSON `null` as missing.

**Product implication.** The merge endpoint should accept a decision with its sources: evidence,
readers' verdicts, and confidence, so a model-adjudicated merge reads the same as a rule-based one in
activity.

### 11. What the duplicate finder still lists, in solvable groups

After the model passes (round 1 over recall-oriented groups, then Vatican City, invented state
suffixes, and a second round that grouped places, natural features, and neighborhoods by primary
name), the finder still listed 178 clusters. They fell into six groups. Most were not duplicates, and
three tools cleared them.

| # | Group | Clusters | What it is | Tool that cleared it |
|---|-------|----------|------------|----------------------|
| 1 | Region estimates shadowing a real record | 76 | Ingest minted a vague-area record (`(region estimate)`) next to a real neighborhood, city, or state of the same name (`Loop`, `Brooklyn`, `Morelos`), or several of them (`CTA Brown Line` ×7) | **Fold-in rule.** Region estimates are kept as a concept, but the real record wins: estimates fold into it, and estimates of one region with no real record merge together. 74 groups, 79 records |
| 2 | Same name, different place at admin level | 37 | `Oxford, OH` / `Oxford, England`; a city versus a country (`Belgium, IL`); a bare name whose address is in another country | **Dismissal rule** on the address's country or state, and a country paired with a US city or state. 40 pairs |
| 3 | Kind conflicts | 35 | A neighborhood and the park of the same name, or a city and a school named for it | **Model readers**, with a rubric that keeps neighborhoods apart from the parks and schools named for them. Housing developments and districts recorded as both kinds (`Lake Meadows`, `The 78`, `Brooklyn`) merged; parks, village halls, and schools were dismissed |
| 4 | Same name, different towns (places) | 21 | `Stockton High School` in CA and IL; chain branches | **Dismissal rule**: different states, or different towns more than 10 km apart, or street addresses more than 3 km apart with linked mentions. 17 pairs, plus model dismissals |
| 5 | Same institution, several addresses | 8 | A theatre or venue recorded at two addresses | **Model readers**: `TimeLine Theatre` and `Avondale Music Hall` merged |
| 6 | A natural feature blocked by bad data | 1 | `Monona Bay` | Not cleared: an invalid mention blocks the merge |

A fifth kind of fix was also needed: a state that exists once but has a copy geocoded to another
place (`Louisiana` in Illinois, `Oregon`, `Pennsylvania`, `Bihar`). Those merged into the correct
record (5 records).

**Result.** The finder fell from 178 clusters to 18 after the fold-ins, dismissals, a third reader
round over 59 groups (14 merges, 34 reader-based dismissals), and the wrong-address merges. Canonicals
went from 17,171 to 16,919 over this stretch. The 18 left need a person: ambiguous names (`Carolina`,
`Puerto Rico`, `Vatican City`, `Nueva York`), `Monona Bay`, and 13 groups where a reader answered
`unsure` or the two readers disagreed (`Homan Square`, `Palmer Square`, `Pizza Lobo`, `Green City
Market`, and a few schools).

**What this says about the product.** Group 1 and the dismissal rules (groups 2 and 4) are
deterministic, so the finder should apply them itself instead of leaving them for a person. Groups 3
and 5 need the evidence-and-readers loop. A cleanup agent needs three tools: fold or merge with
evidence, dismiss with a reason, and hold for a person.

## Product spec

### Principles

1. **Detection and decision are separate from application.** An agent proposes; the server
   re-validates and applies.
2. **Evidence travels with every proposal.** Agents should not need SQL or a shell to judge a pair.
3. **Safe by default.** Dry run is the default, caps are enforced server-side, and anything the
   server would not auto-merge needs an explicit decision.
4. **Every action is attributable and reversible by a person.** Who, which run, what evidence.
5. **Same behavior for people and agents.** The UI merge gets the same fixes.

### Capabilities

| # | Capability | Notes |
|---|---|---|
| 1 | **Duplicate proposals** | Return groups with a recommended survivor, per-pair evidence, verdict (`auto_safe`, `needs_review`, `keep_separate`), reasons, and a fingerprint of the members' current state |
| 2 | **Compare two canonicals** | The [evidence package](#evidence-package) for any pair, including pairs no check surfaced |
| 3 | **Apply merges** | Batch of proposals; `dry_run`; per-group result; server rejects if the fingerprint changed |
| 4 | **Keep separate** | Record "these are different places" so they stop resurfacing (extends the existing dismissal) |
| 5 | **Fix place kind** | Change a canonical's kind as part of a proposal, then merge |
| 6 | **Field-level survivor choice** | Take label, kind, geography from different members |
| 7 | **Run history** | List an agent run's actions and outcomes; later, revert support |
| 8 | **Limits** | Per-run action cap, per-call batch cap, and a required run identifier |

### Evidence package

Everything the planner computed, plus what an agent needs to settle "unsure" pairs:

- label, kind, address, status, slug, created date for each side
- geography present on each side, distance between them, whether the shapes are near-identical
- label diff: which qualifiers each side adds, and whether they conflict
- linked mention counts, curated vs machine aliases, metadata, open connections
- geography of the **linked mentions** on each side (the likeliest way to settle pairs where the
  canonicals themselves have no geography)
- a few mention snippets per side with article and project references
- why this was or was not an automatic merge

### Merge semantics (applies to UI and API)

Fixes to the shared merge operation, from the gaps above:

1. Rewire connections **before** relinking mentions, or stop pruning from closing connections that
   the merge is about to move.
2. Carry **all** source aliases and the source's own label to the survivor without overwriting any
   survivor alias; mark them as reviewed-merge provenance.
3. Refuse a merge that would drop geography or metadata unless the caller says which side wins, or
   move them.
4. Accept an actor (`user` / `agent`), a run identifier, and the evidence verdict, and write them to
   the activity row.
5. Make semantic reindex part of the operation, or return the affected articles so every caller
   handles it the same way.
6. Persist `merged_into` for old IDs so pull-based clients can follow it.
7. Remove the redundant delete after pruning.

### Endpoint sketch

Under the existing cleanup namespace; names are placeholders.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/{stylebook}/cleanup/duplicate-places/proposals` | Capability 1; filter by verdict, project, kind; paginated |
| `GET` | `/{stylebook}/cleanup/canonical-locations/{id}/compare/{other_id}` | Capability 2 |
| `POST` | `/{stylebook}/cleanup/merge-proposals/apply` | Capability 3; body has `run_id`, `dry_run`, and proposals with fingerprints and optional field choices |
| `POST` | `/{stylebook}/cleanup/keep-separate` | Capability 4 |
| `GET` | `/{stylebook}/cleanup/agent-runs/{run_id}` | Capability 7 |

Authentication: the cleanup routes authenticate browser sessions and the internal service token
(service-token access to the edit-permission check was not exercised). External agents will need a
scoped credential for this namespace; that decision is open (see below).

### Prevention

- Serialize "create a new place" per Stylebook and normalized name, and re-check for an existing
  match once inside the lock. A unique index is not enough: legitimate same-name places exist.
- Reuse the planner's pair classification as the commit gate for exact-name matches that currently
  defer, so clear cases link instead of queuing.

### Detection

- Fold accents, apostrophes, hyphens, slashes, and spacing in the finder's primary-name join.
- Move pair classification into the quality package so the check, the UI, and the API return the
  same verdict. The check hub should show "safe to merge" and "needs a decision" counts.

## Phases

1. **Shared merge fixes and tests** (items 1–7 above). Smallest change with the largest safety win;
   benefits the UI today.
2. **Finder folding and shared classification**, then the proposals and compare endpoints
   (read-only).
3. **Apply endpoint** with dry run, fingerprints, caps, agent attribution, and run history.
4. **Ingest serialization** and gate reuse; measure new duplicates per run.
5. **Same pattern for people and organizations**, and for the other cleanup classes (mismatched
   links, questionable canonicals, missing geography). The place case is the template.

## Validation

- Unit tests for each verdict, including `Brownsville, TN/TX`, `Kennedy-King College` /
  `U Building`, and `BP` far apart.
- Merge tests: connections stay open, aliases and label carried, geography never lost, metadata
  refused or moved, activity attributed.
- Replay the case study on a restored snapshot; the third planner run must propose nothing.
- Lookup test: every merged-away label resolves to the survivor through label or trusted alias.
- After ingest serialization: concurrent identical places in one run create one canonical.

## Open questions

1. **Credentials for external agents.** Project API keys are rejected outside `/public/v1`. Does the
   cleanup namespace get a scoped agent credential, or do these endpoints move under a public path
   (which also triggers the API Playground update rule)?
2. **How much should `auto_safe` merge without a person?** The case study used a deliberately strict
   rule. A per-Stylebook setting (suggest only / auto-apply safe) may be right.
3. **Undo.** Reverting a merge means recreating the source and relinking its mentions, aliases, and
   connections. Is the run history plus a backup enough, or is a real revert required?
4. **Survivor labels.** Should a merge prefer the better-spelled label even when the other record
   has more data? This needs field-level choice.
5. **Reindex cost.** Merges queue embedding jobs. Should an apply run batch and cap them?
6. **Scope beyond places.** People and organizations have different identity rules; the evidence
   model will differ (affiliation, titles, nicknames).

## What was and was not exercised

- Merges were applied through the shared library function the cleanup endpoint calls, directly
  against the local database, with a backup taken immediately before each pass. The HTTP endpoints
  and their authentication were not exercised.
- Semantic reindex was **not** queued for the moved mentions (about 3,150); those articles' semantic data may
  be stale until it is.
- Tiers C and D (619 groups) were reviewed by reading every proposed group, not by a second
  independent check. The reading removed about fifteen classes of false positive (see the table
  under tier C), and several were found only after a first proposal looked plausible. The first
  proposal for pass 6 had about 500 groups; the applied one had 414. Treat the merged groups as
  high-confidence, not verified, and expect the guard list to keep growing.
- The planner and the verification script both had bugs found only by running them against the
  data (a verification that ignored chained merges; a candidate query that needed a point on both
  sides). A product version needs its own tests built from the cases in this document.
- Passes 1 and 2 ran before the stricter extra-qualifier rule existed. Re-checking those 1,115
  merges against it found 10 that would now be held. Seven look fine (an intersection, a street
  name, a campus in the same town). Three deserve a person's look:
  `Black Panther Party Heritage Trail, Site 2`, `La Rabida Children's Hospital, Child Life
  Pavilion`, and `Tootsie Roll factory, Ford City Mall`. Each can be reversed from the run ledger and
  backup. This is a measured residual risk, not a verified error rate.
- The planner and apply scripts were prototypes in a scratch directory and are not committed.
