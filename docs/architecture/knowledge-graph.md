# Knowledge graph target architecture

**Status:** Phase A connections complete on `explore/knowledge-graph-architecture`.
Additive schema: `077_conn_kg_phase_a`. Data remap: `backfield migrate-connection-kg`.
Schema cutover: `078_conn_kg_cutover` (open-edge unique index; drop connection
`description` / `evidence_json`; evidence FK cascades). Soft-close / reopen, custom
natures, Stylebook + public `evidence[]`, and Stylebook UI polish ship. Storylines remain
Phase B.

This document is the decision record for evolving Stylebook relationships and coverage packaging
into a news-archive knowledge graph. It is **not** current runtime behavior. When slices ship,
update [`database.md`](database.md), [`../development/entities/overview.md`](../development/entities/overview.md),
and the relevant API docs, then retire or narrow the “proposed” sections here.

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
| Communities / packages | **Storylines** (multi-article coverage threads) |
| Invalidation | Deferred; v1 reinforce + editorial close escape hatch |

## Target graph shape

```text
Canonical person / org / location
  ◄── connection (preferred nature) ──► Canonical
         └── evidence[] (article, quote, confidence, …)

Article
  ◄── mention / occurrence ──► substrate ──► Canonical
  ◄── membership (optional primary) ──► Storyline (accepted)
```

**First-class traversable nodes:** canonicals and articles.  
**Storylines:** first-class Stylebook catalog objects (coverage packages), not Event entities.  
**Claims / stances:** prefer article∩storyline∩entity evidence packs; structured facts only when the
object is crisp (preferred nature to a canonical, or later topic/work). Do **not** make events
Stylebook citizens in this plan.

## Decision log

### D1 — Consumer priority

Public news APIs and archive agents first; not agent-context memory.

### D2 — No Event/Claim Stylebook canonicals

Events and propositional claims are hard to identity-manage and fight Stylebook’s substrate →
candidate → canonical muscle. Articles hold journalism; mentions ground entities; storylines group
coverage. Derived temporal facts (edges) are optional structure, not catalog entities.

### D3 — Storylines as the coverage object

A **storyline** is a subject covered across multiple stories or cycles (e.g. “2026 city budget”,
“dispute between X and Y”). Clients have asked for this. It fills the ontology gap for
issue-shaped navigation better than Event canonicals.

| Decision | Choice |
|----------|--------|
| Lifecycle | Candidate → accepted; only accepted are public first-class |
| Membership | Many-to-many article ↔ storyline |
| Ranking | Optional **primary** storyline per article; others secondary |
| Failure mode | Optimize against **false merge / wrong assign** (precision over recall) |
| Entity overlap in matching | **Soft prior** (boost / tighten bar); never a hard gate |
| Tenancy | Org-scoped storyline identity; project-aware membership (Stylebook-like) |
| Persistence | **Own tables and APIs** (not forced through entity substrate abstractions) |
| Presentation | Stylebook-class UX: catalog surfaces, article-review tab peer to people/places/orgs |
| Agate role | Post–Backfield Output side effect (propose only); not a required canvas node |
| Agate review | Read-only hint + link to Stylebook (recommended; confirm at implement time) |

### D4 — Storyline identification (compute)

Incremental, not full-corpus reclustering per ingest:

1. Use existing article embeddings (pgvector).
2. ANN against storyline search docs (summary embedding + optional member centroid) and a capped
   orphan neighborhood for rare “birth new storyline” proposals.
3. Cheap filters (time window, project/org scope); shared canonicals as soft signal.
4. LLM yes/no only on top-K neighbors; high threshold; prefer **link-to-existing** over create.
5. Occasional batch jobs for drift / merge suggestions — not on the hot path.

Cost should grow with **#storylines**, not **#articles**.

### D5 — Connection redesign (taxonomy + evidence + reinforce)

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

**D5b — Assign `temporal_kind` on each nature definition** (`atemporal` | `static` | `dynamic`),
inspired by the OpenAI temporal-agents cookbook, but as **catalog metadata**, not a classifier
pass on every edge.

| Kind | Meaning | Examples | Downstream use |
|------|---------|----------|----------------|
| `static` | True from a point; does not flip back and forth | `born_in`, `founded`, `founded_in` | Reinforce freely; rarely auto-close |
| `dynamic` | Can change / end | `leads`, `works_for`, `represents`, `located_at` | Weight “current” carefully; prefer close / `as_of` later |
| `atemporal` | Independent of calendar time | Rare for local-news ties | Treat like static unless needed |

- Preferred natures: field on the **code** registry entry.
- Custom natures: column on `stylebook_connection_nature_custom`; default `dynamic` (conservative),
  or inherit from `equivalent_to` when set.
- Do **not** store a separate LLM `temporal_type` on each connection row in v1 — resolve via nature
  join/lookup. Edges without a nature (description-only) default to `dynamic`.
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

**D5a — Reinforce, don’t version by default.** Same endpoints + preferred nature → append evidence;
do not mint parallel edges for repeated mentions.

**Accepted tradeoff:** discontinuous terms (left office, then returned) are not modeled as separate
validity windows in v1. Escape hatch: editorial close/delete (and later optional auto-close on clear
“former / no longer” language) so “current” does not rot forever.

Optional later: `valid_at` / `invalid_at`, `as_of` queries, and close/reopen or interval history
without changing the one-edge-many-evidence grain.

