# Places: lessons and requirements (closing summary)

**Status:** Planning only; nothing here is a runtime contract. Closes the places work in
[`stylebook-maintenance-program.md`](stylebook-maintenance-program.md). Evidence is in that file's
Category 2, 3 and 4 sections and its lessons log; method is in
[`stylebook-agent-maintenance.md`](stylebook-agent-maintenance.md).

Measured on `cpm-stylebook`, 2026-11-17. Duplicate place canonicals went from 18,956 to 16,912 and the
duplicate finder from 261 clusters to 12. The location candidate queue went from 1,751 to 22 (the 22 are
intersections and spans, left alone by decision).

## What we learned

1. **Prevention beats cleanup.** Ingest minted most of the duplicates and most of the queue: region
   estimates beside real records, invented state suffixes, address echoes, chains with no street address,
   and thousands of single mentions of places far from the coverage area.
2. **A gate can be the cause of the queue.** 154 candidates sat in review with a 0.93-0.99 match only
   because the content-sanity gate refused to link plain name variants.
3. **Two independent readers are a filter, not a judge.** They agree on exact matches and obvious waives
   (most of the queue). They disagree on labels, types, and small institutions. Agreeing on "create" is not
   agreeing on the record.
4. **A geocoder is a cheap creator and a good referee, but never a judge.** It needs checks: region,
   name similarity, matching digits, the right result type, and no point shared by differently named new
   places. Without them it put a "Library Club" in Greenland and a school on another city's street.
5. **Mechanical fixes beat model work.** English place names fixed most foreign failures. Comparing numbers
   before text fixed "District 4 vs 5". An exact label under another type is a link, not a create.
6. **Scope rules matter more than model quality.** Every large drop in the queue came from a rule about what
   is worth a record, not from a better reader.
7. **Cohorts hide behind filters.** About 165 pending addresses were never read because the packet filter
   excluded them. Count the queue by type and by "has anyone read this" before declaring it done.
8. **A cleanup fills the next queue.** Merges wrote aliases that the mismatch check did not trust, and the
   list was 98% our own work. Measure that before building review on top of a queue.
9. **Dismissals and waives need reasons and a way back.** Marking a list reviewed is Stylebook-wide and hid
   24 items that needed a person.

## Operating model (what to automate)

Every automated pass follows the ladder in the program doc. For a candidate queue the tiers were:

| Tier | Meaning | Example |
| --- | --- | --- |
| `auto_link` | Both readers link to the same record, and checks pass | Exact label match; near-duplicate of one record |
| `auto_waive` | Both readers waive, or a scope rule applies | Single out-of-area mention; private residence |
| `review` | Both readers create, with agreed type and label | New street, district, or place with a validated shape |
| `held` | Readers disagree or checks fail | Differing label; geocode in the wrong place |

Apply protocol, always: dry run, targeted backup of the affected tables, apply through the shared create and
link functions with per-item rollback, and a ledger with the before-state. Autonomy was "apply everything,
review after the fact", which was safe because of the ledger and the backups.

## Requirements by spec

Each row says what to build and why. IDs are for cross-reference in specs and tests.

### A. Ingest and canonicalization prevention

| ID | Requirement | Evidence |
| --- | --- | --- |
| A1 | Do not create a review candidate for a chain without a street address; record it as waived with a reason | Chains were held for a street address in the queue |
| A2 | Run the geocode acceptance checks at ingest, not only in cleanup: result in the expected region, result name close to the label, digits equal for numbered roads, result type fits the entity, point not shared by differently named new places | Wrong-city and wrong-country matches in every pass |
| A3 | Ask the geocoder for English names, and resolve known foreign translations (`Nueva York`, `Vatican City`) before geocoding | Local-language names failed region checks; `Nueva York` landed in California |
| A4 | Per-Stylebook scope setting: a home region and a rule for single mentions outside it (defer or waive with reason; create at two mentions) | About 825 no-location places, mostly single mentions |
| A5 | Do not create address candidates for private residences; keep public and business addresses | Vigil and gift-donation addresses were private homes |
| A6 | One writer sets both `geometry_json` and the PostGIS geometry; every merge refreshes moved mentions from the survivor | 8,641 canonicals with no searchable shape; a merge moved a bad shape onto good mentions |
| A7 | Serialize canonical creation per Stylebook and normalized name; use a conditional update when ingest links or defers | Three `Monona Bay` canonicals created seconds apart; pending status with a link left in place |
| A8 | Stop minting region estimates and "(LLM natural estimate)" copies beside a real record; reject invented state suffixes and echoed addresses | Ingest manufactured most duplicates |

### B. Review-queue and finder logic

