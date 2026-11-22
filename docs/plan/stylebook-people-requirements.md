# People: lessons and requirements (closing summary)

**Status:** Planning only; nothing here is a runtime contract. Closes the people work in
[`stylebook-maintenance-program.md`](stylebook-maintenance-program.md) (Categories 5 and 6, decisions
D13 to D20, lessons log). Evidence is in that file and in
[`stylebook-people-maintenance.md`](stylebook-people-maintenance.md); method is in
[`stylebook-agent-maintenance.md`](stylebook-agent-maintenance.md). Places are closed in
[`stylebook-places-requirements.md`](stylebook-places-requirements.md); requirement IDs here use a `P` prefix
(PA1 to PE7) to stay apart from the places IDs.

Measured on `cpm-stylebook` (`STYLEBOOK_ID = 14`), 2026-11-17. Linked mentions were identical before and after
every merge group, so no merge moved a mention to the wrong person by count.

| Measure | Start | Now |
| --- | --- | --- |
| Active people | 52,671 | 51,608 (1,614 records folded; 52,226 after creating from the candidate queue) |
| Duplicate finder clusters | 1,717 | 0 |
| Pending people candidates | 2,193 | 187 (151 held rows, 36 crime / justice rows) |
| Dismissed pairs (reasons kept only in a scratch ledger) | 0 | 960 |

How the 1,514 folds happened: 673 by rule, 307 by two readers, 16 by a three-reader majority, 150 after the
finder learned nicknames, middle names and compound surnames, 68 crime / justice records the owner approved
(D20), 300 one-letter spelling slips (7 of them crime / justice records, owner approved), and 100 records
from the final full-queue adjudication.

The final pass materialized all 295 remaining scored edges, gave each to two blinded readers and a senior
judge, then applied person-specific veto and component checks. It merged 100 source records in 94 groups,
dismissed 190 surviving pairs, and accounted for two post-merge state transitions. The shared person merge
was fixed before apply to preserve source aliases, metadata, standing fields, primary evidence and
connections. All 42,820 linked substrate people, 120,713 mentions and 440,718 occurrences were preserved;
the finder now has zero live edges and zero clusters.

## What we learned

1. **Prevention beats cleanup.** Ingest created 649 groups of exact copies (same name, title, affiliation and
   type) and about 300 typos of names it had already seen. Most duplicate work was undoing ingest.
2. **A finder can only score pairs it compares, and comparison starts from shared keys.** Names one letter
   apart, nicknames, middle names and compound surnames shared no key, so no score ever applied: 789 spelling
   pairs, 179 nickname pairs, 75 dropped middle names and 54 compound surnames were invisible.
3. **A finder that scores only names is a grouper, not a duplicate detector.** 87% of its pairs were
   same-name pairs. Title, affiliation and person type separated duplicates from different people well enough
   to fold 673 records and dismiss 460 pairs by rule.
4. **Every variant rule needs a second signal.** Spelling alone cannot decide (George Carlin and George Catlin
   are two people; Dominique Morrisseau and Morisseau are one). The signal is the same organization, or, with
   no organization, the same title or person type. "Same organization" must ignore generic words, or two fire
   departments in different cities agree.
5. **A finder change surfaces records no earlier round has read, so the review round is part of the change.**
   The variant change surfaced 222 pairs; the spelling change 318 more.
6. **Scope rules clear more queue than any reader.** 721 of 2,193 candidates fell to rules and 395 more to one
   decision about relatives known only by first name. Apply those rules by person type, or they waive
   mononym artists (GZA, DMX) and surname-only public figures (Trump, Putin).
7. **Two readers are a filter, a blind audit makes one reader's dismissals usable.** Reader B agreed on 332 of
   341 merges and on all 70 blind-sampled dismissals. For spelling slips the two agreed on 295 of 318, and
   together they dismissed the real different pairs. One model called almost every pair in some chunks "same"
   (58 of 60); the second model and the vetoes are what made that safe.
8. **A person type that describes a role in one story cannot also be a safety rule.** The crime / justice type
   is assigned from one article (charged, victim, sentenced). The same former House speaker carried it on one
   record and "elected official" on another. The rule blocked 175 pairs; two readers settled 120 of them.
9. **Dismissing and merging are not equally risky for sensitive records.** A dismissal only hides a suggestion;
   a merge attributes one record's story to another. Agents may dismiss on two readers; merges go to a person.
