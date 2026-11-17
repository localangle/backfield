# Stylebook maintenance program (running plan)

**Status:** Living document. Planning only; nothing here is a runtime contract.

This is the working log for turning agent-driven Stylebook cleanup into product: ingest changes,
review-queue changes, an AI review that matches what worked, and an API that an outside agent can
run on a schedule. Add to it as we learn. Move a spec out to its own file when it is ready to build.

Evidence and method for the first category live in
[`stylebook-agent-maintenance.md`](stylebook-agent-maintenance.md) (case study, findings, first
endpoint sketch). This file holds decisions, the spec list, open questions, and the order of work.

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

## Specs to write

Each spec gets a status and an owner as we go. Order is the intended build order.

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

## Open questions

1. **Polygons for natural features and regions.** Which source can supply an area for a lake, river, or
   estimated region, and who owns the correction when it is a model's estimate?
2. **Credentials.** Cleanup routes authenticate browser sessions and the internal service token;
   project API keys work only under `/public/v1`. Does the cleanup namespace get a scoped agent
   credential, or do these endpoints move under a public path (which also triggers the API
   Playground update rule)?
3. **Autonomy.** Which actions may an unattended agent take alone (rule dismissals, region folds),
   which need recorded agreement from two readers, and which are never automatic? Per-Stylebook setting?
4. **Undo.** Is run history plus a backup enough, or does a merge need a real revert (recreate the
   source, relink mentions, aliases, connections)?
5. **Redirects.** Merged-away canonical IDs need a `merged_into` lookup for pull-based clients.
6. **Incremental runs.** What is the watermark: canonicals created or changed since the last run?
7. **Reindex.** About 3,150 moved mentions still have no semantic reindex queued. Does an apply run
   queue it, batch it, or report the affected articles?
8. **Next category.** People or organizations? (Locations: duplicates and geography are in progress.)
9. **Shape sources and attribution.** Census outlines are public domain; OpenStreetMap shapes need
   attribution. Which sources may the agent use, and where does attribution show up?

## Category playbook (draft)

For each category of review:

1. **Frame.** Define "good" for this category in one paragraph, with examples of correct and wrong.
2. **Find.** Candidate generation tuned for recall. Record misses by looking at what a person finds
   that the finder did not. If the finder compares against reference records (state shapes, country
   names), check those references first.
3. **Rules.** Deterministic fold, merge, and dismiss rules. Run in dry mode and read the lists.
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

## Lessons log

Newest first. One entry per lesson: what we saw, what it implies, which spec owns it.

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
