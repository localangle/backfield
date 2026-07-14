# Agate nodes

This is the source-of-truth developer guide for Agate graph nodes, including
runtime registration, graph compatibility, node panels, output display, and review
integration.

Canonical entity types span more than a node. Use
[`entities/implementation.md`](entities/implementation.md) for that cross-layer
work and `.cursor/skills/add-entity-type/SKILL.md` for a new canonical domain.
Use `.cursor/skills/add-agate-node/SKILL.md` for a new pipeline node.

## Node profiles

| Profile | Role | Current examples | Typical review |
|---|---|---|---|
| Input | Ingress text, JSON, or an S3 batch | `TextInput`, `JSONInput`, `S3Input` | None |
| Output | Return JSON, persist Backfield data, or write S3 | `Output`, `DBOutput`, `S3Output` | JSON; entity review after DBOutput |
| Extract | Produce grounded structured records | `PlaceExtract`, `PersonExtract`, `OrganizationExtract`, `CustomExtract` | Entity tabs or Custom |
| Enrich | Transform or resolve upstream values | `GeocodeAgent`, `ArticleMetadata` | Existing entity tab or Meta |
| Embed | Produce semantic vectors | `EmbedText`, `EmbedImages` | Info/Images plus JSON |
| Other | Gather or reshape graph data | `Gather` | Panel output and JSON |

The package currently contains these metadata-backed folders:

```text
article_metadata  custom_extract  db_output       embed_images
embed_text        gather          geocode_agent   json_input
organization_extract              output          person_extract
place_extract     s3_input        s3_output        text_input
```

## End-to-end layer map

| Layer | Path |
|---|---|
| Node source | `packages/backfield-agate/src/agate_nodes/<snake_case>/` |
| Runtime re-export | `packages/backfield-agate/src/agate_runtime/nodes/<snake_case>.py` |
| Runner registry | `packages/backfield-agate/src/agate_runtime/nodes/__init__.py` |
| Async runner registry | `packages/backfield-agate/src/agate_runtime/runners.py` |
| Worker execution | `apps/worker/src/worker/tasks.py` |
| Synced UI copy | `apps/agate-ui/src/nodes/<snake_case>/` |
| Generated UI registry | `apps/agate-ui/src/nodes/registry.ts` |
| Panel shell | `apps/agate-ui/src/components/NodePanel.tsx` |
| Panel tabs | `apps/agate-ui/src/lib/nodePanelTabs.ts` |
| Compatibility | `apps/agate-ui/src/lib/nodeCompatibility.ts` |
| Bookend validation | `apps/agate-ui/src/lib/flowValidation.ts` |
| Icons and colors | `apps/agate-ui/src/lib/nodeUtils.ts`, `nodeColors.ts` |
| Processed-item review | `apps/agate-api/src/api/processed_item/`, `apps/agate-ui/src/lib/review/` |

Most nodes emit JSON only. Durable entity writes normally flow through Backfield
Output to `worker/substrate/orchestration.py`, which dispatches consolidated keys
to registered domain handlers.

## Package UI is the source of truth

Author React node UI beside the runtime:

```text
packages/backfield-agate/src/agate_nodes/<snake_case>/
  metadata.json
  node.py
  runner.py                         # when needed
  prompts/                          # when needed
  ui/
    NodeComponent.tsx
    PanelComponent.tsx
    VisualizationComponent.tsx      # when needed
    *.ts or *.tsx helpers
```

Do not hand-edit `apps/agate-ui/src/nodes/`. From `apps/agate-ui`, run:

```bash
npm run sync-nodes
```

`predev` and `prebuild` also run the sync. `scripts/sync-nodes.js`:

- scans package node folders with `metadata.json`;
- copies node, panel, visualization, and additional TypeScript UI modules;
- inlines configured prompt and output-format files into generated metadata;
- loads prompt presets from `prompts/presets/`;
- injects `nodeMetadata` into copied components when necessary;
- regenerates `src/nodes/registry.ts`.

A node change includes both the package source and generated app copy in the same
reviewable change.

## Runtime contract

Each runtime node provides `run_<snake_case>(params, inputs) -> dict` from its
package folder. Add the thin runtime re-export and register the PascalCase metadata
type in `NODE_RUNNERS`; also register it in `ASYNC_NODE_RUNNERS` when execution is
asynchronous.

Decide explicitly whether output is:

- run-scoped JSON only;
- an existing consolidated key consumed by Backfield Output;
- a new durable domain requiring schema and substrate work;
- an enrichment of an existing entity review lane.

Use Pydantic models for structured boundaries and test output shape and failures.
LLM work must flow through the existing call and usage tracking paths.

### Extract prompts

Keep static instructions, field rules, and output-format guidance before the input
text. End `prompts/extract.md` with:

```text
## Text to Analyze

{text}
```

This keeps the reusable prompt prefix stable while the article text varies.

## `metadata.json`

Metadata drives runtime lookup, chooser copy, compatibility, canvas chrome, panels,
and step display names.

