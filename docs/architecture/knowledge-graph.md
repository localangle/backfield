# Knowledge graph architecture (connections)

**Status:** Phase A connections **shipped**. Additive schema: `077_conn_kg_phase_a`. Data remap:
`backfield migrate-connection-kg`. Schema cutover: `078_conn_kg_cutover` (open-edge unique index;
drop connection `description` / `evidence_json`; evidence FK cascades). Soft-close / reopen,
custom natures, Stylebook + public `evidence[]`, and automatic inference with reinforce writer
are live. **Storylines** (coverage packaging) are deferred — see
[`../plan/storylines.md`](../plan/storylines.md).

This document is the decision record and operational guide for Stylebook **connections** in the
news-archive knowledge graph. For entity ingest and canonicals, see
[`database.md`](database.md) and [`../development/entities/overview.md`](../development/entities/overview.md).

## Goals and non-goals

### First consumers

- Public `/public/v1` news APIs
- Agents navigating a **news archive** (entity ↔ article ↔ coverage), not chat/agent memory

### Non-goals (v1)

- Adopting Graphiti/Zep or a separate graph database as source of truth
- Stylebook **Event** / **Claim** canonicals (world-incident identity)
- Full bi-temporal versioning of discontinuous office terms on day one
- Required Agate canvas nodes for storyline assignment

### Borrowed ideas (Graphiti / temporal cookbook)

Keep Postgres + Stylebook as source of truth. Align concepts where they help news products:

| Concept | Backfield mapping |
|---------|-------------------|
| Episode | Article (ingest/provenance unit) |
| Entity nodes | Stylebook canonicals (person, location, organization; later works as documents) |
| Facts / edges | Connections with preferred natures + evidence rows (+ optional validity later) |
| Communities / packages | **Storylines** (deferred — [`../plan/storylines.md`](../plan/storylines.md)) |
| Invalidation | Deferred; v1 reinforce + editorial close escape hatch |

## Target graph shape

```text
Canonical person / org / location
  ◄── connection (preferred nature) ──► Canonical
         └── evidence[] (article, quote, confidence, …)

Article
  ◄── mention / occurrence ──► substrate ──► Canonical
```

**First-class traversable nodes (Phase A):** canonicals and articles via connections and mentions.
**Storylines** (article ↔ coverage package) are deferred — see
[`../plan/storylines.md`](../plan/storylines.md).

## Decision log

### D1 — Consumer priority

Public news APIs and archive agents first; not agent-context memory.

### D2 — No Event/Claim Stylebook canonicals

Events and propositional claims are hard to identity-manage and fight Stylebook’s substrate →
candidate → canonical muscle. Articles hold journalism; mentions ground entities. Derived
temporal facts (connections) are optional structure, not catalog entities. Multi-article
coverage packaging (**storylines**) is deferred — see [`../plan/storylines.md`](../plan/storylines.md).

### D3 — Connection redesign (taxonomy + evidence + reinforce)

Coupled with temporality ideas; implement as the foundation under public relationship APIs.

#### Preferred nature catalog

- **Global product catalog in code** (same pattern as the entity type registry), not live admin edit.
- Seed from established vocabs — primary backbone: **TAC KBP** slot-filling relations and
  **FollowTheMoney** link schemata; **Schema.org** / **Wikidata** ids carried as crosswalk.
  Curated draft: [`connection-natures.md`](connection-natures.md).
- Synonym / alias map normalizes inference onto preferred slugs.
- **Org custom natures** as Stylebook/org catalog rows with optional `equivalent_to` preferred slug
  — **ship in Phase A** (table + API/picker).
- Free-text **narrative** for nuance lives on **evidence** (not edge identity, not a connection column).

#### Temporal kind on natures (not per-edge LLM typing)

**D3b — Assign `temporal_kind` on each nature definition** (`static` | `dynamic`),
inspired by the OpenAI temporal-agents cookbook, but as **catalog metadata**, not a classifier
pass on every edge.

