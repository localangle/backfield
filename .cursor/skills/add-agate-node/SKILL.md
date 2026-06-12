---
name: add-agate-node
description: >-
  Plan and add an Agate pipeline node (Input, Output, Extract, Enrich, Embed, or Other)
  through an interactive interview that produces a PRD and implementation issues. Read
  docs/NODES.md first. Hand off to add-entity-type for canonical Extract types that
  produce Stylebook entities.
---

# Add Agate node

Use this skill when adding a **net-new Agate pipeline node** or re-planning a port from agate-ai-platform.

**Not for canonical entity types.** If the node is an extract that produces Stylebook substrate (people, organizations, works, locations), stop and use [`add-entity-type`](../add-entity-type/SKILL.md).

**Output:** `prd/<slug>/prd.md` then `prd/<slug>/issues/NN-*/issue.md` (gitignored). Hand issues to an agent for implementation.

**Adjustments to existing nodes** (copy, defaults, panel layout without output contract changes): follow [`docs/NODES.md`](../../docs/NODES.md) checklist only — no PRD.

**Read first:**

1. [`docs/NODES.md`](../../docs/NODES.md) — profiles, layers, review tiers, persistence gate, checklists
2. [`docs/FRONTEND.md`](../../docs/FRONTEND.md) — panel design system and sync flow
3. [`docs/ARCHITECTURE.md`](../../docs/ARCHITECTURE.md) — package boundaries
4. **agate-ai-platform** sibling repo — copy-then-adapt per `AGENTS.md`

**Related skills:** [`add-entity-type`](../add-entity-type/SKILL.md), [`backfield-db-change`](../backfield-db-change/SKILL.md), [`write-a-prd`](../write-a-prd/SKILL.md), [`prd-to-issues`](../prd-to-issues/SKILL.md), [`update-repo-docs`](../update-repo-docs/SKILL.md)

---

## Entry: choose path

| Situation | Path |
|-----------|------|
| **Net-new node type** | Interview below → PRD → issues |
| **Tweak existing node** | [`docs/NODES.md`](../../docs/NODES.md) → **Checklist: adjust existing node** |
| **Extract → Stylebook canonical entity** | [`add-entity-type`](../add-entity-type/SKILL.md) |

---

## Interview rules

- **One question at a time.** Wait for an answer before the next question.
- **~10 core questions** plus profile branches; skip when N/A.
- Resolve dependencies in order.

### Question script

Ask in this order (skip N/A):

1. **Node slug** — Folder name (`snake_case`) and PascalCase `type` (e.g. `place_filter` / `PlaceFilter`)
2. **Profile** — Input | Output | Extract | Enrich | Embed | Other
   - If **Extract** and output is a **canonical Stylebook entity** → **stop**; hand off to [`add-entity-type`](../add-entity-type/SKILL.md)
3. **Purpose** — One sentence user-facing description (becomes `metadata.json` `description` and panel copy)
4. **PRD slug** — Kebab-case directory under `prd/<slug>/`
5. **Upstream / downstream** — Which node types connect; port ids; `requiredUpstreamNodes`
6. **Output shape** — JSON schema or reference example; consolidated key if any
7. **Review tier** — None | Panel+JSON (default for non-entity) | Feeds entity review (which tab: places / people / organizations) | New review surface (flag as out-of-scope unless product insists)
8. **LLM / AI** — Models, prompt files, capabilities (skip for non-LLM profiles)
9. **Visualization** — Custom viz component, or panel output only?
10. **Port source** — Greenfield vs copy from agate-ai-platform (which node path?)
11. **Smoke acceptance** — Minimal graph + expected output to prove the node works

### Persistence gate (substrate block)

Ask **only when any** of:

- Durable cross-run storage (new tables)
- New consolidated key consumed by `DBOutput` / orchestration
- Reads/writes existing substrate tables

When the gate fires, ask:

12. **Durability scope** — Run-scoped vs article-scoped vs project-scoped
13. **Table namespace** — `substrate_*` vs `agate_*`
14. **Persist path** — Node persists directly vs emits JSON for downstream `DBOutput`
15. **Stylebook linkage** — Any canonical FK, or pipeline-only

