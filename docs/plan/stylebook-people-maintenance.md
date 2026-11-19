# Stylebook maintenance: people (plan)

**Status:** Planning only; nothing here is a runtime contract. Starts the next category in
[`stylebook-maintenance-program.md`](stylebook-maintenance-program.md), using the playbook and the places
lessons in [`stylebook-places-requirements.md`](stylebook-places-requirements.md).

The near-duplicate pass has been run (2026-11-17); see [Results of the near-duplicate pass](#results-of-the-near-duplicate-pass).
The closing lessons, requirements by spec and product decisions are in
[`stylebook-people-requirements.md`](stylebook-people-requirements.md). The candidate queue (Phase 5) has also been run; see
[Results of the candidate queue pass](#results-of-the-candidate-queue-pass). Taxonomy is not started. The survey numbers below are a read-only survey of `cpm-stylebook` (`STYLEBOOK_ID = 14`) taken
before any cleanup, to decide how to start.

## Why people are not places

| Places | People |
| --- | --- |
| A geocoder can referee a disagreement | There is no outside referee; the only evidence is names, roles, organizations, and article text |
| A wrong merge moves a pin | A wrong merge attributes one person's actions to another (a crime, a quote, a donation) |
| Single mentions are mostly noise | Single mentions are normal; most people appear once |
| Same name usually means same place | Same name usually means different people (`Brian Johnson`) |
| Wrong shape is visible on a map | Wrong identity is invisible until someone complains |

So the starting rule is the reverse of places: **when unsure, keep records apart and say so.** A missed
duplicate costs a duplicate row; a wrong merge costs trust. Merging people is never fully unattended until
an audit has measured an error rate.

## What the survey found

**Catalog.** 52,671 active person canonicals; 17,571 are marked public figures. All were created in one
bulk load on 2026-11-01. 40,419 have a title and 29,197 have an affiliation. 536 labels are one word.
Person types are mostly athlete (9,589), artist or entertainer (9,277), and community member (8,327);
3,188 are `other` or `unknown`, and 31 use a stray `Politician` outside the taxonomy.

**Evidence behind the canonicals.** 28,941 canonicals have one linked mention. 18,468 have none (to verify:
bulk-load records that no mention has reached yet, or links lost in a past merge). Of 58,433 aliases,
58,106 were written by ingest, which the identity rules do not trust. Only about 330 aliases are editorial
or cleanup-written, so the alias rescue that helped places will rarely apply to people at first.

**Candidate queue.** 2,187 pending, 927 waived, 42,118 linked. Reasons on pending items overlap:
`first_name_only` 885, `ambiguous_person_canonical_match` 758, model adjudication said no match 753,
`pseudonym` 325, `stage_name_or_alias` 219, link-commit veto 8. 1,042 pending names are a single word.
By type: community member 1,049, artist or entertainer 525, unknown 232, athlete 93, elected official 52.

**Duplicates.** 1,496 labels are shared by more than one canonical; 698 share label and affiliation, which
is the likely-real-duplicate pile. The existing `duplicate-people` check returned 1,717 clusters in its one
run. Samples show both problems in the same list:

- `Austin Reed` x5, all Chicago Bears: probable duplicates.
- `Caroline Glennon-Goodman` x5, mostly Circuit Court of Cook County: probable duplicates.
- `Brian Johnson` x6 (AC/DC, 49ers, Evanston commission, a school, a group): different people.
- `Mike Brown` x5 (Bears, Bengals, Knicks, a school, an alliance): different people.

**Tooling that exists.** Checks `duplicate-people`, `mismatched-people`, and
`questionable-person-canonicals`; person merge (`merge_person_canonical_into`); a person review module that
already waives children, animals, and non-persons at extraction and flags first-name-only, pseudonyms, and
stage names; mismatch helpers with nickname and initials handling. Dismissals exist but none are recorded
for people.

## Goal

Make the people catalog trustworthy for editorial use, with automation that is conservative by default:

1. No wrong merges that attribute one person's record to another.
2. Duplicates of the same person folded when evidence is strong, with reasons stored.
3. The candidate queue small and made of real decisions.
4. Sensitive categories (children, crime and justice subjects, community members) never handled
   unattended beyond keeping them apart.

## Principles

1. **Distinct until shown otherwise.** Same name plus no shared affiliation, title, or story context is two
   people.
2. **Evidence must name the person.** Affiliation, title, role, and co-mentioned entities count. Name
   similarity alone never counts.
3. **Two readers plus hard vetoes.** A reader agreement merges only if no veto applies. Vetoes: different
   given or family name, different generational suffix, different organization with no overlap in role or
   time, child or sensitive type.
4. **Waive and hold are first-class.** First-name-only and pseudonym candidates are waived or held with a
   reason, not guessed.
5. **Undoable.** Every merge keeps a before-state that allows an undo; person merges move mentions,
   aliases, and connections.
6. **Review after the fact, with lists.** Same as places: named lists for every autonomous decision.

## Phases

### Phase 0: measure (read-only, no changes)

- Verify the 18,468 canonicals with no linked mentions: where they came from, whether they should exist.
- Split the 1,496 duplicate-label groups into: same label and same affiliation, same label with
  compatible affiliations (a team and its league, a city and its office), and clearly different people.
- Profile the 2,187 pending by reason, type, and mention count; find cohorts the review path skips.
- Measure how much of `mismatched-people` and `questionable-person-canonicals` is caused by our own
  earlier merges or by untrusted ingest aliases (places lesson 8).
- Sample 100 current links for an error baseline.
- Output: a findings section here, and a labeled seed set.

### Phase 1: scope rules (decide with the owner, no changes)

Agree these before any reader runs, because they drove the biggest drops for places:

1. **Who is worth a record.** Public figures vs community members vs private people; mentioned once vs
   more. For places, single mentions were waived by rule.
2. **First names and single-word names.** Waive by default, or keep a record when the story gives a full
   identity elsewhere.
3. **Sensitive types.** Children, victims, suspects, defendants. Keep apart; no AI merges; list for a person.
4. **Roles and group labels** (`Chicago Mayor`, `Police Superintendent`): not a person record; waive or link
   to a named holder only with a dated source.
5. **Name forms.** Titles, suffixes, nicknames, initials, transliteration, married and professional names.
6. **Taxonomy.** Fix `Politician` and decide what `other` and `unknown` should become.

### Phase 2: rules and ingest (deterministic, dry run first)

- Fold exact variants: titles stripped, suffix kept, initials, accents, nickname map, dotted initials.
- Group by name plus affiliation; exact same name, title, and affiliation is a merge candidate with no model.
- Same name and different affiliation: dismiss by rule unless an alias or shared mention links them.
- Waive first-name-only and role labels by rule per Phase 1.
- Ingest: do not create a new canonical for a single-word name; resolve a known nickname before creating;
  stop minting a new record when name, title, and affiliation match an existing one.
- Fix the type taxonomy.

### Phase 3: readers and referees

- Packet per cluster: names and aliases, titles, affiliations, types, linked article headlines and
  snippets, co-mentioned organizations and places, dates.
- Two readers (Claude and GPT) with a people rubric: same person, different people, `unsure`. Same
  agreement and tie-break discipline as places, with `unsure` winning ties.
- Referee: the article text itself. A same-article co-mention of two names (`Brian Johnson` and `Johnson`)
  can settle a variant; an outside geocoder does not apply.
- Hard vetoes (Principle 3) applied after readers, never overridden by them.

### Phase 4: apply

- Dry run, targeted backup (`stylebook_person_canonical`, `stylebook_person_alias`, and the substrate
  link column), apply through `merge_person_canonical_into` with per-item rollback and a ledger.
- Start with the strongest tier only (same name, same affiliation, both readers agree). Review the list
  before opening further tiers.
- Merges only at first; no automatic creates or waives on sensitive types.

### Phase 5: queue

- Link candidates to existing canonicals by exact name plus affiliation, then by reader agreement.
- Waive first-name-only and pseudonym items per Phase 1 with reason codes.
- Leave sensitive and ambiguous items for a person, in a named list.

### Phase 6: write down

- Update the program doc: lessons, decisions, and which spec each requirement changes.
- Write the people requirements by spec (A through F), as done for places.

## Results of the near-duplicate pass

Done in this order, with the playbook from the program doc ([Category 5](stylebook-maintenance-program.md#category-5-near-duplicate-people)):

| Step | Result |
| --- | --- |
| Phase 0 recluster | 1,574 exact-name groups; the finder missed none. 591 clusters had no zero-mention member, 987 had one |
| Tier 1 rule folds | 649 groups, 673 records folded (same name, title, affiliation, type; no sensitive member) |
| Rule triage of the rest | 460 pairs dismissed by rule; 775 sent to readers |
| Readers | A (Claude) judged 775; B (GPT) judged 341 same/high plus a blind 70 of A's different/high |
| Consensus | 301 groups, 307 records merged; 140 reader dismissals; 318 pairs held |
| Applied | 52,671 to 51,691 active people; 586 dismissals recorded (14 skipped, member already merged) |
| Majority round on held pairs | B read 294 pairs, a third model read the 134 where A and B split: 98 dismissed, 16 merged, 172 no majority. Final: 51,675 active people, 682 dismissals, 174 held clusters plus 130 sensitive |
| Probe | 179 nickname pairs, 54 compound surnames, 75 dropped middle names, and smaller gaps the finder cannot see |
| Name-variant round (after the finder change) | The finder now surfaces 148 nickname, middle-name and compound-surname pairs and 74 quoted-nickname or exact-name pairs that no round had seen. Two readers judged all 222: 153 agreed same (144 groups merged, 150 records folded, 1 group held by hand), 37 agreed different (32 recorded, 5 already merged), 32 held. Active people 52,226 to 52,076; mentions unchanged (338 before and after); 714 dismissals; 340 live clusters (held plus sensitive) |
| Sensitive pairs (D20) | 175 held pairs that involve a crime / justice type, two readers each: 49 agreed different (dismissed), 71 agreed same (64 merge groups, 68 records folded after the owner approved all 64), 55 held (3 of them a missing second verdict). Mixed types resolved to the person's standing role in 15 groups; 1 group (a lone "other" against crime / justice) kept crime / justice. Active people 52,076 to 52,008; mentions unchanged (142); 763 dismissals; 252 live clusters |
| Spelling-slip round | The finder did not compare names one letter apart (`Shepshu Aakhu` and `Shepsu Aakhu`): they shared no blocking key. Probe: 789 such pairs, of which about 330 share an organization, a title, or a person type. The finder now lists a one-letter pair when one of those agrees. Two readers judged the 318 new non-sensitive pairs: 295 agreed same (286 groups merged, 293 records folded), 6 agreed different (George Carlin and George Catlin, Betty Davis and Bette Davis, Greg Janes and Greg Jones), 17 held. Active people 52,008 to 51,715; mentions unchanged (650); 769 dismissals |
| Spelling slips involving a crime / justice type (D20) | 12 more pairs: 1 agreed different (dismissed), 7 agreed same (merged after the owner approved all 7), 4 held. Active people 51,715 to 51,708; mentions unchanged (15); 770 dismissals; 271 live clusters |
| Final full-queue adjudication | Two blinded readers and a senior judge reviewed all 295 remaining live edges. Person-specific veto and component checks approved 94 merge groups covering 100 sources; 190 surviving pairs were dismissed and two mapped decisions resolved through post-merge state. Active people 51,708 to 51,608; 42,820 linked substrate people, 120,713 mentions and 440,718 occurrences unchanged; 960 dismissals; zero live clusters |

Integrity: linked mentions were identical before and after every group, no mention points at a removed
person, no connection was left on a removed person or closed by a merge, and semantic reindex jobs were
queued (206 for the rule folds, 562 for reader merges). Backups: `backup/people_tier1_*.dump` and
`backup/people_readers_*.dump` under `tmp/stylebook-agent-cleanup/`; the final pass used a validated
custom-format backup and durable pre/post ledgers before applying any mutation.

**Phase 0 findings that changed the plan.** The survey counted 1,496 shared labels; the 1,717 finder
clusters yielded 950 merge groups (649 by rule, 301 by readers). Zero-mention copies were common inside
clusters (1,126 of 1,717 had at least one) and they carried connections, so they are not inert. The wider question of the 18,468 canonicals with no linked mentions was not
investigated; it is still open.

**Review lists for the owner** (all under `tmp/stylebook-agent-cleanup/people_dupes/`, not committed):

| List | File | Size |
| --- | --- | --- |
| Rule folds where a duplicate had mentions | `tier1_review.jsonl` | 37 groups |
| Reader merges (all) | `review_merges.jsonl` | 301 groups |
| Sensitive clusters, untouched | `tier1_sensitive.jsonl` | 130 clusters |
| Held pairs with the reason | `review_held.jsonl` | 318 pairs |
| Same-name dismissal sample | `review_dismissal_sample.jsonl` | 50 of 503 |
| Finder blind-spot proposals | `blind_spots_people.jsonl` | about 320 pairs, proposals only |

**Lessons worth carrying forward.**

- Hand audits (50 random groups for each tier plus every group where a duplicate had mentions) found no wrong
  merge, but the sample is small; a larger audit is still needed to claim an error rate.
- Reader B agreed with 332 of 341 same/high pairs and with all 70 blind different/high pairs, so one reader
  plus a blind audit is enough for dismissals.
- Evidence that helped readers most: the quote that names the role or organization in the article.
- Job changes (`Carlos Ramirez-Rosa`, alderman then park superintendent) were merged by readers on article
  evidence; the hard veto on different organization plus title held back only 13 groups.

## Results of the candidate queue pass

Pending candidates went from 2,193 to 187. Full account: [Category 6](stylebook-maintenance-program.md#category-6-people-candidate-queue).

| Step | Result |
| --- | --- |
| Rule waives | 721: pseudonyms, children, handles, initials, five named groups, lone first names on private-looking types |
| Relatives with an inferred surname (owner scope, D18) | 568: 173 created (public, professional, or two or more mentions), 395 waived |
| Readers | A (Claude) judged 868; B (GPT) judged A's 602 link and create rows plus a blind 60 of A's waives |
| Consensus (D19) | 384 created, 150 linked, 1 create reused an existing canonical, 182 waived, 151 held |
| Applied | Active people 51,675 to 52,226; no link points at a missing canonical; reindex queued |

**Review lists for the owner** (under `tmp/stylebook-agent-cleanup/people_queue/`, not committed):

| List | File | Size |
| --- | --- | --- |
| Held rows with the reason and both verdicts | `review_held.jsonl` | 151 |
| Reader decisions (creates, links, waives) | `decisions_readers.jsonl` | 717 |
| Rule and relative decisions | `decisions_rules.jsonl`, `decisions_relatives.jsonl` | 721, 568 |
| Sensitive candidates, untouched | (pending, sensitive person types) | 36 |

**Lessons worth carrying forward.**

- Scope rules do most of the work; readers should see only what a rule cannot decide.
- Restrict "first name only" and "initials" rules to private-looking person types, or they waive mononym
  artists and surname-only public figures.
- One high-confidence waive checked by a blind sample is enough (41 of 41 agreed); low- and medium-confidence
  waives split the readers and stay pending.
- The extraction misses relationship titles ("Son", "Wife") with a first name only; created relatives inherit
  those titles, which spec A should stop.

## Requirements by spec

**Moved.** The requirements, updated for everything learned since this list was written (including the
crime / justice rule in D20, which replaces the old PC5), are in
[`stylebook-people-requirements.md`](stylebook-people-requirements.md), together with the product decisions
still to make. The list below is the first version, kept for the history of the near-duplicate pass; do not
build from it.

IDs use a `P` prefix to stay apart from the places IDs (A1 to E5). Evidence is from the near-duplicate pass.

### A. Ingest and canonicalization prevention

| ID | Requirement | Evidence |
| --- | --- | --- |
| PA1 | The shared person merge carries `public_figure` (true wins), fills an empty title and affiliation, and keeps the source's aliases with a trusted merge provenance | A zero-mention source was a public figure; source aliases were all untrusted ingest aliases |
| PA2 | Rewire connections before deleting the source, and de-duplicate edges that collide | 429 of 649 groups had connections on a duplicate; the delete ran before relink |
| PA3 | Do not create a person when name, title, affiliation and type match an existing record; resolve known nicknames first | 649 groups of exact copies |
| PA4 | A not-a-person check at canonical level (bands, groups, role labels) | `The Effigies` in the catalog |
| PA5 | Do not create canonicals for single-word names | 536 one-word labels; 885 `first_name_only` candidates |

### B. Review-queue and finder logic

| ID | Requirement | Evidence |
| --- | --- | --- |
| PB1 | Score title and affiliation in the finder, using containment (`Cook County` inside `Circuit Court of Cook County`) | 87% of pairs were same-name; Tier 1 used these signals |
| PB2 | Block on nicknames (a maintained map) and on compound surnames, dropped middle names, initials and spacing variants. **Done for nicknames, quoted nicknames, middle initials, dropped middle names and compound surnames** (`_person_name_variants.py`): a variant pair is listed only when the affiliation agrees (generic words like "department" ignored), or, for nicknames and middle initials, when both affiliations are empty and the person type matches. Quoted nicknames (`Edward "Eddie" Acevedo`) need no second signal. **Done for one-letter spelling slips** (`spelling` kind): one word differs by one letter (substitution, insertion, deletion or swap; both words at least five letters, same first letter), listed when the organization agrees, or, with both organizations empty, when the title is identical or the person type matches. Blocking keys remove one letter from each long word. Still open: first-initial-only and spacing variants, and slips of two letters | 179, 54, 75, 5 and 2 pairs outside every cluster |
| PB3 | Conflicting middle initials and different organization plus role plus type dismiss a pair by rule | 7 and 265 rule dismissals |
| PB4 | Exclude dismissed pairs from the check's next run, and show a cluster's reason for being listed | The same clusters would reappear |
| PB5 | A `needs a person` state with a reason for sensitive clusters and held pairs | 130 sensitive clusters, 318 held pairs |
| PB6 | Ignore title words and generic labels consistently in blocking | Descriptor in label and single-name labels |

### C. Review with AI

| ID | Requirement | Evidence |
| --- | --- | --- |
| PC1 | A versioned people rubric: same, different, unsure; confidence; article text is untrusted; vetoes applied after readers | `RUBRIC.md` |
| PC2 | Packets carry name-in-text quotes, role in story, titles, affiliations, types, aliases and mentions | Quotes naming the role settled most pairs |
| PC3 | Policy: merge only when two models agree on same with high confidence and no veto; one model's different with high confidence dismisses after a blind audit | 332 of 341 agreed; 70 of 70 audited agreed |
| PC4 | A reader-agreement log: pair, model, verdict, confidence, reason, rubric version | Needed to calibrate |
| PC5 | Sensitive types are never merged or dismissed by an agent | Decision D16 |

### D. Agent API, auth, and undo

| ID | Requirement | Evidence |
| --- | --- | --- |
| PD1 | A merge endpoint that returns the connections, mentions and aliases that will move, with a dry run | Connections moved on most duplicates |
| PD2 | A returned ledger with before-state and an undo that restores the removed record, mentions, aliases and connections | Ledger and backup were the only undo |
| PD3 | A reason code on every dismissal and a way to list and reopen by reason | The dismissal table has no reason |
| PD4 | Record agent, model and rubric version on each decision; activity logged as an agent action | `actor_type="agent"` activity |

### E. Evaluation and operations

| ID | Requirement | Evidence |
| --- | --- | --- |
| PE1 | A random audit of merges and dismissals with a measured error rate before any unattended run | Only small hand audits so far |
| PE2 | Named review lists for rule folds with mentions on a duplicate, reader merges, held pairs and sensitive clusters | The lists above |
| PE3 | Metrics: finder clusters by tier, rule vs reader resolution rate, held rate, zero-mention canonicals | Each was a hidden cost |
| PE4 | Run only on people created or changed since the last run | New people arrive daily |

### F. Category playbook

- Measure the queue and its causes first; the finder's own scoring explained most of the list.
- Fold exact copies by rule before reading anything; readers verify what the rules leave.
- Use one reader on all pairs and a second model on the pairs about to be acted on, plus a blind audit.
- Keep a sensitive-type exclusion list from the start.

## Open questions

1. **Scope.** Who counts as a person worth a record, and is the rule per Stylebook?
2. **Autonomy.** May an unattended agent merge any people, or only after a measured error rate? A lower
   bar for exact name-plus-affiliation matches?
3. **Privacy.** Do crime-and-justice and community-member records need different handling in storage,
   export, and the public API?
4. **Time.** Affiliations and titles change. How are former roles recorded, and does a job change count as
   "different organization"?
5. **The 18,468 canonicals with no linked mentions.** Keep, archive, or remove? Do they cause the
   duplicates?
6. **Organizations.** Many `affiliation` values are organization names. Should person matching call the
   organization catalog's canonical ids instead of strings?
7. **Aliases.** Almost all existing aliases came from ingest and are untrusted. Is there a path to promote
   them, for example by reader agreement?
8. **Evaluation.** What is an acceptable error rate for an unattended merge?

## Risks

- A model reader may agree with itself on a wrong merge. Mitigate with hard vetoes, two different models,
  the strongest tier first, and the audit sample.
- Common names (`John Smith`, `Mike Brown`) dominate cluster lists and burn reader time. Rule them out first.
- Merges of people who changed jobs may look like different organizations; do not dismiss by affiliation
  alone when a title or story context matches.
- Reader packets contain article text, which is untrusted input to an agent that can merge. Keep the
  tools narrow, as in the program doc.
- The duplicate finder's list mixes real duplicates with same-name different people; the first pass should
  re-cluster by name plus affiliation instead of working the existing list.