| Kind | Meaning | Examples | Downstream use |
|------|---------|----------|----------------|
| `static` | True from a point; does not flip back and forth | `born_in`, `founded`, `founded_in` | Reinforce freely; rarely auto-close |
| `dynamic` | Can change / end | `leads`, `works_for`, `represents`, `located_at` | Weight “current” carefully; prefer close / `as_of` later |

- Preferred natures: field on the **code** registry entry.
- Custom natures: column on `stylebook_connection_nature_custom`; default `dynamic` (conservative),
  or inherit from `equivalent_to` when set.
- Do **not** store a separate LLM `temporal_type` on each connection row — resolve via nature
  join/lookup. Edges without a nature (description-only) default to `dynamic`. Atemporal ties are
  treated as static until the product has a concrete need to distinguish them.
- Skip cookbook `FACT` / `OPINION` / `PREDICTION` on connections; those belong on quote/claim
  layers if ever.

#### One edge, many evidence

Replace “many near-duplicate edges” (today uniqueness includes `description`) with:

```text
Connection: (stylebook_id, from, to, nature_or_null) → one open row
Evidence[]: article_id, narrative/description, quote, confidence, source, …
```

New supporting articles **append evidence** (reinforce). Uniqueness must not key on description.
Null nature is allowed: still **one open edge per endpoint pair** with many evidence rows.
**Description lives only on evidence** (decision C): no connection-level description column;
list/detail APIs pick a display label from evidence (prefer highest confidence, then latest
`observed_at`).

#### Reinforce policy (v1)

**D3a — Reinforce, don’t version by default.** Same endpoints + preferred nature → append evidence;
do not mint parallel edges for repeated mentions.

**Accepted tradeoff:** discontinuous terms (left office, then returned) are not modeled as separate
validity windows in v1. Escape hatch: editorial close/delete (and later optional auto-close on clear
“former / no longer” language) so “current” does not rot forever.

Optional later: `valid_at` / `invalid_at`, `as_of` queries, and close/reopen or interval history
without changing the one-edge-many-evidence grain.

#### Reported currentness (lightweight temporal layer)

Dynamic edges carry a materialized `currentness` summary (`current` | `former` | `unknown`) plus
`currentness_as_of` and the evidence row responsible for that summary. Each evidence row records
what its source explicitly establishes (`current` | `former` | `unspecified`).

- Article publication time is the reference time; `created_at` remains storage time.
- Rule-based proposals remain authoritative for relationship existence, but every resolved dynamic
  edge receives a currentness review attempt before persistence. Existing candidate-review
  currentness is preserved when it duplicates a deterministic proposal; only still-unreviewed
  edges require the currentness-only model pass.
- The newest explicit current/former evidence updates the edge summary.
- Unspecified evidence reinforces the relationship without changing currentness.
- Evidence records `currentness_review_source` so reviewed-but-ambiguous evidence can be
  distinguished from an unreviewed fallback. Model failures do not discard an otherwise valid
  deterministic relationship.
- Older evidence never overrides newer evidence, and age alone never means a relationship ended.
- Static edges ignore currentness. Public and Stylebook responses project it as not applicable.
- `closed_at` remains editorial record lifecycle and never means the real-world relationship ended.

This deliberately answers “what was most recently reported?” rather than “what was true at time
T?” Full validity intervals, automatic aging, and historical `as_of` reconstruction remain deferred.

#### Canonical merge / delete (connection lifecycle)

| Editor action | Connection behavior |
|---------------|---------------------|
| Merge canonical A → B | Rewire open edges that touch A onto B (`rewire_connections_for_canonical_merge`); drop self-loops; dedupe when B already has the same open edge |
| Delete canonical A (no merge) | Soft-close every open edge that references A (`close_open_connections_for_canonical`) before the row is removed |

Paths covered: Stylebook API delete, cleanup delete, ingest prune of unused canonicals, and
the shared merge helpers. Historical orphans (deleted before this lifecycle landed) can be
inspected/fixed with:

