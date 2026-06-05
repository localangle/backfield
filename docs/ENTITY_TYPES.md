# Entity types and code layout

Backfield organizes persistence, catalog, API, and review code along two axes:

- **`content/`** — story carriers and run-scoped ingest context (article today; document later).
- **`entities/<type>/`** — Stylebook canonical domains and their substrate rows, mentions, and review surfaces.

Article is **content only**. It is not a Stylebook `EntityType` (see [`apps/stylebook-ui/src/lib/entityTypes.ts`](../apps/stylebook-ui/src/lib/entityTypes.ts)). Runtime flow and package boundaries are described in [`ARCHITECTURE.md`](ARCHITECTURE.md).

When adding a type, use [`.cursor/skills/add-entity-type/SKILL.md`](../.cursor/skills/add-entity-type/SKILL.md) — an interactive interview that produces `prd/<slug>/prd.md` and implementation issues.

## Stylebook entity types

| Type | Slug (`EntityType`) | Status |
|------|---------------------|--------|
| Location | `location` | Full stack (substrate ingest, Stylebook canonical, review) |
| Person | `person` | Full stack including PersonExtract node, Agate people review tab, Stylebook manual create, CSV import, and bundle export/import |
| Organization | `organization` | Stub — planned via add-entity-type skill |
| Work | `work` | Stub — planned via add-entity-type skill |

Folder names in Python packages use these slugs (`location`, not `place`). Pipeline JSON may still use `places` in Geocode output; that is product vocabulary, not package naming.

**Catalog create / import / export:** Stylebook catalog rows can be added manually, bulk-imported, or copied via org-admin ZIP bundles. See **Stylebook catalog transfer** below. Registry for CSV importers: `stylebook_api/imports/` (`csv` + entity slug).

Registry source of truth: `packages/backfield-entities/src/backfield_entities/registry/entity_types.py`.

## Stylebook catalog transfer (create, import, export)

Org-admin **Export** / **Import** (Agate **Manage stylebooks**, `worker.tasks.export_stylebook_bundle` / `import_stylebook_bundle`) copies **canonical rows only** — no meta, connections, substrate, or candidate queues. Import seeds a primary alias per canonical (locations and people) with `stylebook_bundle_import` provenance so rows are not treated as ingest orphans. New UUIDs are assigned on import.

Implementation hub: [`packages/backfield-entities/src/backfield_entities/catalog/full_bundle.py`](../packages/backfield-entities/src/backfield_entities/catalog/full_bundle.py). Manifest **`schema_version`** is **3** for new exports; import accepts **1**, **2**, or **3**.

| Concern | Location | Person | Organization / work (future) |
|---------|----------|--------|------------------------------|
| **Manual create (UI)** | `…/locations/create` → `POST …/canonical-locations` or legacy `POST /v1/locations` | `…/people/create` → `POST …/canonical-people` | Add `…/<type>/create` + stylebook-scoped POST when schema exists |
| **Bulk import format** | GeoJSON (`POST …/import/geojson/…`) | CSV (`POST …/import/csv/people/…`) | CSV via `stylebook_api/imports/csv_<type>.py` + registry `(csv, <plural>)` |
| **Import registry** | `(geojson, locations)` → `_GeoJsonLocationsImporter` | `(csv, people)` → `CsvPeopleImporter` | Register `(csv, organizations)` / `(csv, works)` after `add-entity-type` |
| **Bundle export shard** | `canonicals/locations/part-*.jsonl`, manifest `kind: canonical_location` | `canonicals/people/part-*.jsonl`, manifest `kind: canonical_person` | Add `canonicals/<type>/…`, `kind: canonical_<type>`, `_iter_*_canonicals`, `_import_*_row` |
| **Bundle import** | Handles `kind: canonical` (legacy v1/v2) and `canonical_location` | Handles `kind: canonical_person` | Extend `_import_shard_rows` dispatch + `importable_kinds` |
| **Standalone persist helper** | `backfield_entities.entities.location.persist.create_standalone_canonical` | `backfield_entities.entities.person.persist.create_standalone_canonical` | Same pattern under `entities/<type>/persist.py` |
| **Provenance strings** | `stylebook_ui_manual`, `stylebook_ui_import_geojson` | `stylebook_ui_manual`, `stylebook_ui_import_csv`, `stylebook_bundle_import` | Follow `{surface}_manual` / `{surface}_import_csv` |

