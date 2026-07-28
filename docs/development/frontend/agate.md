# Agate frontend

`apps/agate-ui` owns the guided flow builder, run experience, processed-item review,
and organization administration screens.

## Guided flow builder

Create, edit, and run routes share `GuidedFlowBuilder.tsx` and
`components/flow-builder/`.

- The sequence is **Choose an input** → **Choose an output** → **Build your flow**.
- Input bookends are Text, JSON, and S3. Output bookends are JSON Output, Backfield
  Output, and S3 Output.
- Middle steps are added from node and edge **+** controls. Compatibility comes from
  synced node metadata: ports and transitive `requiredUpstreamNodes`.
- Connections are automatic. The canvas has no node palette, drag-to-connect
  interaction, or visible manual handles.
- Nodes may be repositioned; saved positions survive normal graph edits.
- Run view uses the same builder in read-only mode. Editing takes a snapshot;
  **Cancel** restores it and **Save** validates and persists the graph.

Core modules:

```text
apps/agate-ui/src/
  pages/GuidedFlowBuilder.tsx
  pages/RunGraph.tsx
  components/flow-builder/
  lib/flowGraphModel.ts
  lib/flowValidation.ts
  lib/guidedFlowCapabilities.ts
  lib/nodeCompatibility.ts
```

Node panels and synced node UI are documented in
[`../nodes.md`](../nodes.md).

## Run and rerun contracts

- Text and JSON bookend input on the run page is saved to the graph spec before a
  run starts.
- Rerun actions confirm that the current saved flow will run, identify the
  Backfield Output reconciliation policy, and explain that run-local review edits
  for affected items will be cleared.
- Backfield Output presents **Add Only**, **Smart Merge**, and **Replace**. Runtime
  inference owns domain reconciliation details; the panel does not expose
  implementation-level ownership overrides.
- While an S3 batch run is creating processed items, the run table shows
  **Preparing items ...** instead of the empty-run state.

## Processed-item deep links

Processed-item detail tabs are:

`info`, `places`, `people`, `organizations`, `images`, `meta`, `custom`, and `json`.

The active tab is stored as `?tab=<id>`. Missing or invalid values resolve to
`info`. A legacy `#<tab>` fragment is read on entry and promoted to the query-string
form. Keep this contract when changing tab routing so shared review links remain
stable.

Cross-app links are built in `src/lib/platformUrls.ts`:

- canonical location:
  `/stylebook/<slug>/locations/canonical/<uuid>`
- canonical person:
  `/stylebook/<slug>/people/canonical/<uuid>`
- canonical organization:
  `/stylebook/<slug>/organizations/canonical/<uuid>`
- person and organization candidate queues:
  `/stylebook/<slug>/<people|organizations>/candidates`

An optional `?project=<slug>` carries the current project context.

## Review architecture

Review code follows the same content/entity split as the backend:

```text
apps/agate-ui/src/lib/review/
  content/                    # article fields, tabs, output display
  entities/
    custom/
    location/
    person/
    organization/
  overlay/                    # shared review overlay operations

apps/agate-api/src/api/processed_item/
  content/
  entities/
    article_meta/
    location/
    person/
    organization/
  overlay/
```

Locations, people, and organizations all have implemented editorial review
surfaces. Their tabs combine run output with saved substrate context, support
story-text evidence navigation, and write editor changes to the processed-item
overlay. When a saved article exists, supported edits also update or remove the
corresponding substrate row and mentions through Stylebook API helpers.

The entity tabs share these contracts:

- Review-only rows remain in the run overlay until a saved article exists.
- Saved rows may be edited for the current story without silently changing the
  Stylebook canonical.
- **Open Stylebook …** uses the canonical detail URL when linked and the
  project-scoped candidate queue otherwise.
- Add flows lock the chosen story passage while fields are completed; changing the
  passage does not discard entered fields.
- Remove actions update the overlay and remove saved story evidence when present.
- Saved editor changes and stale orphan patches show the shared editor-review
  banner.
- Review editing is locked while a rerun is in flight.

Location review additionally owns geography editing, map selection, adopting saved
story geometry for a Stylebook location, and the no-geography path. Custom review
owns typed record tables and mention editing. The JSON tab switches between
immutable original output and reviewed output, downloads the selected version, and
can sync reviewed S3 Output content back to its object.

## Shell, settings, and administration

- Core session helpers are in `src/lib/core-api.ts`; Agate API helpers are in
  `src/lib/api.ts`.
- Workspace and project navigation is sourced from Core access data.
- Organization administrators use the Settings hub for AI models, integrations,
  users, and Stylebooks.
- Current settings routes are `/settings/models` and `/settings/integrations`.
  Compatibility redirects remain active from `/admin/ai-models` and
  `/admin/integrations`.
- Stylebook administration is `/admin/stylebooks`; `/admin/catalogs` remains a
  compatibility redirect.

Apply the shared conventions in [`conventions.md`](conventions.md), especially the
product-copy and in-app-message rules.