```text
backfield repair-orphan-connections                 # dry-run
backfield repair-orphan-connections --apply         # commit
backfield repair-orphan-connections --stylebook-id N --apply
```

Repair rewires a missing endpoint when evidence `from_display_name` / `to_display_name`
uniquely matches one living canonical of that type in the Stylebook; otherwise it soft-closes.

### D4 — Implementation sequencing

1. **Connection redesign** — natures registry, evidence table, reinforce writer, API/UX updates
   (shipped).
2. **Storylines** — deferred; see [`../plan/storylines.md`](../plan/storylines.md).

Temporal `as_of` on connections is a follow-on once reinforce + evidence exist.

## Schema changes (outline)

Namespaced `stylebook_*` / `substrate_*` tables in `packages/backfield-db`. Preferred natures stay
**code**, not rows (except org customs).

### Phase A — Connection redesign

#### Alter `stylebook_connections`

| Change | Detail |
|--------|--------|
| Drop uniqueness | Remove `uq_stylebook_connection_exact_edge` (includes `description`) |
| Add uniqueness | Open-edge identity: `(scope, from_entity_type, from_entity_id, to_entity_type, to_entity_id, nature)` among non-closed rows. Nature may be null: **one open null-nature edge per endpoint pair**, with multiple evidence children (same reinforce grain as preferred natures) |
| Drop or deprecate | `evidence_json` after backfill into child rows; **`description` moves off the connection** — narrative lives on evidence only (Phase A decision C) |
| Keep | Endpoints, nature (nullable), open/closed; list APIs derive a display label from best/latest evidence at read time (or a thin computed field in the response, not an identity column) |
| Add | `closed_at timestamptz NULL` — **soft-close** in Phase A (editors/Stylebook). Public API
  hides closed by default (`include_closed` optional). Auto inference does not close edges on
  its own. Prefer close over hard delete so evidence/activity stay coherent. **Canonical delete**
  soft-closes open edges that reference the deleted id; **canonical merge** rewires those edges
  to the survivor (see lifecycle below) |
| Add (optional v1) | `updated_at`; `preferred_nature` stays in `nature` column with code-registry validation |
| Scope | **`stylebook_id`** is the identity scope (like canonicals). Migrate existing
  `project_id`-keyed rows to the project’s Stylebook. Do not dual-key uniqueness.
  Provenance stays on evidence (`article_id` → project). Optional nullable
  `project_id` on the connection only if useful for audit; not part of uniqueness |

Indexes: keep from/to lookups; add partial unique index
`WHERE closed_at IS NULL` on `(scope, from_*, to_*, coalesce(nature, ''))` so null natures
collapse to a single open edge per pair (Postgres unique index with `coalesce`, matching today’s
null-safe pattern).

#### New `stylebook_connection_evidence`

| Column | Notes |
|--------|--------|
| `id` | PK |
| `connection_id` | FK → `stylebook_connections`, cascade delete |
| `article_id` | FK → `substrate_article`, nullable for manual/non-article evidence |
| `quote` / `reason` / `description` | text — per-citation narrative (`description` or `reason` required for auto rows) |
| `confidence` | numeric, nullable |
| `source` | e.g. `dboutput_auto_connections`, `manual` |
| `prompt_version` | nullable |
| `run_id` / `processed_item_id` | nullable provenance |
| `observed_at` | article pub_date or ingest time |
| `created_at` | row insert time |
| `payload_json` | optional leftover fields from today’s `evidence_json` |

Uniqueness: **partial unique** `(connection_id, article_id) WHERE article_id IS NOT NULL`.
Null-article evidence (manual / legacy synthetic): **no DB unique constraint** — writer skips
duplicates when normalized quote (+ source) already exists on that connection. Index
`(article_id)`, `(connection_id, created_at)`.