10. **The shared merge must preserve the whole identity record.** It previously dropped `public_figure`,
    title, affiliation and source aliases, and the delete could run before connections were rewired (429 of
    649 groups had connections on a duplicate). The runtime merge now transfers aliases and metadata, fills
    standing fields, preserves primary evidence, resolves standing type and rewires connections before a
    relink can prune the source.
11. **Take the before-state before any change.** A first apply set the merged record's type before the
    before-state was saved, so an undo would have restored the wrong type. A dry-run ledger check caught it.
12. **A suffix guard hides real duplicates and real differences alike.** 40 groups have a bare name beside a
    numbered form: Carlton Davis and Carlton Davis III are one person; Henry Ford and Henry Ford II are not.
    Regnal numbers (Pope Leo XIII, XIV) are never the same person. A rule cannot decide.
13. **Readers should see ranked catalog candidates, not the whole catalog.** With eight scored candidates per
    row, both readers picked the same record for 150 links and agreed on labels for 385 creates.
14. **A candidate queue is mostly things that should never become records,** and the rest are mostly relatives
    and stage names that a name match cannot link.
15. **What stays held is thin records:** a name with one quote, a first name and a role. More reading does
    not help; a person or more evidence does.
16. **Dismissals need a reason and a way back.** The dismissal table stores only the pair; every reason lives
    in a scratch ledger.
17. **Rollback simulation must inspect preservation, not only row counts.** The final dry run caught 15
    source alias requirements and 77 connections that the old merge path would have lost. Exact mention
    totals alone would have missed both defects.

## Operating model (what to automate)

Every automated pass follows the ladder in the program doc. For people pairs the tiers were:

| Tier | Meaning | Example |
| --- | --- | --- |
| `rule_fold` | Same name, title, affiliation and person type; no reader | 649 groups of exact copies |
| `rule_dismiss` | A hard conflict decides it | Conflicting middle initials; different organization, role and type |
| `readers_merge` | Two models say same, neither low confidence, one high, no veto | 295 spelling slips; 153 variants |
| `readers_dismiss` | Two models say different, neither low confidence | George Carlin and George Catlin |
| `needs_approval` | Two models say same, but a record has a crime / justice type | 71 groups, approved by the owner from a list |
| `held` | Readers split or are unsure, or a veto applies | 17 spelling pairs; 174 pairs after the majority round |

Vetoes (applied after readers, never overridden): different generational suffix, conflicting middle initials,
different organization and title, and a pair judged different inside a merge group. For candidates, a link or
create needs two models to agree with no low confidence; a waive needs one model's high confidence, checked by
a blind sample read by the second model.

Apply protocol, always: dry run, targeted backup of the affected tables (`stylebook_person_canonical`,
`stylebook_person_alias`, the mention link column, connections, activity, dismissals), apply through the shared
merge and link functions with per-group rollback, a ledger with the before-state, an activity row per merge,
integrity checks (mention counts equal, no mention on a removed record, no connection left on a removed record),
and a semantic reindex for moved mentions. Autonomy was "apply, then review named lists", safe because of the
ledger and the backups.

## Requirements by spec

IDs use a `P` prefix. This section replaces the earlier list in the people plan, which is now a pointer.
"Done" means the finder or script behavior exists today in the repository; the requirement is that it also holds
for the product and the outside agent.

### A. Ingest and canonicalization prevention