| ID | Requirement | Evidence |
| --- | --- | --- |
| B1 | Do not block a high-confidence link on name similarity when the model's rationale and the geocode agree; report the gate's veto rate | 154 false vetoes |
| B2 | Queue tiers (`auto_link`, `auto_waive`, `review`, `held`), each with a stored reason | Operating model above |
| B3 | Duplicate checks compare numbers first; numbered records (districts, routes) never fuzzy-match across different numbers | `Commissioner District 4` vs `5` |
| B4 | Type guard strict for creates; for links among area types (city, region, neighborhood, natural feature, district) allow a mismatch with a recorded override | 11 agreed links refused, plus canals, lakes and Pearl Harbor |
| B5 | An exact label under another type is a link candidate, not a create | Quarry lakes, Vatican City, nine such cases |
| B6 | Near-duplicate of one existing record, single mention: link by rule | Capitol Rotunda, Congress Plaza Garden and 25 more |
| B7 | Waives and dismissals carry a reason code, can be listed by reason, and can be reopened | Reasons lived only in a scratch ledger |
| B8 | A shared rule for school-board districts and sub-districts (`District 2b`) | Whole-district and sub-district records coexist |
| B9 | Queue health view: count by type and by "read or not"; flag any cohort the review path skips | 165 unread standalone addresses |
| B10 | Decide a policy for intersections and spans (rule, scope out, or review) | 22 left pending |
| B11 | Judge areas by their edge, not centroid distance; check reference shapes before using them as a test | 92 flags by centroid vs 23 by edge; 105 of 124 false alarms from point-shaped states |

### C. Review with AI

| ID | Requirement | Evidence |
| --- | --- | --- |
| C1 | Verdicts need agreed verdict, type and label from two readers; ties go to rules: a named place beats a bare address, create vs waive means waive, no location means waive | Wave 13 tie-break rules |
| C2 | A create verdict carries type, label, and either a validated shape or an explicit "no shape" | Creates without shape were fine for places with two or more mentions |
| C3 | Packet: article context, similar records, adjudication rationale, and the scope rule | Packets drove most agreement |
| C4 | An `unsure` or `held` state with a reason, never a forced choice | Ambiguous names and unlocatable places |
| C5 | A versioned rubric with the label conventions (`Sheridan Road, Chicago, IL`; `Name Township, County, IL`; neighborhood form only for unique venues; chains labeled with street address) and the venue vs address rules | Label disagreements were the main reader conflict |
| C6 | The geocoder is a referee that may answer "unresolved"; require the match to be the named place, not a nearby one | A park returned for a bait shop |

### D. Agent API, auth, and undo

| ID | Requirement | Evidence |
| --- | --- | --- |
| D1 | Endpoints to create a canonical from a candidate with type and optional shape, link with a recorded override reason, and waive with a reason code | `apply_consensus.py` is the prototype |
| D2 | Dry run, per-item rollback, a returned ledger with before-state, and an undo | Used on every wave |
| D3 | Preconditions: candidate still pending and unchanged since the evidence was read | Parallel ingest races |
| D4 | Record agent, model, rubric version, reasons and confidence with each decision; activity logged as `cleanup_ai` | Audit and evaluation set |
| D5 | Shape source and attribution recorded per canonical | Open question 9 |
| D6 | Per-run caps and idempotency keys | Outside agent with its own model |

### E. Evaluation and operations

| ID | Requirement | Evidence |
| --- | --- | --- |
| E1 | A labeled set from reader agreement and disagreement and from human decisions | Reader conflicts are the hard cases |
| E2 | Named review lists for decisions made without a person: reader disagreements, waived addresses, creates without a shape, type-mismatch links, near-duplicate links | The "after the fact" review the user asked for |
| E3 | Metrics: queue size by type, auto-resolution rate, gate veto rate, create-without-shape rate, geocode rejections by reason, canonicals with JSON-only shape | Each was a hidden problem |
| E4 | Run on a schedule against new candidates only, with a watermark; start in shadow mode | New candidates arrive daily |
| E5 | A random audit of auto-applied decisions to measure error rate | Duplicate merges still have no measured error rate |

### F. Category playbook

The playbook in the program doc gains two steps and a clarification, taken from places:

1. **Measure first.** Count the queue by cohort and by whether anything has read it. Ask what put each item
   there (gate, race, missing rule, previous cleanup).
2. **Agree scope rules with the owner before reading anything.** The biggest drops came from "what is worth a
   record".
3. **Run cheap rungs first**, then readers on what remains. Readers verify the rules' output; they do not
   replace it.

## Open after places

- The 22 intersections and spans (B10).
- Reindex of moved mentions (program doc, open question 7).
- Polygon sources for natural features and regions (open question 1).
- Oddities to look at: `Khan Yunis, NY`, Chicago school-board sub-districts beside whole-district records,
  duplicate Willis Tower and Sears Tower records.
- Specs A through F are still unbuilt; this file is the requirements input.