**Data migration:** see [Existing-data migration plan](#existing-data-migration-plan) below.

#### New `stylebook_connection_nature_custom` (org escape hatch)

**In Phase A** (not deferred): table + Stylebook API (+ picker). Preferred natures remain code-only.

| Column | Notes |
|--------|--------|
| `id` | PK |
| `stylebook_id` | FK → `stylebook` |
| `slug` | unique per stylebook |
| `label` | display |
| `equivalent_to` | nullable preferred slug from code catalog |
| `temporal_kind` | `static` \| `dynamic`; default `dynamic`, or inherit from `equivalent_to` |
| `created_at` / `updated_at` | |

Inference may emit a custom slug only if it exists for that Stylebook; otherwise prefer
preferred catalog or null nature + narrative on evidence. Auto prompts list preferred natures
first; customs optional in editor flows.

#### Deferred (not phase A)

`valid_at` / `invalid_at` / `invalidated_by` on connections — add when shipping `as_of` without changing evidence grain.

### Existing-data migration plan

Applies to Phase A only (connections). Storylines are additive — no backfill of historical
packages required for v1.

Run as an **explicit offline / one-off command**, not silently inside API traffic:

```bash
backfield migrate-connection-kg                 # dry-run inventory + plan
backfield migrate-connection-kg --inventory-only
backfield migrate-connection-kg --apply         # commit remaps, merges, evidence
backfield migrate-connection-kg --stylebook-id N --json
```

Prefer: schema migration `077_conn_kg_phase_a` (additive) → this data command →
later cutover uniqueness + drop `evidence_json` → ship reinforce writer.

Implementation: `backfield_entities.connections.migrate_kg_phase_a` + CLI
`backfield migrate-connection-kg`.

#### Step 0 — Inventory (preflight)

On each environment, count and sample:

| Bucket | Example query intent |
|--------|----------------------|
| By nature × pair | Spot unexpected natures (`plays_for` org→org, `located in`, …) |
| Null-nature edges | How many; sample descriptions for remappable vs leave-null |
| Exact duplicates | Same `(scope, from, to, nature, description)` |
| Near-duplicates | Same `(scope, from, to, nature)`, different description |
| `evidence_json` present vs absent | Auto vs manual |

Record totals for a before/after report. Do not delete in this step.

#### Step 1 — Nature remaps (in place, before merge)

Apply deterministic rewrites. Preserve row ids until Step 2 merges.

| Current | Action |
|---------|--------|
| `represented_by` (person→person) | Swap endpoints; set nature `represents` |
| `plays_for` where both ends are organizations (team→school pattern) | Set nature `team_of` |
| Nature not in preferred catalog and not custom | Leave as-is temporarily **or** map via an explicit alias table; do not invent |
| Typo / freeform natures (e.g. `located in`) | Map to preferred slug if unambiguous (`located_at`); else null nature + keep description |
| Null nature | Keep null for now; optional later pass: LLM or rules suggest preferred nature from description (offline, high threshold, no auto-apply without review flag) |

Do **not** invent `holds_office_in` / `owns` / etc. from null descriptions in the first cut —
wrong remaps poison more than missing natures. Those improve on **new** inference after catalog
+ prompt ship; optional offline suggest-queue is Phase A+.

#### Step 2 — Merge to one open edge + evidence children

For each group key `(stylebook_id, from_entity_type, from_entity_id, to_entity_type, to_entity_id, coalesce(nature,''))` among non-closed rows:

1. **Pick survivor:** prefer row with richest `evidence_json`; else earliest `created_at`; else lowest `id`.
2. **Connection fields on survivor:** drop connection-level `description` after migration (or
   leave nullable unused). Narratives move to evidence only.
3. **For each row in the group (including survivor):** insert one
   `stylebook_connection_evidence` child:
   - If `evidence_json` present → map fields (`quote`, `confidence`, `source`, `article_id`,
     `run_id`, `processed_item_id`, `prompt_version`, `match_basis`, …) into columns;
     map connection `description` → evidence `description`/`reason`; remainder → `payload_json`.
   - If no `evidence_json` (manual / thin rows) → synthetic evidence:
     `source=legacy_manual` or `legacy_duplicate`, `description`/`quote`/`reason` from the
     row’s description when usable, `article_id` null, `observed_at` = row `created_at`.
4. **Dedupe evidence** within the group on `(article_id)` when set: keep highest confidence /
   richest quote.
5. **Retire extras:** delete duplicate connection rows (after evidence attached to survivor),
   **or** set `closed_at` and a migration note if soft-delete is preferred for audit — hard
   delete is OK if activity log already recorded `connection_created`.

Null-nature groups merge on the same key with empty nature — one null-nature open edge per
endpoint pair, many evidence/description citations. Editors can later assign a preferred nature.

#### Step 3 — Reject / quarantine garbage

Flag or drop (do not merge into survivors):

- Descriptions that assert **no relationship** (seen in production samples).
- Self-loops (`from_*` = `to_*`) if any remain.
- Endpoint pairs outside the allowed matrix after remaps.

Quarantine table or migration report is enough; no need for a permanent product surface.

#### Step 4 — Schema cutover

1. Enforce new partial unique index on open edges
   `(scope, from_*, to_*, coalesce(nature,'')) WHERE closed_at IS NULL` — including **one open
   null-nature edge per endpoint pair** (same reinforce / many-evidence model as preferred natures).
2. Stop writing `evidence_json`; writer only appends evidence children (reinforce).
3. Drop `evidence_json` column after verifying child-row parity (row counts + spot checks).
4. Update Stylebook/public APIs to return evidence arrays; connection list/detail may include a
   derived `description` from best evidence for convenience, but storage is evidence-only.

#### Step 5 — Validation

- Connection count: survivors ≈ distinct open `(scope, ends, nature)` groups from Step 0.
- Evidence count ≥ original rows with `evidence_json` + synthetic manuals.
- Spot-check high-volume natures (`works_for`, `member_of`, `located_at`) and remaps
  (`represents`, `team_of`).
- Bundle export/import: bump schema version only when storylines land; Phase A may keep
  connections bundle shape with evidence embedded or as nested objects.
- Activity history: historical `connection_created` events may reference deleted duplicate ids —
  accept as append-only audit (do not rewrite activity).

#### Out of scope for this migration

- Backfilling `holds_office_in` / `owns` / `appointed_by` onto null-nature rows (optional later
  suggest job).
- Temporal `valid_at` / `invalid_at`.
- Storyline membership for historical articles.
- Unbounded archive-wide inference. Historical inference uses the scoped, budgeted backfill below.

#### Rollback

Keep a backup dump or staging clone through Step 4. Schema rollback = restore
`evidence_json` from children if needed (reversible while column exists). After column drop,
rollback requires restore from backup.

### Evidence-first automatic connection inference

Backfield Output generates canonical pairs only when article text or linked mention occurrences put
the entities in the same or adjacent sentence, or when a high-precision construction identifies
the pair. High-precision constructions include journalistic party+district tags such as
``D-Ottawa`` / ``R-Springfield`` after a legislator's name (deterministic ``represents``).
When a person's extracted **affiliation** names an organization in the article (including team
nicknames such as Phillies → Philadelphia Phillies), Backfield Output may create a
``plays_for`` / ``coaches`` / ``works_for`` edge without an LLM call. When an organization and
place canonical name the same site (place head tokens are a prefix of the org head, or
equal; single-token city names require exact match), Backfield Output may create a deterministic
``located_at`` edge when the article also co-mentions the pair. Single-token city names alone do
not qualify (Chicago Public Schools ↮ Chicago). Other extracted metadata remains a lower-trust
hint for the model. Every model proposal must identify its candidate and copy an exact quote from
that pair's evidence packet.

