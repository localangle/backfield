# Stylebook maintenance: people (plan)

**Status:** Planning only; nothing here is a runtime contract. Starts the next category in
[`stylebook-maintenance-program.md`](stylebook-maintenance-program.md), using the playbook and the places
lessons in [`stylebook-places-requirements.md`](stylebook-places-requirements.md).

No people cleanup has been run yet. The numbers below are a read-only survey of `cpm-stylebook`
(`STYLEBOOK_ID = 14`), 2026-11-17, taken to decide how to start.

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
