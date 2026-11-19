# Stylebook maintenance program (running plan)

**Status:** Living document. Planning only; nothing here is a runtime contract.

This is the working log for turning agent-driven Stylebook cleanup into product: ingest changes,
review-queue changes, an AI review that matches what worked, and an API that an outside agent can
run on a schedule. Add to it as we learn. Move a spec out to its own file when it is ready to build.

Evidence and method for the first category live in
[`stylebook-agent-maintenance.md`](stylebook-agent-maintenance.md) (case study, findings, first
endpoint sketch). This file holds decisions, the spec list, open questions, and the order of work.
Closing requirements for places are in [`stylebook-places-requirements.md`](stylebook-places-requirements.md);
people were planned in [`stylebook-people-maintenance.md`](stylebook-people-maintenance.md) and are closed in
[`stylebook-people-requirements.md`](stylebook-people-requirements.md). Organizations were planned in
[`stylebook-organizations-maintenance.md`](stylebook-organizations-maintenance.md) and closed in
[`stylebook-organizations-requirements.md`](stylebook-organizations-requirements.md). The next
full-year experiment is specified in
[`stylebook-autonomous-year-cleanup.md`](stylebook-autonomous-year-cleanup.md).

## How we work

1. Run a category of cleanup with a coding agent against real data (`cpm-stylebook`).
2. Log what worked, what failed, and which tool was missing (Lessons log below).
3. Decide where each fix belongs using the ladder below, and record it in a spec.
4. Agree the specs before building. Then build in phases, with tests built from the logged cases.
5. Repeat for the next category using the playbook.

## Where a fix belongs (the ladder)

Prefer the earliest rung that can solve it:

1. **Prevent at ingest or canonicalization.** Do not create the bad record.
2. **Deterministic rule.** Safe, explainable, no model (fold, merge, or dismiss by rule).
3. **Review-queue logic.** The finder and its "needs a decision" list.
4. **AI review.** Evidence plus model verdicts, with a hold state.
5. **A person.** Ambiguous names and anything a reader answered `unsure` on.

## Decisions so far

| # | Decision | Date |
|---|----------|------|
| D1 | The outside agent brings its own model. The API serves candidates and evidence and accepts decisions; it does not run the agent's reasoning for it. See [implications](#implications-of-an-outside-agent-with-its-own-model). | 2026-11-17 |
| D2 | Region estimates exist, but the real record wins. Estimates fold into the real record of the same name; estimates of one region with no real record merge together. | 2026-11-16 |
| D3 | Models adjudicate duplicates liberally; initial finder filters should favor recall over precision. | 2026-11-16 |
| D4 | Outside knowledge counts as evidence. Merge renames, address-only records into named places, and the same site recorded under variant names. | 2026-11-16 |
| D5 | A state or place that exists once but has a copy with a wrong address or invented state code is merged into the correct record. | 2026-11-16 |
| D6 | Agent writes go through the existing shared merge and dismissal library functions, not new SQL. | 2026-11-16 |
| D7 | Regions and natural features should be **areas**, not points. A point for either is a defect to repair, not an acceptable shape. | 2026-11-17 |
| D8 | Aim for consistent geometry. The existing rule applies: when a canonical's geometry changes, apply it to the mentions linked to that canonical (`apply_canonical_geometry_to_substrates`). The same rule fixes disagreement between a canonical and its mentions, but only after the canonical itself is judged right. | 2026-11-17 |
| D9 | Missing geometry is acceptable by default. The review queue should surface wrong geometry, not missing geometry. | 2026-11-17 |
| D10 | Scope rules come before readers. Candidate queues are cleared by what is worth a record (home region, mention count, public vs private, chains need an address), then by readers on what remains. | 2026-11-17 |
| D11 | For candidate queues, an unattended agent may apply decisions when two readers agree on verdict, type and label, checks pass, and a dry run, backup and ledger exist; the owner reviews named lists afterward. | 2026-11-17 |
| D12 | A geocode may create or referee but never decides alone: it must pass the acceptance checks in the places requirements (A2). | 2026-11-17 |
| D13 | Next category is people, conservative by default: records stay apart when unsure, and sensitive types are never merged by an agent. See the people plan. | 2026-11-17 |
| D14 | People who share name, title, affiliation and person type are folded by rule with no reader, after a dry run, a backup and a ledger; the owner reviews a list of folds where more than one record had mentions. | 2026-11-17 |
| D15 | Other people merges need two readers from different models to say same with high confidence and no hard veto. One reader's `different` with high confidence dismisses the pair once an audit sample read by the second reader agrees (70 of 70 did). Everything else is held. | 2026-11-17 |
| D16 | Sensitive person types (crime and justice subjects) are never merged or dismissed by an agent; clusters containing one are listed for a person. | 2026-11-17 |
| D17 | For held people pairs, the owner chose a majority vote of three readers (A, B, and a third model when A and B split); a low-confidence verdict counts as unsure; hard vetoes and group-conflict checks still apply. | 2026-11-17 |
| D18 | People candidates: relatives known only by first name plus a relationship get a canonical only if a public figure, a professional, or mentioned two or more times (otherwise waived); stage names link to the existing person when one exists, else public performers are created under the stage name and influencers, honorees and handles are waived; first-name-only with a title or affiliation goes to a reader to try to link, the rest are waived. | 2026-11-17 |
| D19 | For candidates, a link or create needs two readers from different models to agree (same record, or same folded name) with no low confidence; a waive needs one reader's high confidence, checked by a blind sample read by the second reader. Anything else stays pending. Sensitive person types are never touched. | 2026-11-17 |
| D20 | Narrows D16 for held pairs that involve a sensitive person type: two readers who agree the people are different may dismiss the pair (it only hides a suggestion); two readers who agree they are the same may only propose a merge, which the owner approves from a list. An agent still never merges, links or creates a sensitive record on its own. The type reflects a person's role in one story, so a difference in type is not evidence of different people. | 2026-11-17 |
| D21 | Organizations are the next maintenance category. A canonical is a durable acting institution, not a product, platform, event, law, work title, generic group, or place. | 2026-11-18 |
| D22 | Organization hierarchy remains explicit: parent and child institutions, chapters, departments, schools and districts, universities and teams, leagues and teams, and independently acting branches stay apart. Readers may answer `related_but_distinct`; that result is never a merge. | 2026-11-18 |
| D23 | Organization type mismatch is taxonomy evidence, not an identity veto. Exact label and type are not sufficient for an unattended fold; a rule fold needs a second independent signal and no hard veto. Generated acronyms and ingest aliases never decide identity alone. | 2026-11-18 |
| D24 | Brand/platform boundary candidates link only when the mention denotes an existing institution as actor; create only an independently acting organization; otherwise defer or waive with a boundary reason. Products and streaming services do not become organization canonicals by default. | 2026-11-18 |
| D25 | The next full-year experiment uses cohort-triggered guarded autonomy across every candidate and cleanup queue. It permits reversible writes only, treats explained holds as valid, and runs at most three closure iterations. | 2026-11-19 |
| D26 | Freeze ingest and manual edits for that run and take one validated full-database backup before mutation. Quarantine known item conflicts, but abort globally on unexplained drift, evidence loss, or integrity failures. | 2026-11-19 |
| D27 | `GPT-6 Luna` and `GPT-6.1 Terra` read independently, cross-critique disagreements, and must converge without a hard veto before apply. Every merge, unlink, retirement, and high-impact geometry repair receives an adversarial audit. This is an experiment-specific exception to D20 for sensitive people; both readers must be high confidence, and D20 remains the product default pending audit. | 2026-11-19 |
| D28 | Evaluate the run with operation/reference counts, issue and residual rates per 1,000 articles, model behavior, integrity, and incremental model cost. Duplicate rate, link precision, false-merge rate, and residual quality use a clearly labeled model-only holdout, not claimed ground truth. | 2026-11-19 |