The model returns one explicit `link=true|false` judgment for every submitted pair. Only
`link=true` decisions continue through quote, nature, confidence, and endpoint validation;
`link=false` is authoritative and records a `model_declined` skip. An affirmative decision is also
rejected when its rationale says the evidence does not establish a relationship. This consistency
gate is nature-independent and does not add another model call.

Linked entities are capped at **32 per type** for inference, but entities that participate in same- or
adjacent-sentence pair evidence are reserved before occurrence-ranked truncation so high-signal
teams and people are not dropped from crowded articles.

Classification batches at most eight pairs per request. Backfield Output uses up to sixteen
requests per article with concurrency two (128 ranked candidate pairs). Candidate pairs are ranked
by direct grammar, same-sentence evidence, adjacent-sentence evidence, then metadata-assisted
evidence. Overflow pairs that exceed the request budget are reported as `unprocessed` in
diagnostics rather than queued for a second pass.

An idempotent Celery task (`infer_deferred_article_connections`) remains available for scoped
backfills that pass explicit candidate ids.

All deterministic and model proposals are resolved together before writing:

- symmetric natures use stable endpoint order;
- exact endpoint+nature duplicates retain the strongest direct evidence;
- declared specific natures suppress only their broader equivalents;
- explicitly incompatible natures require a confidence or evidence margin, otherwise neither is
  written as an `ambiguous_conflict`;