### D6 — Implementation sequencing

1. **This ADR** (done as living target doc).
2. **Connection redesign** — natures registry, evidence table, reinforce writer, API/UX updates.
3. **Storylines** — tables/APIs, propose/accept, Stylebook + article-review presentation, then
   public navigation.

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
| Add | `closed_at timestamptz NULL` — **soft-close only** in Phase A (editors/Stylebook). Public API
  hides closed by default (`include_closed` optional). Auto inference does not close. Prefer
  close over hard delete so evidence/activity stay coherent |
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
the pair. Extracted affiliation and entity metadata are labeled lower-trust hints: they can help
interpret text but cannot prove an edge. Every model proposal must identify its candidate and copy
an exact quote from that pair's evidence packet.

Classification batches at most eight pairs per request. The inline path permits four requests with
concurrency two; the article-wide ceiling is eight requests. Candidate pairs are ranked by direct
grammar, same-sentence evidence, adjacent-sentence evidence, then metadata-assisted evidence.
Overflow candidate keys are queued only after the article transaction commits and are processed by
an idempotent Celery task.

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

### Phase B — Storylines

#### New `stylebook_storyline`

| Column | Notes |
|--------|--------|
| `id` | UUID PK (canonical-like) |
| `stylebook_id` | FK → `stylebook` |
| `label`, `slug` | unique `(stylebook_id, slug)` |
| `summary` | editorial / LLM package summary |
| `status` | `candidate` \| `accepted` \| `rejected` \| `merged` (or equivalent) |
| `merged_into_id` | nullable FK self |
| `created_at` / `updated_at` | |
| Optional | `primary_article_id`, closed/archived flags |

#### New `stylebook_storyline_membership`

| Column | Notes |
|--------|--------|
| `id` | PK |
| `storyline_id` | FK |
| `article_id` | FK → `substrate_article` |
| `project_id` | denormalized from article for scoping (or join-only) |
| `status` | `proposed` \| `accepted` \| `rejected` |
| `is_primary` | bool; at most one accepted primary per article (partial unique) |
| `confidence` | nullable |
| `source` | `auto` \| `editor` |
| `created_at` / `updated_at` | |

Uniqueness: `(storyline_id, article_id)`. Partial unique: one `is_primary` accepted membership per `article_id`.

#### New `stylebook_storyline_embedding` (or columns on storyline)

Search doc for ANN: summary embedding (+ optional centroid metadata). Reuse pgvector patterns from `substrate_article_embedding`. Index for ANN query by `stylebook_id`.

#### Activity / bundles

- Extend `stylebook_activity` event kinds: storyline created/accepted/merged; membership proposed/accepted; connection evidence added / connection closed.
- Bundle schema bump later: export/import accepted storylines + memberships whose articles resolve.

### Unchanged

- `substrate_article`, mention/occurrence tables (still the article↔entity layer)
- Canonical person/location/organization tables
- No `stylebook_event_canonical` / claim tables in this plan

### Diagram (target)

```text
stylebook_connections          stylebook_connection_evidence
  (1 open row / nature+ends) ──< (N citations / articles)

stylebook_storyline            stylebook_storyline_membership
  (org catalog package) ─────< (N articles, optional primary)

stylebook_connection_nature_custom  (org-only; preferred natures in code)
```

## Relation to current system

| Area | Today | Target |
|------|--------|--------|
| Connections | `stylebook_connections` + `evidence_json`; uniqueness includes description | Connection row + `evidence` children; identity = endpoints + preferred nature |
| Natures | Small fixed auto set in `connections/taxonomy.py` | Code registry of preferred natures + aliases; org customs in DB |
| Articles in graph | Mentions only; not connection endpoints | First-class for traversal; episodes for provenance |
| Coverage packages | None in-repo | Storylines (candidate → accepted) |
| Agate | Auto-connections after `db_output` | Same hook family for storyline **proposals** |
| Query | 1-hop connection lists | Still 1-hop first; multi-hop / as-of later |

## Open points (resolve at implement time)

- Storyline candidate UX: queue density caps given precision-first thresholds (Phase B).
- Public API shapes for storyline list/detail and `include=` expansion (Phase B).

### Locked for Phase A

- Connection identity scope: **`stylebook_id`** (not project-keyed uniqueness).
- One open edge per `(stylebook_id, ends, coalesce(nature,''))` including null natures; many evidence.
- **Description on evidence only** (no connection-level description column); APIs may derive a
  display label from highest-confidence / latest evidence.
- Evidence uniqueness: partial unique on `(connection_id, article_id)` when article set; null-article
  rows unconstrained in DB, app-level quote/source dedupe.
- **Soft-close only** (`closed_at`); public hides closed by default; no auto-close in Phase A.
- **Org custom natures in Phase A** — table + Stylebook API/picker; preferred catalog stays in code.

## References

- [Graphiti](https://github.com/getzep/graphiti) — temporal context graphs, episodes, fact validity
- [Temporal agents with knowledge graphs (OpenAI cookbook)](https://developers.openai.com/cookbook/examples/partners/temporal_agents_with_knowledge_graphs/temporal_agents)
- Current connections: `packages/backfield-entities/src/backfield_entities/connections/`
- Entity model: [`../development/entities/overview.md`](../development/entities/overview.md)
