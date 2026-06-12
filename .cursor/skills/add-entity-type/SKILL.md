---
name: add-entity-type
description: >-
  Plan and add a Stylebook canonical entity type through an interactive interview
  that produces a PRD and implementation issues. Use when adding person, organization,
  work, or extending location patterns with substrate, Stylebook, extract nodes, and
  Agate review. Read docs/ENTITY_TYPES.md first.
---

# Add entity type

Use this skill when adding a **canonical entity type** (person, organization, work, or a new type beyond location) or when re-planning an existing stub type.

**Output:** `prd/<slug>/prd.md` then `prd/<slug>/issues/NN-*/issue.md` (gitignored). Hand issues to an agent for implementation.

**Read first:**

1. [`docs/ENTITY_TYPES.md`](../../docs/ENTITY_TYPES.md) — layout, Issue 00 foundation, issue order, **Per-type implementation patterns** (required shell vs opt-in)
2. [`docs/DATABASE.md`](../../docs/DATABASE.md) — shared field contracts
3. [`docs/ARCHITECTURE.md`](../../docs/ARCHITECTURE.md) — package boundaries
4. **agate-ai-platform** sibling repo — copy-then-adapt per `AGENTS.md`

**Related skills:** [`add-agate-node`](../add-agate-node/SKILL.md) (non-entity pipeline nodes), [`write-a-prd`](../write-a-prd/SKILL.md), [`prd-to-issues`](../prd-to-issues/SKILL.md)

---

## Entry: detect and branch

Before interviewing, inspect the repo for **Issue 00 foundation** markers. Foundation is **present** when **all** exist:

| Marker | Path |
|--------|------|
| Entity registry + fingerprint | `packages/backfield-entities/src/backfield_entities/registry/entity_types.py` |
| Persist domain dispatch | `apps/worker/src/worker/substrate/entities/registry.py` |
| Shared field docs | `docs/DATABASE.md` → section **Shared entity fields** |
| UI entity registry | `apps/stylebook-ui/src/lib/entityRegistry.ts` |

**If foundation is missing** → **prerequisite path** (below).

**If foundation is present** → **per-type path** (below).

**If foundation is partial** → propose an “extend shared base” issue before per-type work.

---

## Prerequisite path (Issue 00)

Use when foundation markers are missing (first time on a clone, or pre-foundation branch).

1. Confirm scope: shared substrate + Stylebook canonical contracts, orchestration registry, API/UI scaffolds — **no new entity tables**.
2. Write `prd/entity-types-foundation/prd.md` (short; reference [`docs/ENTITY_TYPES.md`](../../docs/ENTITY_TYPES.md) Issue 00).
3. Write `prd/entity-types-foundation/issues/01-shared-foundation/issue.md`.
4. Implement Issue 00 in code before running per-type planning again.

---

## Per-type path

### Interview rules

- **One question at a time.** Wait for an answer before the next question.
- **~14–16 questions** total; skip when defaults apply.
- Resolve dependencies in order; do not accept vague “it depends” without resolving each branch.

### Question script

Ask in this order (skip N/A):

1. **Slug** — Which `EntityType`? (`person`, `organization`, `work`, or new slug)
2. **Display names** — Singular/plural user-facing labels (non-technical; see `docs/FRONTEND.md`)
3. **PRD slug** — Kebab-case directory under `prd/<slug>/`
4. **Substrate entity fields** — Type-specific columns beyond [shared substrate contract](../../docs/DATABASE.md)
5. **Stylebook canonical fields** — Type-specific columns beyond shared canonical contract
6. **Fingerprint inputs** — Which normalized fields feed `compute_identity_fingerprint` for this type?
7. **Consolidated JSON key** — Confirm registry entry (default: plural of slug; `location` → `places` is legacy only)
8. **Extract output shape** — Per-entity and per-mention fields the `<Type>Extract` node must emit
9. **Mention fields** — Shared vs type-specific (`role_in_story`, `nature`, review flags)
10. **Stylebook UI** — List columns, filters (include **Minimum mentions** + project scope + URL query sync per [`FRONTEND.md`](../../docs/FRONTEND.md)), candidate clustering behavior
11. **API quirks** — Anything beyond standard list / detail / candidates / meta
12. **Agate review tab** — Enabled? List vs edit vs link-to-Stylebook actions (planned in late issue)
13. **Connection pairs** — New allowed edges in `stylebook_connections` (see `connections_utils.py`)
14. **Smoke acceptance** — Minimal demo text and success criteria for extract → DBOutput → substrate
15. **Canonical auto-link strategy** — Tier-1 identity fields for `LINK_EXISTING`, defer rules, whether recall list is required for suggestions (see ENTITY_TYPES → **Required shell** decision table; copy location vs person policy shape)
16. **Opt-in ingest/review** — Any of: LLM adjudication (`ai_assisted`), extract review routing (waive vs flag queue), variant-name recall/catalog search (person `name_match` pattern). Default **none** unless the PRD needs them.

After the interview, record decisions in the PRD and map opt-ins to issues **02** (policy/recall), **04** (worker adjudication), **05** (extract review), **03** (link modal search).

### Pipeline profile

| Profile | Pipeline | Types |
|---------|----------|-------|
| **`extract_and_persist`** | `TextInput → <Type>Extract → DBOutput` | Default for all **new** types |
| **`location_full`** | `PlaceExtract → GeocodeAgent → DBOutput` | Location only |

- **Extract is always in the plan** for new types (no catalog-only path).
- **Enrichment/resolution nodes** are out of scope except location’s `GeocodeAgent`.
- **Agate review** is always in the plan as a **late issue** (after ingest + extract smoke).