## Specs to write

Each spec gets a status and an owner as we go. Order is the intended build order. Requirements from places
(IDs A1-A8, B1-B11, C1-C6, D1-D6, E1-E5) are in [`stylebook-places-requirements.md`](stylebook-places-requirements.md);
requirements from people (IDs PA1-PA11, PB1-PB8, PC1-PC7, PD1-PD6, PE1-PE7) and the product decisions still to
make are in [`stylebook-people-requirements.md`](stylebook-people-requirements.md). Organization evidence and
measured procedure are in [`stylebook-organizations-maintenance.md`](stylebook-organizations-maintenance.md);
closing requirements OA through OF are in
[`stylebook-organizations-requirements.md`](stylebook-organizations-requirements.md).

| Spec | Scope | Status |
|------|-------|--------|
| **A. Ingest and canonicalization prevention** | Stop minting region estimates and "(LLM natural estimate)" copies beside a real record; serialize creation per Stylebook and normalized name; reject invented state suffixes and echoed addresses; fix the pending-with-link race; fold accents, apostrophes, word order | Not started |
| **B. Review-queue and finder logic** | Primary-name blocking and kind-aware edges; dismissal rules (different country or state, country vs same-named city, different towns, far-apart branches); region estimates excluded once folded; mixed-kind clusters; a "needs a person" state with a reason; order by impact | Not started |
| **C. Review with AI** | One rubric and evidence builder shared by the UI button and the API; verdicts with confidence including `unsure`; parts; held groups; stored reasons; merge only on the policy in D1 | Not started |
| **D. Agent API, auth, and undo** | Queue and evidence endpoints, apply and dismiss with preconditions, run history, scoped agent credential, `merged_into`, in-product undo | Not started |
| **E. Evaluation and operations** | Labeled set from our verdicts and human UI decisions; shadow mode; schedule; health metrics; alerts | Not started |
| **F. Category playbook** | Template for the next category (below) | Draft below |

## Implications of an outside agent with its own model

D1 changes the shape of the API and where checks live:

- **Evidence over verdicts.** The server returns candidate groups and evidence packets (labels,
  addresses, points, distances, mention snippets, linked counts, curated data). The agent decides.
- **The server enforces hard guards, not the model's honesty.** Apply endpoints re-check facts: members
  still exist and are unchanged since the evidence was read, no merge across different states or far
  apart (unless a rule allows it), the survivor keeps a shape a source had, kinds are compatible,
  and per-run caps hold. The server cannot verify that two readers were independent, so a
  "two-model consensus" policy has to be the agent's own practice, recorded with the decision.
- **Record the decision's provenance.** Store the agent identity, model name, rubric version, reasons,
  and confidence with each merge and dismissal, so a person can audit and the evaluation set can
  use it.
- **Publish the rubric** as a versioned document the agent can fetch (an MCP resource), so the UI
  button and outside agents judge by the same rules. Keep Chicago-specific wording in
  per-Stylebook configuration.
- **Evidence is untrusted text.** Snippets come from articles. Mark packets as data and keep the
  agent's tools narrow, because an article could try to steer an agent that can merge.
- **Cost is the agent owner's.** The server still needs rate limits, per-run caps, and idempotency keys.

## Category 2: missing or incorrect geography

Review queue: `missing-geometry-locations` (missing shapes, and "Linked place far from catalog").
Measured on `cpm-stylebook`, 2026-11-17.

### What the check measures

A linked mention is flagged when its own geocode is outside the canonical's shape and more than 150 km
from the shape's centroid (`location_geography_issues.py`). It cannot say which side is wrong: the
canonical, the mention's geocode, or the link.

### Findings

1. **Half the catalog was invisible to the check.** 8,641 of 16,912 canonicals had a stored shape
   (`geometry_json`) but no PostGIS `geometry`, all created on 2026-11-13. The check and the public
   location geo-search read the PostGIS column. The one-off rebind script fixed 8,638 (backup
   first). Three polygons that cross the 180th meridian (`Fiji`, `Northern Hemisphere`,
   `Western Hemisphere`) cannot be converted and stay stored-only.
2. **Centroid distance is the wrong measure for areas.** Once the whole catalog is visible, 92
   canonicals are over 20 km from a mention by centroid distance; measured to the edge of the area, 23
   are. Most of the difference is regions, lakes, and rivers (`Lake Michigan`: 210 km by centroid, 45 km
   to the edge).