| ID | Requirement | Evidence |
| --- | --- | --- |
| PA1 | The shared person merge carries `public_figure` (true wins), fills an empty title and affiliation, and keeps the source's aliases with a trusted merge provenance; person link-mismatch checks must honor those cleanup aliases while continuing to distrust ingest-only aliases | A zero-mention source was a public figure; source aliases were all untrusted ingest aliases; the 2024 merge wave initially surfaced merged name variants as false mismatches |
| PA2 | Rewire connections before deleting the source, and de-duplicate edges that collide | 429 of 649 groups had connections on a duplicate |
| PA3 | Do not create a person when name, title, affiliation and type match an existing record; resolve known nicknames first | 649 groups of exact copies |
| PA4 | Do not create a person whose name is one letter from an existing record with the same organization (or, with no organization, the same title or type); link or hold it instead | About 300 spelling slips folded afterwards (`Shepsu Aakhu` and `Shepshu Aakhu`) |
| PA5 | A not-a-person check at canonical level (bands, groups, role labels) | `The Effigies` in the catalog |
| PA6 | Do not create canonicals for single-word names | 536 one-word labels; 885 `first_name_only` candidates |
| PA7 | The canonical person type describes the person's standing (elected official, athlete, community member); the story role (charged, victim) is kept per mention, not on the canonical | Madigan, Acevedo and 14 other groups carried two types |
| PA8 | A merge sets the survivor's type by the standing rule: prefer a non-crime / justice type that is not `other` or `unknown`; otherwise keep the crime / justice type; record the old and new type | 16 mixed-type groups |
| PA9 | Do not queue a relationship plus a first name ("Son", "Wife") or a bare first name with no title or affiliation; resolve surname-only public figures by title and affiliation | 568 relative candidates, 1,042 single-word pending names |
| PA10 | Apply the first-name and initials rules by person type (community members and unknown only); recognize relationship titles at extraction | Rules waived GZA, DMX, Trump and Putin; created relatives inherited "Son" as a title |
| PA11 | Fix the type taxonomy: remove the stray `Politician` value; decide what `other` and `unknown` should become | 31 `Politician` rows; 3,188 `other` or `unknown` |

### B. Review-queue and finder logic

| ID | Requirement | Evidence |
| --- | --- | --- |
| PB1 | Score title and affiliation in the finder, using containment (`Cook County` inside `Circuit Court of Cook County`) | 87% of pairs were same-name; rules folded 673 |
| PB2 | Block and score name variants, each with its own second signal. **Done:** nicknames, quoted nicknames, middle initials, dropped middle names, compound surnames, one-letter spelling slips (`_person_name_variants.py`). **Open:** first-initial-only, spacing, and two-letter slips | 179, 54, 75, 789 pairs; 5 and 2 still unseen |
| PB3 | Conflicting middle initials, and different organization plus role plus type, dismiss a pair by rule | 7 and 265 rule dismissals |
| PB4 | Exclude dismissed pairs from the check's next run, and show why a cluster is listed | The same clusters would reappear |
| PB5 | A `needs a person` state with a reason for held pairs and crime / justice clusters, separate from `needs approval` | 271 clusters left |
| PB6 | Ignore title words and generic labels consistently in blocking | Descriptors in labels and single-name labels |
| PB7 | List a bare name beside a numbered form (`Carlton Davis`, `Carlton Davis III`) when title or affiliation agrees; never list regnal numbers against each other | 40 groups; about half the same person |
| PB8 | Show the shared signal that put a pair on the list (same organization, same title, nickname, spelling) | Reviewers could not tell why pairs were listed |

### C. Review with AI