**Checklist when adding a new entity type:**

1. **Schema (issue 01):** `stylebook_<type>_canonical` table + migration.
2. **Persist (issue 02):** `create_standalone_canonical`, slug allocator, export dict helper (`<type>_canonical_to_export_dict`).
3. **Manual create + list UI (issue 03):** `Create<Type>.tsx` using `CreateCanonicalShell` + `createCanonicalFormClasses` (see [`FRONTEND.md`](FRONTEND.md)), list **Create** button, `POST …/canonical-<type>`, canonical list page with standard filters (`**q**`, type, project scope, `**min_mentions**`, sort, pagination in URL — see [`FRONTEND.md`](FRONTEND.md) → **Canonical list URL state**).
4. **CSV import (issue 03+):** `Csv<Type>Importer`, analyze/run routes, `Import<Type>` wizard (non-geographic types use CSV only).
5. **Bundle transfer (same issue or follow-up):** export iterator + import row handler + manifest kind constant; extend tests in `tests/entities/test_full_bundle_roundtrip.py`.
6. **Docs:** Update this table, [`API.md`](API.md), [`OPERATIONS.md`](OPERATIONS.md) bundle bullets.

**Not in bundle v3:** primary substrate FKs are cleared on export/import; editor must re-link substrate rows in target orgs separately.

## Issue 00 — shared foundation

Before adding a new type, ensure **Issue 00** scaffolding is merged:

| Marker | Path |
|--------|------|
| Entity registry + fingerprint | `backfield_entities/registry/entity_types.py` |
| Persist domain dispatch | `worker/substrate/entities/registry.py` |
| Shared field docs | `docs/DATABASE.md` → **Shared entity fields** |
| UI entity registry | `apps/stylebook-ui/src/lib/entityRegistry.ts` |

Foundation is **refactor-only**: no new entity tables; location behavior unchanged.

## Adding a new type (default pipeline)

**Profile:** `extract_and_persist` — always include an extract node in the plan.

```
TextInput → <Type>Extract → DBOutput → substrate → Stylebook
```

**Location exception:** `PlaceExtract → GeocodeAgent → DBOutput` (enrichment node is location-only).

**Agate review** is always in the plan as a **late issue** (after extract + ingest smoke).

### Consolidated JSON keys

Keys follow **`EntityType` slug** pluralization (not Agate tab names):

| Slug | Consolidated key |
|------|------------------|
| `location` | `places` (legacy) |
| `person` | `people` |
| `organization` | `organizations` |
| `work` | `works` |

### Canonical ID policy

All **new** canonical types use **UUID string** primary keys from day one.

### Per-type issue order

| Issue | Slice |
|-------|-------|
| 01 | Type-specific schema (migration) |
| 02 | `backfield_entities/entities/<type>/` |
| 03 | stylebook-api + stylebook-ui |
| 04 | Worker substrate + orchestration handler |
| 05 | `<Type>Extract` node + smoke graph |
| 06 | Agate review tab |

See [`DATABASE.md`](DATABASE.md) for shared substrate and Stylebook column contracts.

## Per-type implementation patterns

Use this section when implementing **issue 02–06** after the interview ([`add-entity-type` skill](../.cursor/skills/add-entity-type/SKILL.md)). **Person** is the reference for `extract_and_persist` types; **location** remains the reference for geocoding, geometry, and legacy `/v1/candidates` paths.

### Required shell

Every new `extract_and_persist` type should ship the same **canonical ingest + editorial** skeleton unless the PRD explicitly waives a row.