3. **What the 23 are (first reading, not exhaustive):**
   - The canonical's own shape or address is wrong: `U.S. Virgin Islands` (address in Illinois),
     `Michoacán` (California), `Downtown, Chicago` (shape of `Downtown West Chicago`), `Manhattan, NY`
     (address `Manhattan Park`), `Gaza` region.
   - Mentions disagree about one canonical, or one canonical covers two places: `Peach's Restaurant`
     (four mentions 1,660 km apart), `Legion Park`, `Loyola University Chicago` (the Maywood campus shape
     holds 11 mentions that look like the main campus).
   - A mention's geocode is wrong on a correct link: `Louisiana`.
   - Natural features with weak shapes: `Gulf of Mexico` (point), `Lake Fairfield` (a model's estimate).
   - Some were made visible or worse by our own merges, where the surviving record had the bad shape
     (`Downtown, Chicago`, `Louisiana`). A survivor's shape must be checked before mentions inherit it.
4. **Shape types.** Regions are all polygons already. Natural features: 379 polygons, 21 points, 14 with
   no shape. Places are mostly points, which is fine. Neighborhoods: 8 points, 1 missing.
5. **Missing shapes (171):** 82 countries, 69 places, 14 natural features, 5 cities, 1 neighborhood.

### The solution: a procedure we can repeat

This is what worked on `cpm-stylebook`. Each step names the script that did it (scratch scripts in
`tmp/stylebook-agent-cleanup/`, to be promoted into the repo) and the existing code it relies on.

| Step | What happens | Tool | Guard |
| --- | --- | --- |
| 1. Make everything visible | Every canonical must have its shape in both stored forms (the JSON and the PostGIS column). Rebind the ones that do not. | `scripts/rebind_location_postgis_geometry.py` | Dry run first; backup first |
| 2. Check the reference shapes | Before using state or country shapes to judge others, check them: type, size, and whether most places labeled with that state fall inside it. Georgia, Utah and DC failed (points), which made 105 of 124 first-run flags false. | `geography_audit.py` (state check) | Use polygon references only |
| 3. Audit, read-only | Four tests per canonical: (a) containment, a label ending in a state code has its shape inside that state, with 25 km slack; (b) label versus address, for states and countries; (c) distance from the canonical's edge to each linked mention, over 5 km; (d) the mentions' vote, do the far mentions agree with each other. Region and natural features stored as points or nothing are listed separately as "area needed". Missing shapes are counted, not flagged (D9). | `geography_audit.py` | Read-only transaction |
| 4. Referee with an outside source | For each disagreement, geocode the label and see which side lands near. Allowed answers: canonical right, mention right, unresolved. Require the match to be the named place. | `geography_referee.py` | Unresolved is a valid answer; skip multi-site names |
| 5. Repair the canonical | Replace its shape with the best source: the mentions' agreed shape, a public-domain outline (Census), or a geocode checked to fall inside the expected state. If nothing trustworthy exists, clear the shape. Fold a mis-named duplicate into the real record instead of repairing it. | `fix_geography.py`, `geography_referee_apply.py`, `plan_spanish_states.py` + `apply_merges.py` | Containment check before write; ledger entry with the previous shape |
| 6. Make mentions consistent (D8) | Only after the canonical is judged right, copy its shape to its linked saved places of a comparable type. | `apply_canonical_geometry_to_substrates` | Marks the mention as edited so re-ingest does not undo it |
| 7. Fix side effects | Correct stale addresses; refresh mentions moved by a merge. | `fix_geography_followup.py` | |
| 8. Mark the rest reviewed | Leftovers that need a person or an area source are dismissed, with the reason in this file. Dismissals are Stylebook-wide, not per project. | `dismiss_geography_list.py`, `dismiss_canonical_issue` | Report what was dismissed |

#### Decision rule

| Evidence | Verdict | Action |
| --- | --- | --- |
| Shape outside the state the label names; geocode of the label lands inside | Canonical wrong | Replace shape, then step 6 |
| Address names a different place than the label | Canonical wrong | Fold into the real record if one exists; otherwise fix shape and address |
| Mentions agree with each other and sit where the geocode lands | Canonical wrong | Take the mentions' shape, then step 6 |
| Canonical sits where the geocode lands; a few mentions do not | Mention wrong | Copy canonical shape onto those mentions |
| Geocode finds nothing, or neither side is near | Unresolved | Leave for a person, or clear a clearly wrong shape |
| Label, address, and shape agree and no mention disagrees | Fine | Nothing |

Wrong shapes are cleared rather than guessed; a cleared canonical lands in "missing", which D9 accepts.

#### False positives to build in from the start

- A containment test is only as good as its reference shapes (step 2).
- Two-letter suffixes are ambiguous (`DE`, `CA` are also country codes): skip records whose address names
  a non-US country.
- Name variants (`Türkiye`/`Turkey`, `Curaçao`/`Curacao`, `Russian Federation`/`Russia`): fold accents and
  compare by similarity before calling a contradiction.
- Multi-site names (`Howard Brown Health`) and long features (`Illinois Prairie Path`) cannot have one
  right shape for every mention.

### What to change in existing features

| Where | Change | Spec |
| --- | --- | --- |
| Ingest and canonicalization | Write both stored shape forms together everywhere; find the writer that skipped the PostGIS column on 2026-11-13. Reject a first geocode that falls outside the state or country the label names, since it becomes the canonical's shape. Resolve known foreign-language state names to the real record before geocoding (`Nueva York` landed in California). After any merge, refresh the moved mentions from the survivor. | A |
| "Missing or incorrect geographies" queue | Measure distance to the edge of the area, not the centroid. Add the containment and label-versus-address tests, and verify reference shapes first. Show the reason and the mentions' vote on each row. Do not list missing shapes by default; keep them filterable. Show "area needed" for regions and natural features stored as points. | B |
| "Review with AI" button | Add the outside-geocode referee as evidence beside the two-reader verdict: geocode result, distance to each side, whether the match is the named place. Verdicts: canonical right, mention right, unresolved. | C |
| Agent API | Suspects with evidence (both shapes, distance to edge, containment result, vote, referee result). Actions: set a canonical's shape (with a precondition on the current shape), clear it, copy it to mentions, dismiss with a reason. Server re-checks that the new shape falls inside the expected state before accepting it. | D |
| Evaluation | Labeled set from this run: the 19 canonical fixes, the 24 referee verdicts, and the false positives above. Track the share of flags that are false alarms. | E |
| Category playbook | Add "check the reference data" and "referee with an outside source" as steps (below). | F |

### Status

Done on `cpm-stylebook` (2026-11-17; backups `pre_geofix_*`, `pre_referee_*`; ledger
`geography_ledger.jsonl`):

- Rebound 8,638 canonicals so the check and public location search can see their shapes.
- Audit: 16,912 canonicals, 205 flagged on the first run, 104 after fixing the test, 63 after repairs.
- Merged four Spanish-named states into the real states (aliases kept).
- Set shapes: Georgia, Utah, DC and U.S. Virgin Islands (Census); Michoacán and Veracruz (OpenStreetMap);
  Leavitt Street Inn, Halsted Orange Line station, Lakeview East, Barry Art Museum, Venice (Los Angeles),
  Holmdel (OpenStreetMap, each checked inside its state); Peach's Restaurant (its four mentions).
- Cleared shapes: Bobo, Touch Gift Foundation, Trento NJ. Corrected three stale addresses.
- Referee pass on 46 disagreements: eleven canonicals took the mentions' shape, thirteen kept theirs and
  their far mentions were refreshed; three skipped (multi-site or weak match); 17 unresolved.
- Marked the whole list reviewed (198: 174 missing, 24 far-linked). The 24 include rows that still need a
  person; they can be un-dismissed.

Still open:

- 36 regions and natural features stored as points or nothing (D7); no polygon source yet.
- 17 unresolved venue and school rows, plus `Tuskegee, AL` (a stray place with a Chicago address).
- OpenStreetMap shapes need attribution wherever they are shown (Open Database License). Decide on an
  attribution line, or replace them with a public-domain source.
- Finder, ingest, API and button changes in the table above are specified, not built.

## Category 3: mismatched places

Review queue: `mismatched-locations` ("Potential mismatched places"). Measured on `cpm-stylebook`,
2026-11-17. Direction: treat links as correct unless evidence clearly shows otherwise.

### What the check measures

It lists a place when a linked mention's name does not look like the place's name, using the same
helpers as the link-commit gate. It lists places, one row per canonical, and dismissals key on the place.

### Findings

1. **The list was mostly our own merges.** 260 places and 425 linked mentions were listed. 408 of the
   425 names were already active aliases of the place, but the check only trusted aliases from a short
   list of editorial sources. Aliases written by a cleanup merge (`stylebook_cleanup_merge`, 3,977 on
   this Stylebook) were not on it, so every merge of a renamed or variant place created new flags
   (`Miller Park` into `American Family Field`).
2. **Plain variants were flagged.** Spelling (`Theater`/`Theatre`), accents (`Taquería`), apostrophes,
   `The`, run-together words (`LaSalle`), and a name that is a shorter form of the other (`Raven` /
   `Raven Theatre`). A name rule alone clears 164 of the 425.
3. **Distance separates renames from errors.** 405 of 425 mentions sit within 300 m of the place. A
   different name at the same spot is nearly always a rename. Only about a dozen are over 300 m, and
   four over 2 km (`Dumas Elementary` 17.5 km, `Henry's` 5.9 km, `Fitzgerald's` 2.9 km, `The 606` 2.5
   km). Those are geography problems, not name problems. Caveat: a mention whose shape was copied from
   the place has distance zero by construction.

### Solution so far

- Trust aliases written by a cleanup merge or an approved AI review when checking links
  (`is_location_alias_trusted_for_link_checks`). Pruning protection is unchanged.
- Compare names after folding accents, apostrophes, and spelling variants, in the shared comparison key.
- Hide plain name variants from the list only (`location_names_are_obvious_variants`), with a place-type
  guard; the commit gate does not use it.
- Result: 260 places down to 4: two mentioned by street address (`Hubbard Inn`, `West Chicago Community
  High School`), `Washington, DC` mentioned as `District of Columbia`, and `Fox Chain O'Lakes` mentioned
  as `Chain O' Lakes`.
- Tests: predicates, the trusted-alias rule, and a finder test (cleanup-merge alias rescued, ingest alias
  still flagged). Docs: `docs/development/entities/overview.md`.

### What this means for the specs

| Where | Change | Spec |
| --- | --- | --- |
| Merge | Writing the old name as a trusted alias is part of the merge; document that it is what makes later checks quiet | A |
| Finder | Rules first (aliases, folding, variants); only the remainder goes to a person or a model | B |
| Review with AI | Link-level verdicts (`correct` by default, `wrong`, `unsure`); `correct` saves the name as a trusted alias instead of dismissing the place; `wrong` needs a second reader or a geocode referee before an unlink | C |
| Dismissals | Today they key on the place and hide future mentions; link-level dismissals are needed for this check | B, D |
| Ingest | Apply the same folding when matching, so variants link without creating an alias | A |

### Status

Finder fix applied and tested. Four items remain (two street-address mentions of a named place, two
name variants); the model review has little left to do here, so this category is closer to done than expected. Lesson: before
building a review for a queue, measure what the queue's own rules and our own earlier work contribute.

## Category 4: location candidate review queue

Review queue: location candidates (`/locations/candidates`): mentions with no canonical link yet.
Measured on `cpm-stylebook`, 2026-11-17. Direction: link when the catalog already has the place, create
when it does not, wave off single mentions that are out of area or private, and leave the rest to a person.

### Findings

1. **Many "needs review" items were already settled.** 154 place candidates had an automatic match at 0.93-0.99
   confidence, blocked only by the content-sanity gate on link commit
   (`substrate_canonical_link_blocked_by_content_sanity`). Two independent readers confirmed nearly all of them,
   so the gate was a false positive for plain variants. Owner: spec B.
2. **Most of the queue was places with no location.** About 825 places outside the catalog had no geometry, and
   most were mentioned once. Rule used: outside Illinois, create only with two or more mentions; waive single
   mentions; link when the name equals the label of exactly one place; hold chains (they need a street address).
3. **A geocoder is a cheap creator, not a judge.** Each create needs the result in the expected state or country,
   a result name close to the label, and no point shared with a differently named new place. Without those checks
   wrong matches got through (a school geocoded to another city's street). A second pass with simpler queries found
   45 of 295 held places.
4. **Readers agree most on exact matches and least on what to call the thing.** Streets, districts and cities were
   mostly agreed. Disagreements were over the label (`Ramallah, West Bank` vs `Ramallah, Palestine`), the type
   (`city` vs `region_city` for townships), and small schools.
5. **Similar text is not a duplicate for numbered things.** `Commissioner District 4` and `District 5` look alike
   to a trigram check. Compare the numbers first. Chicago school-board districts need a rule for sub-districts
   (`District 2b`) before a person or reader can link them.
6. **A link can be right while the types disagree.** 11 agreed links were refused because the candidate was
   typed `city` and the match is a region or neighborhood. The type guard is correct for creates but too strict
   for these area types.

### Procedure used

Packets (article context, similar records, adjudication rationale) -> two readers (Claude and GPT, read-only
except one verdict file) -> consensus tiers (`auto_link`, `auto_waive`, `review`, `held`) -> dry-run, backup,
apply through the shared create and link functions with per-item rollback and a ledger with before-state.
Creates additionally need agreed type and label, a geocode that passes the checks above, and no existing
record under the same label with another type. The scratch scripts live under
`tmp/stylebook-agent-cleanup/address_queue/` and are not committed.

### What this means for the specs

| Where | Change | Spec |
| --- | --- | --- |
| Link commit | Do not block high-confidence matches on name similarity when the model's rationale and the geocode agree | B |
| Candidate review | Tiers (auto link, auto waive, review, held), a scope rule for single out-of-area mentions, and a duplicate check that compares numbers | B |
| Review with AI | Create verdicts carry a type and label; require two readers to agree on both | C |
| Agent API | Create a record from a candidate with a type and optional shape; return the ledger for undo | D |
| Ingest | Do not create candidates for chains without a street address | A |

### Status

Queue went from 1,751 to 22 pending; the 22 left are 20 intersections and 2 spans, left alone by decision.
Everything else was resolved in the last pass without a person in the loop, so these decisions need review after
the fact:

- **Geocoding in English.** Many foreign places failed because the geocoder returned local-language names
  (Vatican City, Kyiv). Asking for English names turned most of those into creates.
- **Standalone addresses were a hidden cohort.** About 165 pending addresses had never been read because they
  were outside the packet filter. They were read in a later pass; ties between readers resolved by rule (a named
  place beats a bare address; create versus waive means waive; no location means waive).
- **Hand decisions at the end.** Near-duplicates were linked to the record named in the match; places mentioned
  once with no clear match were waived; places mentioned twice or more with no location were created without a
  shape. Place candidates matching a record of another type (canals, lakes, Pearl Harbor) were linked despite the
  type guard. Wrong geocodes (a Greenland "Library Club", an Australian "Lazy Bones", the wrong Thorp school, a
  Carthage in another city) were stripped before creating.
- **Addresses.** Public or business addresses (event sites, build days, offices) became address records; private
  residences, incidental locations, and one address geocoded to the wrong city were waived.
- **Worth a look.** The odd existing record "Khan Yunis, NY"; Chicago school-board sub-districts sitting next to
  whole-district records; duplicate canonicals such as Willis Tower and Sears Tower.

## Category 5: near-duplicate people

Check: `duplicate-people` (one run, 1,717 clusters over 52,671 active people on `cpm-stylebook`, 2026-11-17).
Direction: fold the same person when evidence is strong, keep records apart when unsure, never touch sensitive
types. Plan and survey: [`stylebook-people-maintenance.md`](stylebook-people-maintenance.md).

### Findings

1. **The finder has full recall on exact names and poor precision.** It missed none of the 1,574 exact-name
   groups, but it scores person type, not title or affiliation, so 87% of its pairs are same-name pairs and many
   are different people (`Brian Johnson` x6).
2. **Most duplicates were obvious.** 649 groups (673 records) shared name, title, affiliation and type, and
   were folded by rule. A hand audit of 50 random groups plus all 37 where a duplicate had mentions found no
   wrong fold.
3. **Duplicates carried connections.** 429 of those 649 groups had connections on a duplicate (1,167 rows,
   962 after de-duplication), so zero-mention copies are not inert.
4. **The shared merge drops information.** It does not carry `public_figure`, title, affiliation or the
   source's aliases; the cleanup script did so before merging.
5. **Rules dismissed more pairs than readers.** After the folds, 1,235 pairs remained outside sensitive
   clusters. Rules dismissed 460 (conflicting middle initials; different organization, role and type;
   different specific types with nothing shared). Readers then judged 775: 341 same/high, 140 different/high,
   94 different/medium, 199 unsure, 1 same/medium.
6. **A second model agreed on the dismissals and almost on the merges.** Reader B read the 341 same/high
   pairs and a blind sample of 70 different/high pairs: 332 of 341 agreed, 6 unsure, 3 different; all 70 of the
   sample agreed different. 301 groups (307 records) merged; a 50-group hand audit found no wrong merge.
7. **The finder cannot see nicknames.** After cleanup a probe found 179 pairs it does not cluster
   (`Tom Dart` and `Thomas Dart`, `Dan Goldman` and `Daniel Goldman`), 68 with the same affiliation. Not all
   are the same person (`Matthew Martin` and `Matt Martin` at different fire departments), so nicknames need
   readers, not a rule. Smaller gaps: 54 compound-surname pairs (`Maggie Daly`, `Maggie Daly Skogsbakken`),
   75 dropped middle names, 5 first-initial-only, 7 single-name labels, 2 spacing variants.

### Procedure used

Snapshot and recluster -> Tier 1 rule folds (dry run, backup, per-group transaction, ledger, activity log,
semantic reindex) -> rule triage of the remainder -> Reader A (Claude) on every pair -> Reader B (GPT) on
Reader A's same/high pairs plus a blind sample of different/high pairs -> consensus with hard vetoes ->
apply through the shared merge and dismissal functions. Scratch scripts and lists are under
`tmp/stylebook-agent-cleanup/people_dupes/` and are not committed.

### What this means for the specs

Requirement IDs (PA through PF) are in the people plan.

| Where | Change | Spec |
| --- | --- | --- |
| Shared person merge | Carry `public_figure`, title, affiliation and trusted aliases; rewire connections before deleting | A |
| Finder | Score title and affiliation; add a nickname and compound-surname key; exclude dismissed pairs | B |
| Review with AI | A people rubric, vetoes applied after readers, reader-agreement log | C |
| Agent API | Merge with a returned ledger and undo; dismissals with a reason code | D |
| Evaluation | Audit sample of merges and dismissals; named review lists | E |

### Status

Active people went from 52,671 to 51,675 (996 records folded: 673 by rule, 307 by two readers, 16 by
majority vote). Linked mentions were unchanged by every merge group (guards held), no mention points at a
removed record, and semantic reindex jobs were queued. 682 dismissals were recorded (586 in the first pass,
96 by majority vote). Left for a person, in named lists:

- **Sensitive clusters, untouched:** 130 clusters (`tier1_sensitive.jsonl`).
- **Held pairs after the majority round:** 186 (172 with no majority, 14 vetoed for a different organization
  and title) plus the group conflicts, in `review_still_held.jsonl`. The first-round list of 318 is
  `review_held.jsonl`. The live finder shows 304 clusters: 130 sensitive and 174 held.
- **Majority-vote round (D17):** Reader B judged the 294 pairs only Reader A had seen; a third model
  (Gemini) judged the 134 where A and B split. Result: 98 pairs dismissed, 16 merged, 172 no majority. Most of
  the no-majority pairs are thin records (a name with a contact line or a single quote). Two merges
  (`Reganne Reardon`, `Matthew Bailey`) rest on a record with the wrong team: two readers called them the same
  player, one called them opposing players. Listed in `review_majority_merges.jsonl`.
- **Reader merges to review:** all 301 in `review_merges.jsonl`; **rule folds to review:** 37 groups in
  `tier1_review.jsonl`.
- **Sample of dismissals:** 50 random same-name dismissals to spot check, in `review_dismissal_sample.jsonl`
  (503 same-name dismissals in total).
- **Not in scope:** the 22 intersections and spans from places; the finder blind-spot pairs
  (`blind_spots_people.jsonl`), which are proposals only.

## Category 6: people candidate queue

Check: pending people candidates on `cpm-stylebook` (2,193 on 2026-11-17, before any cleanup). Direction: waive
what should never be a canonical, link what is already in the catalog, create the rest, and leave unsure or
sensitive items for a person. Plan: [`stylebook-people-maintenance.md`](stylebook-people-maintenance.md), Phase 5.

### Findings

1. **Most of the queue was not people to create.** Of 2,193, 721 fell to deterministic rules: descriptive
   pseudonyms, children, social handles, initials, five named groups, and a lone first name with no title or
   affiliation on a private-looking person type.
2. **The earlier model adjudication said "no match" for 743 candidates, and that was mostly right.** They were
   relatives ("Son", "Wife" plus a first name) and stage names, which a name match cannot link. Few real
   links existed, so rules and readers mostly decided between create and waive.
3. **Relatives with a first name are a scope question, not a matching one.** 568 had a surname inferred
   from the article: 173 were created (public figures, professionals, or two or more mentions), 395 waived.
4. **Rules over-reached until restricted by person type.** The first-name and initials rules waived mononym
   artists (GZA, DMX, Beck) and surname-only public figures (Trump, Putin, Musk); they now apply only to
   community members and unknown types.
5. **Readers repaired labels the extraction got wrong.** Bands typed as artists, surnames labelled as first
   names (Burke, Jenks), and surname-only references to public figures that resolve by title and
   affiliation (Vance, Poles, Welch).
6. **A second reader makes waives safe only at high confidence.** On a blind sample of 60 of Reader A's waives,
   Reader B agreed with all 41 high-confidence ones, but disagreed on 8 of 15 low- and medium-confidence ones.

### Procedure used

Survey (read-only) -> rule waives (dry run, backup, ledger, activity log) -> relatives by owner scope ->
packets of 50 with ranked catalog candidates, article evidence and the extraction note -> Reader A (Claude) on
868 -> Reader B (GPT) on A's 602 link and create rows plus a blind 60 of A's waives -> consensus (D19) ->
hand audit of 45 creates and 25 links -> apply through the shared link and create functions. Scratch scripts
and lists are under `tmp/stylebook-agent-cleanup/people_queue/` and are not committed.

### What this means for the specs

| Where | Change | Spec |
| --- | --- | --- |
| Ingest | Do not queue a relationship plus first name or a bare first name with no title or affiliation; resolve surname-only public figures by title and affiliation | A |
| Person rules | Apply first-name and initials rules by person type; recognize relationship titles | A |
| Review with AI | Packets with ranked catalog candidates and a people rubric; two-reader agreement for link and create | C |
| Agent API | A decision endpoint with reason codes, a ledger and undo | D |

### Status

Pending went from 2,193 to 187. Applied: 721 rule waives, 173 relative creates and 395 relative waives, then
reader decisions on 868 rows: 384 new canonicals, 150 links, 1 create that reused an existing canonical, and 182
waives. Active people went from 51,675 to 52,226. No link points at a missing canonical and semantic reindex
jobs were queued. Left for a person: 151 held rows (84 low- or medium-confidence waives, 49 low-confidence
actions, 10 reader disagreements, 5 label mismatches, 2 whose name already exists in the catalog, 1 link
mismatch) in `review_held.jsonl`, and 36 sensitive rows, untouched.

## Category 7: organizations

Checks: `duplicate-organizations`, `mismatched-organizations`,
`questionable-organization-canonicals`, and the organization candidate queue. Direction: fold real
institutional duplicates without flattening hierarchy, remove wrong entity boundaries without losing
evidence, reconcile type after identity, and close the brand/platform queue under D24. Running plan:
[`stylebook-organizations-maintenance.md`](stylebook-organizations-maintenance.md).

### Baseline

As of 2026-11-18: 30,401 active canonicals; 5,178 duplicate edges in 2,900 clusters; 1,606 repeated labels
(only 222 repeated label/type groups); 10,194 zero-linked canonicals; 2,711 questionable-label prefilter
hits; zero reported name mismatches pending an audit; and 88 brand/platform candidates. Organization rows
participate in 37,876 open connections, so zero linked mentions does not make a row safe to discard.

### Procedure

Measure and label cohorts -> harden merge, finder, recall, dismissal and cached-run behavior -> deterministic
two-signal rules -> two independent readers with `related_but_distinct` -> guarded duplicate waves ->
questionable/boundary and type review -> mismatch audit -> candidate queue -> closing requirements.

No data mutation begins until source aliases and metadata survive merges, external-ID conflicts veto a merge,
and the dry-run ledger can restore every affected field.

## Open questions

1. **Polygons for natural features and regions.** Which source can supply an area for a lake, river, or
   estimated region, and who owns the correction when it is a model's estimate?
2. **Credentials.** Cleanup routes authenticate browser sessions and the internal service token;
   project API keys work only under `/public/v1`. Does the cleanup namespace get a scoped agent
   credential, or do these endpoints move under a public path (which also triggers the API
   Playground update rule)?
3. **Autonomy.** Partly answered for candidate queues by D11. Still open: which actions may an unattended agent
   take alone (rule dismissals, region folds, any merge of people), which need two readers, and which are never
   automatic? Per-Stylebook setting?
4. **Undo.** Is run history plus a backup enough, or does a merge need a real revert (recreate the
   source, relink mentions, aliases, connections)?
5. **Redirects.** Merged-away canonical IDs need a `merged_into` lookup for pull-based clients.
6. **Incremental runs.** What is the watermark: canonicals created or changed since the last run?
7. **Reindex.** About 3,150 moved mentions still have no semantic reindex queued. Does an apply run
   queue it, batch it, or report the affected articles?
8. **Next category.** Organizations are closed apart from the open items in their requirements summary
   (D21-D24), as are locations and people.
9. **Shape sources and attribution.** Census outlines are public domain; OpenStreetMap shapes need
   attribution. Which sources may the agent use, and where does attribution show up?

## Category playbook (draft)

For each category of review:

0. **Measure the queue first.** Count it by cohort and by whether anything has read it, and ask what put each
   item there (a gate, a race, a missing rule, an earlier cleanup). Agree scope rules with the owner (D10)
   before readers run.
1. **Frame.** Define "good" for this category in one paragraph, with examples of correct and wrong.
2. **Find.** Candidate generation tuned for recall. Record misses by looking at what a person finds
   that the finder did not. If the finder compares against reference records (state shapes, country
   names), check those references first.
3. **Rules.** Deterministic fold, merge, and dismiss rules. Run in dry mode and read the lists. Readers verify
   the rules' output; they do not replace it.
4. **Evidence.** One packet format; include what a person would look at.
5. **Readers and referees.** Rubric plus addendum for the category; verdicts with confidence and
   `unsure`. Where an outside source can settle a disagreement (a geocoder for geography), use it as a
   referee that may answer "unresolved".
6. **Apply.** Dry run, backup, apply through the shared function, verify counts and integrity.
7. **Review leftovers.** What is left should be small and need a person; log why.
8. **Write down.** Update this file: lessons, new decisions, spec changes.

## Status: duplicate places in `cpm-stylebook`

As of 2026-11-17:

- Place canonicals went from 18,956 to 16,912 across model-assisted passes, rule-based folds, and some
  merges done by hand in the Stylebook UI.
- The finder list went from 261 clusters at the start of finder-focused work to 12.
- What is left needs a person, mostly ambiguous names and groups the readers marked `unsure`.
- Open data items: semantic reindex for moved mentions and a random audit of agreed merges for an
  error rate. (The geometry rebind and the re-geocoding of contradictory addresses are done; see
  Category 2.)

## Status: near-duplicate people in `cpm-stylebook`

As of 2026-11-17: active people went from 52,671 to 51,675 (673 folded by rule, 307 by two readers, 16 by
majority vote), and 682 pairs were dismissed with reasons in the ledger. A later name-variant round (after
the finder learned nicknames, quoted nicknames, middle names and compound surnames) folded 150 more records
and recorded 32 dismissals. A sensitive-pair round under D20 then dismissed 49 pairs and, after the owner
approved all 64 proposed groups, folded 68 more records. A spelling-slip round (names one letter apart, listed
when organization, title or type agrees) folded 300 more (7 of them crime / justice records the owner
approved) and recorded 7 dismissals; active people are 51,708.
What is left are held pairs and sensitive records that readers could not settle, which need a person. Open data items: a random audit of reader merges for an error rate and the finder
blind-spot pairs. See [Category 5](#category-5-near-duplicate-people).

## Status: people candidate queue in `cpm-stylebook`

As of 2026-11-17: pending candidates went from 2,193 to 187 (557 created, 150 linked, 1,298 waived across
rules, relatives and readers). Active people are 52,226. What is left (151 held, 36 sensitive) needs a person.
See [Category 6](#category-6-people-candidate-queue).

## Lessons log

Newest first. One entry per lesson: what we saw, what it implies, which spec owns it.

- **2026-11-17: a finder can only score pairs it compares, and comparison starts from shared keys.** Names one
  letter apart shared no key, so no score or cap mattered: 789 such pairs were invisible. Giving each long
  word a "one letter removed" key made them comparable. Spelling alone cannot decide (George Carlin and George
  Catlin are two people; Dominique Morrisseau and Morisseau are one), so a second signal is required and two
  readers confirm. Of 318 listed pairs, readers agreed 295 were the same and 6 different. Owner: spec B (PB2).

- **2026-11-17: a person type that describes a role in one story cannot also be a safety rule.** The
  crime / justice type blocked 175 pairs, including the same former House speaker typed two ways and a
  student against the mayor. Two readers settled 120 of them (49 different, 71 same). The type should
  describe the person's standing, with the story role kept per mention. Merged records now keep the standing
  type (D20). Owner: spec A (canonical type) and spec C.
- **2026-11-17: snapshot a record before changing it, not after.** The first apply for sensitive merges set the
  survivor's type before the before-state was saved, so an undo would have restored the wrong type; a check of
  the dry-run ledger caught it. Owner: spec D (undo).
- **2026-11-17: a suffix guard hides real duplicates and real differences alike.** 40 groups have a bare name
  next to a numbered form (Carlton Davis and Carlton Davis III are one person; Henry Ford and Henry Ford II
  are not). A rule cannot decide; the finder would have to list them when title or affiliation agrees. The
  owner deferred this (Pope Leo, XIII and XIV). Owner: spec B.

- **2026-11-17: a variant rule needs a second signal, and "affiliation agrees" must ignore generic words.**
  Our first affiliation test treated "Chicago Fire Department" and "Evanston Fire Department" as the same
  because they share "fire" and "department"; a test caught it. Nickname and middle-initial variants need
  the same organization (or both empty with the same person type); dropped middle names and compound
  surnames need the same organization; a quoted nickname in the label needs nothing more. Two readers then
  agreed on 153 of 222 new pairs. Owner: spec B (PB2).
- **2026-11-17: a finder change surfaces records that earlier rounds could not see, so the review round is
  part of the change.** The same change also surfaced 74 pairs from labels with quoted nicknames or exact
  names created by earlier work. Plan to re-run readers on newly visible pairs. Owner: spec E.

- **2026-11-17: a candidate queue is mostly things that should never become records.** 721 of 2,193 people
  candidates were removed by rules and 395 more by one scope decision; only about a quarter needed a reader.
  Settle scope with the owner first, and apply rules by person type so mononym artists and surname-only
  public figures are not caught. Owner: spec A.
- **2026-11-17: let readers see ranked catalog candidates, not the whole catalog.** With 8 candidates per row
  scored by name, alias, affiliation and title overlap, both readers chose the same record for 150 links and
  agreed on labels for 385 creates. Owner: spec C.

- **2026-11-17: for people, a finder that scores only names is a grouper, not a duplicate detector.** 87% of
  its pairs were same-name pairs; title, affiliation and type separated duplicates from different people
  well enough to fold 673 records by rule and dismiss 460 pairs by rule. Score those signals in the finder.
  Owner: spec B.
- **2026-11-17: a second model's blind audit is what makes one reader's dismissals usable.** Reader B was
  not told which pairs were sampled from Reader A's `different/high`; all 70 matched. This is cheaper than
  two readers on every pair. Keep the audit as a standing check. Owner: specs C, E.
- **2026-11-17: the shared person merge loses data a person would keep.** `public_figure`, title,
  affiliation and the source's aliases were dropped, and the delete can run before connections are
  rewired. Cleanup scripts compensated. Owner: spec A.
- **2026-11-17: nickname pairs hide in plain sight.** 179 pairs (Tom and Thomas Dart) are outside every
  finder cluster, and a rule would be wrong about some (two fire chiefs at different departments). Add
  nicknames to blocking and let readers decide. Owner: spec B.

- **2026-11-17: scope rules clear more queue than any reader.** The largest drops came from deciding what is
  worth a record (single mentions out of area, chains without an address, private residences). Agree these
  with the owner first. Owner: spec B and the playbook.
- **2026-11-17: a cohort outside the packet filter stays invisible.** About 165 pending addresses were never
  read because the filter excluded them. Count the queue by type and "read or not". Owner: spec B.
- **2026-11-17: ask the geocoder for English, and check what comes back.** Local-language display names
  failed region checks; unchecked matches placed a "Library Club" in Greenland. Owner: spec A.
- **2026-11-17: reader ties need rules.** Create versus waive resolves to waive; a named place beats a bare
  address; unlocated means waive. Owner: spec C.

- **2026-11-17: a gate that blocks good matches inflates the queue.** 154 candidates sat in review with a 0.93-0.99
  match only because the content-sanity gate refused to link. Before sending a queue to readers, check why each
  item is in it and whether a gate is the cause. Owner: spec B.
- **2026-11-17: reader agreement on a verdict is not agreement on the record.** Two readers chose "create" and
  still disagreed on the label or type for some items. Check type and label before creating, and compare numbers
  before calling two numbered records duplicates. Owner: spec C.

- **2026-11-17: a cleanup's own side effects can fill the next queue.** The mismatched-places list was 98%
  mentions our merges had folded in, because the check did not trust merge-written aliases. Before
  building an AI review for a queue, measure how much of the queue the previous cleanup created and
  fix the cause. Owner: spec B and the category playbook.

- **2026-11-17: an outside geocode is a good referee when the catalog and its mentions disagree.** Of 43
  disagreements, 26 resolved by geocoding the label and seeing which side was near; about half the time
  the catalog was wrong and the mentions were right. Venue and school names often return nothing, so the
  referee must be allowed to say "unresolved". Require the match to be the named place, not a nearby one
  (a park for a bait shop). Owner: spec B (review-queue logic) and spec D (agent API).
- **2026-11-17: a merge can move a bad shape onto good mentions.** After folding `Hawái` into `Hawaii`,
  the mention that came with it still carried a California shape and Hawaii was flagged. Every merge
  should refresh the moved mentions from the survivor (D8). Owner: spec A.
- **2026-11-17: foreign-language state names geocode to an unrelated US state.** `Nueva York` landed in
  California, `Nuevo México` in Illinois. Ingest should resolve known translations to the real record
  before geocoding. Owner: spec A.

- **2026-11-17: marking a whole list reviewed is Stylebook-wide and hides work.** Clearing the geography
  queue dismissed 198 items, 24 of which still needed a person. Dismissals need a reason and a way to
  list what was dismissed and why, so a person can reopen them. Owner: spec D.
- **2026-11-17: a containment test is only as good as its reference shapes.** Our first audit flagged 124
  records; 105 were false alarms because the Georgia and Utah state records are points. Any rule that
  compares against catalog records must first check those records (type, size, self-consistency: do
  most places labeled with the state fall inside it?). Also treat two-letter suffixes as ambiguous and
  fold accents before comparing names. Owner: spec B (finder) and the category playbook.

- **2026-11-17: a bulk import left half the catalog without a searchable shape.** 8,641 canonicals created
  on one day had `geometry_json` but no PostGIS geometry, so the geography check and public location
  geo-search skipped them. Nothing flagged it. Implies a writer that sets both columns together and a
  health check for json-only rows. Owner: A, E.
- **2026-11-17: judge areas by their edge.** Centroid distance made lakes, rivers, and regions look wrong
  (92 flags, versus 23 by edge). Owner: B.
- **2026-11-17: merges can move a bad shape onto good mentions.** When a fold or merge picks a survivor,
  its shape was not checked against the mentions it received (`Downtown, Chicago`, `Louisiana`). Owner: C, D.

- **2026-11-17: pending status with a link left in place.** Four substrate locations (two
  `Monona Bay`, `North Side, Chicago, IL`, `Southeast Wisconsin`) had a canonical link but a pending
  status, which the merge code refuses. Three `Monona Bay` canonicals were created seconds apart,
  which points to a lost update between parallel ingest workers: one linked the row, another wrote
  only the pending status from a stale copy. Repaired by hand. A fix needs row locking or a
  conditional update when ingest links or defers. Owner: A.
- **2026-11-16: the finder's remaining list was mostly not duplicates.** Of 178 clusters: region-estimate
  shadows 76, same name in different places 37, kind conflicts 35, places only 29 (21 in different
  towns or branches, 8 one institution at several addresses), one blocked natural feature. Rules and three reader rounds cleared them. Owner: B.
- **2026-11-16: grouping by kind hid mixed-kind pairs.** Round 2 blocked by kind, so a neighborhood and
  the park of the same name were never read together. Third round read mixed kinds with a rubric
  that keeps neighborhoods apart from parks and schools. Owner: B, C.
- **2026-11-16: ingest manufactures most duplicates.** Region estimates, natural-feature estimates,
  invented state suffixes, and address echoes created records beside real ones. Owner: A.
- **2026-11-16: two independent readers plus agreement caught what rules missed** (renamed schools,
  translations, one address known by many labels) and held the ambiguous cases. Owner: C, D.
- **2026-11-16: dismissals need a reason.** The finder's dismissal table keeps only the pair; our
  reasons lived in a scratch ledger. Owner: B, D.