| Field | Contract |
|---|---|
| `type` | PascalCase React Flow and executor type |
| `label` | User-facing chooser, panel, progress, and cost-summary name |
| `icon` | Lucide icon registered in `nodeUtils.ts` |
| `color` | Metadata color retained for compatibility |
| `description` | Plain-language panel description |
| `category` | Input, output, extraction, enrichment, embedding, or other grouping |
| `dependencyHelperText` | Optional upstream guidance |
| `requiredUpstreamNodes` | Transitive branch-ancestry requirements |
| `inputs`, `outputs` | Port IDs, labels, and value types |
| `defaultParams` | Initial graph node data |

Input bookends are `TextInput`, `JSONInput`, and `S3Input`. Output bookends are
`Output`, `DBOutput`, and `S3Output`; all other enabled metadata nodes are middle
steps.

The worker records node ID and type for AI usage. Agate resolves display names from
the current graph and metadata label, with node type as a fallback, so every node
needs a useful product label.

## Canvas components

`ui/NodeComponent.tsx` uses React Flow `NodeProps`, normally wrapped in `memo`.
Match existing node cards:

- `w-[280px]` card width and selected `ring-2 ring-primary`;
- category-derived icon and background from `nodeUtils.ts`/`nodeColors.ts`;
- short muted preview text;
- explicit handle IDs matching metadata ports.

Handles exist for topology resolution but are hidden on the guided canvas because
wiring is automatic.

## Panel shell and tabs

`NodePanel.tsx` owns drawer chrome, scrolling, metadata description, dependency
guidance, tab navigation, invalid-connection messaging, and lazy panel loading.
Package panels render only inner content.

`GraphPanelContext` provides organization and project IDs, workspace Stylebook
defaults, and project AI-model loading. Reuse that context and existing helpers
instead of calling Core directly from a package panel.

Tab IDs and labels are centralized in `src/lib/nodePanelTabs.ts`. Current routing:

| Node type | Tabs |
|---|---|
| Text Input, S3 Input | Settings; Output when run output exists |
| JSON Input | Settings, Info; Output when run output exists |
| Place, Person, Organization, Custom Extract | Settings, Prompt, Output, Info |
| Article Metadata | Settings, Prompt, Output, Info |
| Geocode Agent | Settings, Models |
| Embed Text, Embed Images | Settings, Info |
| Gather | Settings, Info; Output when run output exists |
| JSON Output | Output only when run output exists |
| Backfield Output | Settings, Stylebook |
| S3 Output | Settings; Output when run output exists |

Wrap each panel section in `NodePanelTabGate`. Update `getNodePanelTabs` whenever a
panel adds or removes a section.

### Panel design conventions

- Primary labels use `text-sm font-medium`; use `FieldLabel` for required fields.
- Helper copy uses `text-xs text-muted-foreground`.
- Intro and empty-state copy uses
  `text-sm text-muted-foreground leading-relaxed`.
- Top-level tab content uses `space-y-4`; label/control groups use `space-y-2`.
- Numeric values that users type freely use text inputs rather than browser number
  spinners.
- Use **Stylebook** in user-facing panel copy, not “catalog.”
- Apply the product-copy and message rules in
  [`frontend/conventions.md`](frontend/conventions.md).

Panel props should include only what the panel reads. For editable fields, treat
`editMode` and `setNodes` as a pair and patch only the selected node's `data`.
Merge defaults before rendering.

AI model selects use `apps/agate-ui/src/lib/nodePanelAiModel.ts` and
`graphContext.fetchProjectAiModels`. Display the catalog model name and persist its
provider/model and configuration IDs. Do not hard-code model presets. Stylebook
selection persists `stylebook_id`; the reader accepts the older camelCase key only
for compatibility.

## Output and review integration

Panel Output tabs use `currentRun`, `nodeOutputLookupSpec`, and
`getNodeOutputById`. Add `VisualizationComponent.tsx` only when the run detail
needs a node-specific visualization.

Processed-item review tabs are `info`, `places`, `people`, `organizations`,
`images`, `meta`, `custom`, and `json`.

- Use panel plus JSON for diagnostic and pass-through output.
- Feed an existing entity lane when output enriches places, people, or
  organizations; document the consolidated merge contract.
- Add a dedicated editable review surface only when users must edit a distinct
  record domain. Extend the shared overlay and reviewed-output merge.
- Do not add a second visualization that duplicates an existing entity review
  surface.

Custom Extract is the reference for a non-canonical editable record domain.
Locations, people, and organizations use the entity implementation path.

## Checklist

1. Add package runtime, metadata, typed schemas, and focused tests.
2. Add runtime re-export and runner registration.
3. Declare ports and upstream requirements; verify graph compatibility.
4. Author node and panel UI in the package source.
5. Register panel tabs and any new icon.
6. Wire output lookup, visualization, persistence, or review only when required by
   the node contract.
7. Run `npm run sync-nodes` from `apps/agate-ui`.
8. Verify package and generated app trees changed together.
9. Run targeted tests, then:

```bash
make lint
make test
```

Run `make smoke` when execution or persistence crosses live service boundaries.