| Layer | What to add | Reference |
|-------|-------------|-----------|
| **Shared plan types** | `CanonicalPersistDecision`, `CanonicalPersistPlan`, `ADJUDICATION_LINK_MIN_CONFIDENCE` (0.9) | [`canonical/plan_types.py`](../packages/backfield-entities/src/backfield_entities/canonical/plan_types.py) |
| **Policy** | `decide_<type>_canonical_persist_plan(session, stylebook_id, substrate_row) → CanonicalPersistPlan` | [`entities/location/policy.py`](../packages/backfield-entities/src/backfield_entities/entities/location/policy.py), [`entities/person/policy.py`](../packages/backfield-entities/src/backfield_entities/entities/person/policy.py) |
| **Recall** | `retrieve_<type>_canonical_candidates` — ranked `(canonical_id, label)` for defer paths, LLM payloads, and link UI (cap **24**, recall-biased score floor) | [`entities/person/recall.py`](../packages/backfield-entities/src/backfield_entities/entities/person/recall.py) |
| **Persist + link** | `create_standalone_canonical`, alias upsert on link, `rank_canonical_suggestions_for_substrate`, atomic link/unlink; **person:** `maybe_prune_ingest_orphan_person_canonical` removes ingest-only catalog rows when the last substrate unlinks (manual/CSV/bundle/review-queue rows protected via editorial alias provenance) | [`entities/person/persist.py`](../packages/backfield-entities/src/backfield_entities/entities/person/persist.py) |
| **Worker handler** | Upsert substrate → call policy → link / defer / materialize; register in [`substrate/entities/registry.py`](../apps/worker/src/worker/substrate/entities/registry.py) | [`substrate/entities/person/handler.py`](../apps/worker/src/worker/substrate/entities/person/handler.py) |
| **stylebook-api** | `GET /v1/<plural>/candidates`, `GET …/candidates/{id}/suggested-canonicals`, `POST …/{id}/link-canonical`, catalog `GET /v1/canonical-<plural>?q=…` | [`entities/person/`](../apps/stylebook-api/src/stylebook_api/entities/person/) |
| **stylebook-ui** | Candidate queue page, **Link to canonical** modal (suggestions + catalog search), canonical detail (mentions, meta, connections) | [`PersonCandidates.tsx`](../apps/stylebook-ui/src/pages/PersonCandidates.tsx), [`PersonCanonicalLinkModal.tsx`](../apps/stylebook-ui/src/components/PersonCanonicalLinkModal.tsx) |
| **Agate review (issue 06)** | processed_item entity slice + review tab | [`agate-api/…/entities/person/`](../apps/agate-api/src/api/processed_item/entities/person/), [`agate-ui/…/review/entities/person/`](../apps/agate-ui/src/lib/review/entities/person/) |

**Canonical persist decision contract** (implement in per-type `policy.py`; behavior differs by type):