- independent natures, including `founded` and `leads`, may coexist.

The reinforce writer appends article evidence to an existing open edge and never closes editorial
or historical edges. Inference summaries report candidate sources/rejections, entity and candidate
truncation, request and batch sizes, prompt characters, elapsed time, duplicate/subsumption/conflict
counts, and create/reinforce outcomes.

### Unchanged

- `substrate_article`, mention/occurrence tables (still the article↔entity layer)
- Canonical person/location/organization tables
- No `stylebook_event_canonical` / claim tables in this plan

### Diagram (connections)

```text
stylebook_connections          stylebook_connection_evidence
  (1 open row / nature+ends) ──< (N citations / articles)

stylebook_connection_nature_custom  (org-only; preferred natures in code)
```

Storylines (deferred): [`../plan/storylines.md`](../plan/storylines.md).

## Relation to current system

| Area | Before Phase A | Now (Phase A) |
|------|----------------|---------------|
| Connections | `stylebook_connections` + `evidence_json`; uniqueness includes description | Connection row + `evidence` children; identity = endpoints + preferred nature |
| Natures | Small fixed auto set in `connections/taxonomy.py` | Code registry of preferred natures + aliases; org customs in DB |
| Articles in graph | Mentions only; not connection endpoints | First-class for traversal; episodes for provenance |
| Coverage packages | None in-repo | Deferred — [`../plan/storylines.md`](../plan/storylines.md) |
| Agate | Auto-connections after `db_output` | Same hook; reinforce writer + explicit `link` judgment |
| Query | 1-hop connection lists | Still 1-hop first; multi-hop / as_of later |

## Locked decisions (Phase A)

- Connection identity scope: **`stylebook_id`** (not project-keyed uniqueness).
- One open edge per `(stylebook_id, ends, coalesce(nature,''))` including null natures; many evidence.
- **Description on evidence only** (no connection-level description column); APIs may derive a
  display label from highest-confidence / latest evidence.
- Evidence uniqueness: partial unique on `(connection_id, article_id)` when article set; null-article
  rows unconstrained in DB, app-level quote/source dedupe.
- **Soft-close** (`closed_at`); public hides closed by default; inference does not auto-close.
  Canonical **delete** soft-closes open edges that reference the deleted id; canonical **merge**
  rewires open edges to the survivor (via `connections/rewire.py` / `connections/lifecycle.py`).
  One-shot repair: `backfield repair-orphan-connections` (dry-run by default; `--apply` to commit).
- **Org custom natures in Phase A** — table + Stylebook API/picker; preferred catalog stays in code.

## References

- [Graphiti](https://github.com/getzep/graphiti) — temporal context graphs, episodes, fact validity
- [Temporal agents with knowledge graphs (OpenAI cookbook)](https://developers.openai.com/cookbook/examples/partners/temporal_agents_with_knowledge_graphs/temporal_agents)
- Current connections: `packages/backfield-entities/src/backfield_entities/connections/`
- Entity model: [`../development/entities/overview.md`](../development/entities/overview.md)
- [`../plan/storylines.md`](../plan/storylines.md) — deferred coverage packaging (storylines)