| ID | Requirement | Evidence |
| --- | --- | --- |
| PC1 | A versioned people rubric: same, different, unsure; confidence; article text is untrusted; vetoes applied after readers | `RUBRIC.md` |
| PC2 | A second rubric for crime / justice records: the type says nothing about who the person is; join private people only when something ties the records together; a public figure's distinctive name and role is enough | `RUBRIC_SENSITIVE.md`; 120 of 175 pairs settled |
| PC3 | Packets carry name-in-text quotes, role in story, titles, affiliations, types, aliases and mentions; candidate packets add ranked catalog candidates | Quotes naming the role settled most pairs; 150 links agreed |
| PC4 | Merge only when two models agree on same, neither low, one high, no veto. A dismissal needs two models agreeing on different, or one high-confidence `different` checked by a blind audit | 332 of 341; 70 of 70; 295 of 318 |
| PC5 | Crime / justice records: two models agreeing on different may dismiss; two agreeing on same may only propose a merge for a person to approve. An agent never merges, links or creates one alone (D20, replaces D16's blanket rule) | 49 dismissals, 71 proposals approved |
| PC6 | A reader-agreement log: pair, model, verdict, confidence, reason, rubric version, per round | Needed to calibrate each round |
| PC7 | Round-specific hints in the reader brief (for example "names differ by one letter") without changing the rubric | Spelling round |

### D. Agent API, auth, and undo

| ID | Requirement | Evidence |
| --- | --- | --- |
| PD1 | A merge endpoint that returns the connections, mentions, aliases and type change that will move, with a dry run | Connections moved on most duplicates |
| PD2 | A ledger with the before-state taken before any change, and an undo that restores the removed record, mentions, aliases, connections and type | A before-state captured after the type change nearly broke undo |
| PD3 | A reason code on every dismissal, and a way to list and reopen by reason | The dismissal table has no reason |
| PD4 | Record agent, model and rubric version on each decision; activity logged as an agent action | `actor_type="agent"` activity |
| PD5 | An approval list for proposed merges: show both records, both types, mentions and the readers' reasons; approve by group, all or some; applying uses the owner approval flag, not a separate path | 64 groups and 7 groups approved |
| PD6 | A candidate decision endpoint (create, link, waive) with reason codes, a ledger and undo | Candidate queue pass |

### E. Evaluation and operations

| ID | Requirement | Evidence |
| --- | --- | --- |
| PE1 | A random audit of merges and dismissals with a measured error rate before any unattended run | Only hand audits of 50 groups so far |
| PE2 | Named review lists for rule folds with mentions on a duplicate, reader merges, held pairs, proposals and crime / justice clusters | The lists in the plan |
| PE3 | Metrics: clusters by tier, rule versus reader resolution rate, held rate, zero-mention canonicals, reader agreement per round | Each was a hidden cost |
| PE4 | Run only on people created or changed since the last run | New people arrive daily |
| PE5 | When the finder changes, re-run readers on pairs it newly lists (shadow mode first) | 222 and 318 new pairs |
| PE6 | Count the queue by type and by "has anyone read this" before declaring it done | A cohort hid behind the packet filter in places |
| PE7 | Measure how much of the next queue the last cleanup created | Places lesson 8 |

### F. Category playbook

The program playbook gains four steps from people:

1. **Check what the finder compares before trusting its list.** Probe for pairs a person would join that share no
   key (nicknames, one-letter slips). Fixing the finder reveals records, so budget the review round.
2. **Require a second signal for every variant rule,** and test it against a near miss (two fire departments).
3. **Take the before-state first,** read the dry-run ledger for changed fields, then apply.
4. **Separate dismissing from merging for sensitive records,** and keep a named approval list.

## Product decisions to make

Each is a choice the owner has not yet made. The recommendation is what the work so far supports.

| # | Decision | Options | Recommendation |
| --- | --- | --- | --- |
| 1 | What the canonical person type means | Standing, with story role per mention; or role in the first story seen | Standing (PA7); needs a per-mention role field |
| 2 | Who may approve proposed merges, and where | The Stylebook UI with an approval list; or the agent API with an owner-held credential | UI list, approve by group (PD5) |
| 3 | Suffix and regnal cases | List them when title or affiliation agrees; or leave them alone | List when a second signal agrees; never list regnal numbers against each other (PB7). The owner deferred this |
| 4 | Autonomy for an unattended agent | Rule folds only; plus two-reader merges after a measured error rate; plus dismissals | Rule folds and two-reader dismissals now; merges after PE1 |
| 5 | Privacy of crime / justice records | Same storage and API as others; or separate handling | Decide before the outside agent gets read access (program doc, open question 3) |
| 6 | The 18,468 canonicals with no linked mention | Keep, archive, or remove | Measure first: do they cause duplicates? |
| 7 | Time: former roles and job changes | Record titles and affiliations with dates; or keep only the latest | Dates, so a job change is not "different organization" |
| 8 | Affiliation as a string or an organization id | Strings now; or call the organization catalog | Organization id once organizations are cleaned |
| 9 | Whether ingest may link a one-letter slip itself (PA4) | Link; or hold for review | Link only when the second signal is the organization; hold otherwise |
| 10 | Who reviews the held pairs | Owner list; or an in-product "needs a person" queue (PB5) | In-product queue with the reason |

## Open after people

- The duplicate finder is at zero live edges; its pair-key dismissals still need reason, evidence-hash and
  finder-version metadata so changed evidence can reopen them safely.
- The 151 held candidate rows and 36 crime / justice candidate rows.
- The 40 suffix groups, first-initial-only and spacing variants, and two-letter slips (PB2, PB7).
- A random audit of agreed merges for an error rate (PE1).
- The 18,468 zero-mention canonicals, the taxonomy cleanup (PA11), and the intersections and spans from places.
- Specs A through F are unbuilt; this file is the requirements input. The scratch scripts used for the passes
  (`tmp/stylebook-agent-cleanup/`, not committed) are prototypes for the ledger, undo and approval work.