| `CanonicalPersistDecision` | Typical trigger | Persist side effect |
|----------------------------|-----------------|---------------------|
| `LINK_EXISTING` | Tier-1 strong identity match (type-specific normalized fields) | Set substrate `stylebook_<type>_canonical_id`, refresh aliases |
| `DEFER` | Ambiguous recall, policy block, or review-only ingest | `canonical_link_status=pending`; store `canonical_review_reasons_json` |
| `MATERIALIZE_NEW` | No safe link; policy allows new catalog row | Create canonical + link (empty recall in rules mode; **person**/**location** `ai_assisted` may materialize after LLM declines recall when defer gates do not apply) |

| Type | Tier-1 auto-link inputs | Defer when |
|------|-------------------------|------------|
| **Location** | Geocode-resolved identity + location policy rules | Private residence, ambiguous place match, etc. |
| **Person** | Exact normalized **name + affiliation** on canonical | Alias hit with affiliation mismatch; multiple recall candidates (`ambiguous_person_canonical_match` in rules mode) |

**`canonicalization_mode`** (project/workspace): `rules` applies policy only; `ai_assisted` may call LLM adjudication when policy defers with non-empty recall (see opt-in below). **Location** also defers (and triggers LLM when `ai_assisted`) when fuzzy recall surfaces a candidate whose **pre-gate** string score is at or above the recall floor but **deterministic gates** (head-anchor, type, jurisdiction, etc.) demote it below that floor—e.g. spelling variants like `Racecourse` vs `Race Course`. Document chosen mode in the PRD.

**Suggested canonicals (link modal):** `rank_canonical_suggestions_for_substrate` should prefer **exact alias** match, then ranked recall. UI calls `GET …/candidates/{substrate_id}/suggested-canonicals` and catalog search `GET …/canonical-<plural>?q=…`. See [`API.md`](API.md) and [`FRONTEND.md`](FRONTEND.md).

### Candidate queue UX parity (required for every type)

Location and person queues share the same **linking niceties**; new types must ship the same behavior (do not copy-paste per page—reuse the shared modules below).

| Behavior | API / data | Shared UI (stylebook-ui) | Reference pages |
|----------|------------|--------------------------|-----------------|
| **Review context under rows** | List rows include `canonical_review_lines` from `canonical_review_reasons_json` (open + deferred when displayable). Location **`deferred_policy`** rows (e.g. geocode **`needs_review`** bucket) get product copy via [`review_display.py`](../packages/backfield-entities/src/backfield_entities/entities/location/review_display.py) at ingest and in [`candidate_review_display.py`](../apps/stylebook-api/src/stylebook_api/helpers/candidate_review_display.py) for legacy rows. | [`CandidateReviewReasons.tsx`](../apps/stylebook-ui/src/components/CandidateReviewReasons.tsx) | [`LocationCandidates.tsx`](../apps/stylebook-ui/src/pages/LocationCandidates.tsx), [`PersonCandidates.tsx`](../apps/stylebook-ui/src/pages/PersonCandidates.tsx) |
| **Create-modal “similar canonical exists” nudge** | `GET …/candidates/{substrate_id}/suggested-canonicals` while the user edits the draft label; show when label similarity ≥ **0.86** | [`candidateQueueSimilarity.ts`](../apps/stylebook-ui/src/lib/candidateQueueSimilarity.ts) (`pickCreateLinkNudge`), [`CreateCanonicalLinkNudgeAlert.tsx`](../apps/stylebook-ui/src/components/CreateCanonicalLinkNudgeAlert.tsx) | Same pages (create dialog) |
| **Post-create + linked toasts** | After accept/materialize or link, auto-dismiss success toasts (~3s); prefetch open-queue `q=` matches (top **5**) for optional “Potential links” dialog | [`useCandidateQueueToasts.ts`](../apps/stylebook-ui/src/lib/useCandidateQueueToasts.ts) (hook), [`candidateQueueToast.ts`](../apps/stylebook-ui/src/lib/candidateQueueToast.ts) (`useAutoDismissToast`), [`CandidateQueueCreatedToast.tsx`](../apps/stylebook-ui/src/components/CandidateQueueCreatedToast.tsx), [`CandidateQueueLinkedToast.tsx`](../apps/stylebook-ui/src/components/CandidateQueueLinkedToast.tsx), [`PotentialCandidateLinksDialog.tsx`](../apps/stylebook-ui/src/components/PotentialCandidateLinksDialog.tsx) | Wire the hook in `<Type>Candidates.tsx` with type-specific list/link callbacks and copy props on the two toast components |
| **Link modal** | Suggested-canonicals + catalog `?q=` search + `POST …/link-canonical` | Per-type `*CanonicalLinkModal` | [`CanonicalLinkModal.tsx`](../apps/stylebook-ui/src/components/CanonicalLinkModal.tsx), [`PersonCanonicalLinkModal.tsx`](../apps/stylebook-ui/src/components/PersonCanonicalLinkModal.tsx) |
| **Inline editor notes** | `POST …/candidates/{substrate_id}/note` stores `review_note` on `canonical_review_reasons_json`; list + context return `note` | [`useCandidateQueueInlineNote.ts`](../apps/stylebook-ui/src/lib/useCandidateQueueInlineNote.ts), [`CandidateQueueInlineNote.tsx`](../apps/stylebook-ui/src/components/CandidateQueueInlineNote.tsx) | Expand row → click-to-edit note under article context; sticky-note icon on rows with a saved note |

**API checklist for issue 03:** wire `canonical_review_lines` in the candidate list serializer (helper: [`candidate_review_display.py`](../apps/stylebook-api/src/stylebook_api/helpers/candidate_review_display.py)). Implement `POST …/candidates/{id}/note` and `_extract_review_note` like location/person. **UI checklist:** add `<Type>Candidates.tsx` by adapting the location page pattern and importing the shared pieces above; set `entityNoun` / `candidateNounPlural` / column labels for product copy.

### Opt-in patterns (enable in PRD when needed)

| Pattern | When to enable | Person reference | Notes |
|---------|----------------|------------------|-------|
| **LLM canonical adjudication** | Ambiguous recall under `ai_assisted` | Person: [`worker/…/person/adjudication.py`](../apps/worker/src/worker/substrate/entities/person/adjudication.py). Location: [`worker/…/canonical/adjudication.py`](../apps/worker/src/worker/substrate/canonical/adjudication.py) after policy `DEFER` with `ambiguous_canonical_match` (includes **gate-demoted** recall per `entities/location/policy.py`) | Link only if model confidence ≥ `ADJUDICATION_LINK_MIN_CONFIDENCE` (0.9); declined link → `MATERIALIZE_NEW` when materialize-after-recall gates allow (person: blocked by PersonExtract `flag_review` / `auto_defer`) |
| **Extract review routing** | Extract emits review codes (waive vs flag queue) | [`entities/person/review.py`](../packages/backfield-entities/src/backfield_entities/entities/person/review.py) | PersonExtract: `child` / `animal` → waive when `auto_apply_canonicalization`; `stage_name_or_alias` / `first_name_only` → open pending + `needs_review` on mentions |
| **Variant-name recall / search** | Display names vary (formal vs nickname, middle initials) | [`entities/person/name_match.py`](../packages/backfield-entities/src/backfield_entities/entities/person/name_match.py), recall + catalog `q` token OR | Organizations may use legal name vs DBA; skip for types with stable unique codes |

### Tests per issue

Minimum pytest targets per slice (global ladder: [`TESTING.md`](TESTING.md)). Replace `<type>` with the entity slug.

| Issue | Tests to add or extend |
|-------|------------------------|
| **01** | `tests/backfield_db/test_<type>_models.py` — schema + constraints |
| **02** | `tests/entities/test_<type>_persist.py` — policy, aliases, `rank_canonical_suggestions_*` |
| **02** | `tests/entities/test_<type>_recall.py` (and `test_<type>_name_match.py` if variant-name opt-in) |
| **03** | `tests/stylebook_api/test_<type>_api.py` — catalog list filters, `q`, candidates, suggested-canonicals, link |
| **04** | `tests/worker/test_<type>_substrate_persistence.py`, `test_<type>_review_canonical_flow.py` |
| **04** | Mocked LLM adjudication test when opt-in enabled |
| **05** | `packages/backfield-agate/tests/test_<type>_extract_*.py` |
| **06** | Agate API/UI tests or smoke follow-up per PRD |
| **Bundle** | Extend `tests/entities/test_full_bundle_roundtrip.py` when catalog transfer ships |

Run `make lint` and `make test` after each issue; `make smoke` when cross-service ingest or review behavior changes.

## Directory conventions by layer

### Worker (current)

```
apps/worker/src/worker/
  substrate/
    __init__.py
    orchestration.py
    entities/
      registry.py            # PersistDomainHandler dispatch
      location/
        handler.py           # places persist loop
        upsert.py
        mentions.py
        span.py
      person/
        handler.py           # people persist loop
        adjudication.py      # ai_assisted LLM pick among recalled canonicals
        upsert.py
        mentions.py
      organization/          # stub
      work/                  # stub
    canonical/
      adjudication.py
  nodes/db_output.py
```

Public entrypoint: `from worker.substrate import persist_from_consolidated`

### backfield-entities (current)

```
packages/backfield-entities/src/backfield_entities/
  catalog/                   # org Stylebook rows, resolve, library CRUD, bundle transfer
    bootstrap.py
    resolve.py
    stylebook_library.py
    full_bundle.py
  registry/
    entity_types.py          # slug registry, consolidated keys, fingerprint
  canonical/
    plan_types.py            # CanonicalPersistDecision, CanonicalPersistPlan (shared)
    link.py / link_matrix.py / retrieval.py / ...
  entities/
    linking/
      substrate_actions.py   # editorial substrate ↔ canonical link/unlink/suggestions
    location/
      policy.py              # decide_location_canonical_persist_plan
      persist.py
      types.py
    person/
      policy.py
      recall.py
      name_match.py          # opt-in variant-name overlap (link search + recall)
      review.py              # opt-in extract review routing
      persist.py
      types.py
  ingest/                    # substrate pipeline adjuncts
    db_output_settings.py
    geocode_cache/
    semantic_indexing/
```

### stylebook-api (current)

```
apps/stylebook-api/src/stylebook_api/
  helpers/
    project_scope.py
    pagination.py
  entities/
    location/
      locations.py           # /v1/locations (unchanged)
      candidates.py          # /v1/candidates*
      meta.py
    person/
      people.py              # /v1/canonical-people, catalog q + token search
      candidates.py          # /v1/people/candidates*
      meta.py
```

Location HTTP paths are unchanged. Future types use `/v1/<plural>`, `/v1/<plural>/candidates`, meta under canonical id — see [`API.md`](API.md).

### Stylebook canonical detail page (all entity types)

Every Stylebook **canonical detail** page (`/stylebook/{slug}/<type>/canonical/{id}`) must expose the same evidence + catalog sections as location (adapt labels and columns per type):

| Section | Scope | API (stylebook-scoped) |
|---------|--------|-------------------------|
| **Details** | Canonical card fields | `GET\|PATCH\|DELETE …/canonical-<type>/{id}` |
| **Mentions** | Grouped by linked substrate row; respects `?project=` filter | `GET …/canonical-<type>/{id}/mentions`, `GET …/linked-substrates` |
| **Metadata** | Stylebook-wide JSON meta on the canonical | `GET\|POST …/meta`, `PATCH\|DELETE …/meta/{meta_id}` |
| **Connections** | Stylebook-wide graph edges | `GET\|POST …/connections`, … |

UI wiring: reuse **`MetaTab`** via a thin `<Type>MetaTab` wrapper; mentions table mirrors `LocationDetail` (substrate group header with **Move…** / **Unlink**, nested article rows with nature, role, quoted text). Location adds **Geography**; non-location types omit map sections unless the entity has geography.

When the last mention is unlinked and no linked substrate rows remain, prompt to delete the canonical via **`usePromptDeleteEmptyCanonical`** (same copy and confirm flow for every type).

Link/move modals (`CanonicalLinkModal`, `PersonCanonicalLinkModal`) must omit the **source canonical** from suggestions and catalog search: pass **`excludeCanonicalId`** from canonical detail move flows, and exclude the substrate’s current linked canonical id when loaded from **`GET /v1/people/{id}`** / **`GET /v1/locations/{id}`**.

Do not show canonical **`status`** on the detail page Details card (location does not; same rule for person and future types). Status may still appear on canonical list rows where the list UI already surfaces it.

When adding a type (issue 03), ship mentions list route + linked-substrates + meta routes together with the detail page — do not leave metadata or mentions for a follow-up unless the type is catalog-only stub.

### stylebook-ui (current)

```
apps/stylebook-ui/src/lib/
  entityTypes.ts
  entityRegistry.ts          # EntityConfig + home cards
  entityConfigs/
    connectionPickers.ts
```

Location catalog pages remain under `src/pages/Locations*.tsx`; per-type issues add config-driven surfaces.

### agate-api processed_item (current)

```
apps/agate-api/src/api/processed_item/
  entities/
    location/
  overlay/
  mention_occurrences.py
```

### Agate UI review library (current)

```
apps/agate-ui/src/lib/review/
  entities/
    location/
```

Non-location tabs: **People** review is implemented (issue 06); other entity tabs remain placeholders.

### Agate nodes

One folder per node under `packages/backfield-agate/src/agate_nodes/<snake_case>/`.

Current extract nodes: `place_extract`, `person_extract`. Run `npm run sync-nodes` in `apps/agate-ui` after adding or changing node UI/metadata.

For **run AI cost and step labels**, the worker records React Flow `node_id` and node type on each `backfield_ai_call_record` row; Agate UI shows user-facing names from synced `metadata.json` `label` (via `getNodeStepDisplayName`, with `node_type` fallback when the graph id is missing). New extract nodes must ship `metadata.json` with a product **`label`** before merge.

**Extract prompt layout (`prompts/extract.md`):** Put static instructions, field rules, and output-format guidance **before** the article body. End the file with a `## Text to Analyze` section containing only the `{text}` placeholder (same pattern as `place_extract`). The opening paragraph should refer to “the text provided at the end of this prompt” so the model knows where to look. This keeps the long static prefix identical across requests so provider prompt caches can reuse it; only the trailing article text changes per run.

`db_output` stays the generic persist node; entity logic lives in worker `substrate/`.

## Naming rules

- **Python package folders:** `location`, `person`, `organization`, `work` (match `EntityType`).
- **Database tables:** Do not rename `substrate_*` or `stylebook_location_*` in layout-only refactors.
- **Pipeline / review JSON:** May keep legacy keys (`places`, etc.).

## Validation

```bash
make lint
make test
```

Run `make smoke` when runtime behavior across services changes. Per-issue test expectations: **Per-type implementation patterns** → **Tests per issue**; command ladder: [`TESTING.md`](TESTING.md).