Record decisions; plan **issue 00** (migration) via [`backfield-db-change`](../backfield-db-change/SKILL.md) when new tables are needed.

### Profile branches (ask when relevant)

| Profile | Extra questions |
|---------|-----------------|
| **Input** | Bookend type (`TextInput` / `JSONInput` / `S3Input`)? Batch vs inline? |
| **Output** | `Output` (JSON only) vs `DBOutput` (persist) vs `S3Output` (S3 files)? Stylebook override on DBOutput? |
| **Extract** | Non-canonical only here. Prompt layout per [`ENTITY_TYPES.md`](../../docs/ENTITY_TYPES.md) |
| **Enrich** | Mutates upstream key in place vs new key? Feeds which review merge path? |
| **Embed** | Embedding model; storage target (new table vs semantic indexing pipeline) |
| **Other** | Flow-control semantics; idempotency; error propagation |

---

## Node profiles (reference)

| Profile | Examples | Stylebook |
|---------|----------|-----------|
| Input | `TextInput`, `JSONInput`, `S3Input` | No |
| Output | `Output`, `DBOutput`, `S3Output` | DBOutput persists only |
| Extract | `PlaceExtract`, … | Entity extracts → `add-entity-type` |
| Enrich | `GeocodeAgent` | No new canonical type |
| Embed | *(future)* | Usually no |
| Other | Gather, stats, format | Case-by-case |

---

## PRD addendum

After the interview, write `prd/<slug>/prd.md` using [`write-a-prd`](../write-a-prd/SKILL.md) **plus** under **Implementation Decisions**:

- **Profile** and **Extract handoff** (if any)
- **Upstream/downstream** wiring and port contract
- **Output JSON schema** and consolidated key (if any)
- **Review tier** and merge contract (if feeds entity review)
- **LLM / AI** (models, prompts, cost tracking)
- **Visualization** (if any)
- **Persistence / substrate** (if gate fired)
- **Port source** (agate-ai-platform path or greenfield)
- **Smoke acceptance** criteria
- **Issue ordering** (below)

---

## Issue order template

Break the PRD into issues via [`prd-to-issues`](../prd-to-issues/SKILL.md):

| Issue | Slice | Skip when |
|-------|-------|-----------|
| **00** | Schema / migration | Persistence gate false |
| **01** | Runtime + unit tests — `agate_nodes/`, `agate_runtime/nodes/`, `NODE_RUNNERS` | — |
| **02** | Graph UI — `metadata.json`, `ui/`, `nodePanelTabs`, `npm run sync-nodes`, commit synced output | — |
| **03** | Run output / viz — Output tab, `VisualizationComponent` | Input; simple pass-through |
| **04** | Review merge hook — `agate-api` / `agate-ui` review lib | Review tier None or Panel+JSON only |
| **05** | Smoke / demo graph | — |

Each slice is a thin vertical path — demoable on its own.

### Layer reference (runtime + UI)

| Layer | Path |
|-------|------|
| Node package | `packages/backfield-agate/src/agate_nodes/<snake>/` |
| Runtime registration | `packages/backfield-agate/src/agate_runtime/nodes/` + `NODE_RUNNERS` |
| Worker | `apps/worker/src/worker/tasks.py` (uses registry; `DBOutput` special-cased) |
| Graph UI source | `agate_nodes/<snake>/ui/` |
| Panel tabs (app) | `apps/agate-ui/src/lib/nodePanelTabs.ts` |
| Sync | `apps/agate-ui/scripts/sync-nodes.js` |
| Review (if tier requires) | `apps/agate-api/src/api/processed_item/`, `apps/agate-ui/src/lib/review/` |
| Tests | `packages/backfield-agate/tests/` or `tests/agate_nodes/` |

Full checklist: [`docs/NODES.md`](../../docs/NODES.md).

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

See [`docs/TESTING.md`](../../docs/TESTING.md).

When behavior or node workflows change, update [`docs/NODES.md`](../../docs/NODES.md) via [`update-repo-docs`](../update-repo-docs/SKILL.md).