### Consolidated JSON keys

Keys are derived from **`EntityType` slug**, not Agate tab names. Types without Agate tabs use the same rule.

| Slug | Consolidated key | Notes |
|------|------------------|-------|
| `location` | `places` | Legacy; do not rename |
| `person` | `people` | Irregular plural |
| `organization` | `organizations` | |
| `work` | `works` | |

Registry source of truth: `backfield_entities.registry.entity_types`.

### Canonical ID policy

All **new** canonical types use **UUID string** primary keys from day one (same as `stylebook_location_canonical.id`).

---

## PRD addendum

After the interview, write `prd/<slug>/prd.md` using [`write-a-prd`](../write-a-prd/SKILL.md) **plus** these sections under **Implementation Decisions**:

- **Shared vs type-specific fields** (substrate, mention, occurrence, canonical, alias, meta)
- **Consolidated key** and extract JSON schema
- **Fingerprint inputs**
- **Stylebook API surface** (routes follow `/v1/<plural>`; location URLs unchanged)
- **Stylebook UI** (columns, filters, sections)
- **Agate review tab** behavior
- **Connection pairs** to add
- **Canonical auto-link** (tier-1 fields, defer reasons, `canonicalization_mode`)
- **Opt-in patterns** (LLM adjudication, extract review codes, variant-name search) — reference ENTITY_TYPES **Opt-in** table
- **Issue ordering** (see below)

---

## Issue order template

Break the PRD into issues via [`prd-to-issues`](../prd-to-issues/SKILL.md). Standard per-type order:

| Issue | Slice | Blocked by |
|-------|-------|------------|
| **01** | Type-specific schema (Alembic migration) | Issue 00 foundation |
| **02** | `backfield_entities/entities/<type>/` persist + link | 01 |
| **03** | stylebook-api routers + stylebook-ui **entity shell configs** (`entityConfigs/<type>/candidateQueue`, `canonicalLinkModal`, `canonicalList`, `canonicalDetail`) + thin page wrappers (`<Type>Candidates.tsx`, `<Type>s.tsx`, `<Type>Detail.tsx`) — mount shared shells, do not copy `LocationCandidates.tsx` | 02 |
| **04** | Worker `substrate/entities/<type>/` + orchestration handler registration | 01 |
| **05** | `<Type>Extract` Agate node + smoke graph | 04 |
| **06** | Agate review (agate-api + agate-ui tab) | 05 |

Each slice is a thin vertical path — demoable on its own.

---

## Layer reference (location)

Replace `<type>` with the entity slug. Prefer new paths over legacy shims.

| Layer | Location reference |
|-------|-------------------|
| DB models | `packages/backfield-db` — `SubstrateLocation*`, `StylebookLocation*` |
| Shared contracts | `backfield_db/entity_contracts.py`, `backfield_entities/registry/entity_types.py` |
| Worker persist | `worker/substrate/entities/location/` + `orchestration.py` |
| Stylebook logic | `backfield_entities/entities/location/persist.py` |
| stylebook-api | `stylebook_api/entities/location/` |
| stylebook-ui | `entityConfigs/location/*` + thin page wrappers + `entityRegistry.ts` (see ENTITY_TYPES → **stylebook-ui shells**) |
| Extract node | `agate_nodes/place_extract/` |
| Enrichment (location only) | `agate_nodes/geocode_agent/` |
| agate-api review | `api/processed_item/entities/location/` |
| agate-ui review | `apps/agate-ui/src/lib/review/entities/location/` |

### Layer reference (person — `extract_and_persist`)

Use for organization/work and other non-location types. Waive rows marked opt-in unless the PRD enables them.

| Layer | Person reference |
|-------|------------------|
| DB models | `SubstratePerson*`, `StylebookPerson*` in `backfield_db` |
| Policy + recall | `backfield_entities/entities/person/policy.py`, `recall.py` |
| Opt-in name overlap | `entities/person/name_match.py` |
| Opt-in extract review | `entities/person/review.py` |
| Persist + suggestions | `entities/person/persist.py` |
| Worker | `worker/substrate/entities/person/handler.py`; opt-in `adjudication.py` |
| stylebook-api | `stylebook_api/entities/person/` (`people.py`, `candidates.py`, `meta.py`) |
| stylebook-ui | `entityConfigs/person/*` + thin wrappers (`PersonCandidates.tsx`, `PersonCanonicalLinkModal.tsx`, `People.tsx`, `PersonDetail.tsx`) |
| Extract node | `agate_nodes/person_extract/` |
| agate-api review | `api/processed_item/entities/person/` |
| agate-ui review | `apps/agate-ui/src/lib/review/entities/person/` |
| Tests | See ENTITY_TYPES → **Tests per issue** (`tests/entities/test_person_*.py`, etc.) |

---

## Pipeline nodes (no new EntityType)

For nodes that do **not** introduce a new Stylebook `EntityType` (Input, Output, Enrich, Embed, Other, or non-canonical Extract), use [`add-agate-node`](../add-agate-node/SKILL.md) and [`docs/NODES.md`](../../docs/NODES.md). Entity extract nodes for **this** type stay in issue **05** of the per-type template above.

---

## Validation

After implementation issues merge:

```bash
make lint
make test
```

After cross-service runtime changes:

```bash
make smoke
```

See `docs/TESTING.md` for the command ladder; per-issue test file expectations are in [`docs/ENTITY_TYPES.md`](../../docs/ENTITY_TYPES.md) → **Tests per issue**.
