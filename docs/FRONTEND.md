# Frontend

This document covers frontend conventions for `apps/agate-ui` and `apps/stylebook-ui`.

## Stylebook UI (Backfield)

- **Scope key (first slice):** the UI keeps **agate-ai-platform–style `project_slug`** in the query string (`?project=…`) as the primary navigation scope. `**stylebook-api**` resolves the slug to `backfield_project.id`. `**substrate_location**` rows are project-scoped place instances; the Stylebook **catalog** is `**stylebook_location_canonical`** (one row per editorial canonical), linked via `**substrate_location.stylebook_location_canonical_id**`.
- **Catalog scope (multiple Stylebooks per org):** each catalog is `**/stylebook/<stable-slug>/…`** (nested routes below). Legacy `**/?stylebook=<slug>**` and unprefixed `**/locations/…**` / `**/import/…**` URLs redirect into that prefix while preserving `**project_scope**` / `**project**` when present. Visiting a catalog without workflow scope (for example `**/stylebook/default`**) auto-adds `**?project_scope=<slug>**` (prefers a project whose slug is `general`, else the first visible project) so the shell sidebar, dashboard stats, and deep links match URLs that already carry scope. The sidebar picker navigates between slugs. The shared fetch helper reads the slug from the path (legacy query fallback) and mirrors it to Stylebook API calls as `stylebook_slug`. Agate **GET /projects** includes optional `**workspace_stylebook_slug`** so the hub can open the right catalog (Agate links use `**/stylebook/<slug>/**` plus optional `**?project=**` for the current project context). Stylebook may still use `**project_scope**` when workflow scope and evidence filter need different values (`project_scope` + `**project**`).
- **Canonical list ordering:** Stylebook `**GET /v1/stylebooks/{slug}/canonical-locations`** defaults to alphabetical `**label**` (case-insensitive, then `**id**`). With search (`q`), results rank by label match unless `**sort=recent**`, which orders by the latest of the canonical’s `**updated_at**` or any linked `**substrate_location.updated_at**` in the caller’s project scope (optional `**project**` narrows both counts and this activity signal). `**min_mentions**` filters to canonicals with at least that many non-deleted mentions in scope. The canonical list page shows each row’s **geography type** (canonical `**location_type`**, same PlaceExtract taxonomy as the Type filter—including **political district** for wards and numbered legislative districts) alongside status, linked place count, and mention count.
- **Canonical list URL state:** the Stylebook canonical list mirrors filters in the query string (`**q`**, `**type**` for PlaceExtract slug, `**sort**`, `**min_mentions**`, `**page**`) alongside `**project**` / `**project_scope**`. The filter panel includes a **Project** picker backed by `**project`** and defaults to **all projects** when unset; inherited workflow scope lives in `**project_scope`** so arriving from a project-scoped shell does not preselect the filter. Opening a canonical carries the same query on the detail route; the **Locations** breadcrumb and browser **back** restore the list with those filters.
- **First-slice routes (supported):** `**/`** redirects to `**/stylebook/<slug>/**` (dashboard); nested segments include `**locations/candidates**`, `**locations/canonical**` (lists `**GET /v1/canonical-locations**`; each row’s `**id**` is a **canonical UUID string**; the API may include a catalog `**slug`** but the Stylebook UI does not surface it), `/locations/canonical/:id` (`**:id**` is that UUID; detail uses `**GET /v1/canonical-locations/{id}**`, `**…/mentions**`, and `**GET …/linked-substrates**`), stylebook-scoped `**GET|POST /v1/stylebooks/{stylebook_slug}/canonical-locations/{id}/meta**` plus `**PATCH|DELETE …/meta/{meta_id}**` for catalog JSON metadata, stylebook-scoped `**GET|POST /v1/stylebooks/{stylebook_slug}/canonical-locations/{id}/connections**` plus `**PATCH|DELETE …/connections/{id}**` for the directed connections graph (and `**GET /v1/connections/stylebooks/{stylebook_slug}/natures**` for nature typeahead), `/locations/create` (creates a catalog canonical only via `**POST /v1/canonical-locations**` or legacy `**POST /v1/locations**` — **no** `substrate_location` row; navigate using the returned canonical `**id`**), `**/import/locations**` (GeoJSON FeatureCollection wizard: `**POST /v1/import/geojson/analyze**` then `**POST /v1/import/geojson**` with `mappings` plus optional top-level `**meta_property_mappings**` — an optional **Metadata** step maps `properties` keys to `StylebookLocationMeta.meta_type` per feature, persisting `**data`** as `**{ "<property_key>": <value> }**` so the metadata card can show Key / Value; skip sends `[]`), plus **stub** pages for other entity candidates, and agents so deep links do not 404. The canonical detail page includes **Metadata** (single card with **Add Meta** in the card header and per-entry **Edit** / **Delete** on each row) and **Connections** (single card with **Add connection** in the card header, then list + **reactflow** graph tab) aligned with agate-ai-platform; person / organization / work canonical pickers use **empty-list stub** APIs until those entities are migrated. Metadata **data** defaults to a **key / value table** when the stored JSON is a flat object with scalar values (strings, numbers, booleans, null); otherwise the UI shows formatted JSON. **Table** and **JSON** toggles let editors switch modes; the API still stores arbitrary JSON-serializable payloads.
- **Location candidates review queue:** `**/stylebook/<slug>/locations/candidates`** calls `**GET /v1/candidates**` with `**limit=100**`, `**offset**`, and the tab / type / search filters; the UI shows Previous/Next using `**total**`, `**has_next**`, and `**has_prev**`. Changing tab, type filter, or debounced search resets to **page 1**. The page subtitle and link/create dialogs state the two scopes explicitly: candidates are listed per **project**; linking and new canonicals target the **stylebook** from the URL (sidebar catalog).
- **Instance geometry dialog:** on the canonical detail linked-places table, **View geometry** opens **Instance Geometry** (map + collapsible **GeoJSON**, collapsed by default) and **Adopt for canonical** (dark button) to copy that instance’s geometry onto the catalog canonical. Linked-place rows include their source **project** so instance-level actions stay explicit even when the page is showing all projects.
- **Canonical detail scope:** the **Project** filter narrows mentions and linked-place rows, but **Metadata** and **Connections** stay stylebook-wide at the canonical level. Those sections should render and edit the same content no matter which projects currently reference the canonical.
- **Canonical linking (substrate vs catalog):** open candidates are `**substrate_location`** rows with `**canonical_link_status = pending**` and a **null** `stylebook_location_canonical_id`. The **Deferred** tab lists waived rows (`status=deferred`); list payloads may include `**defer_display_message`** when `**canonical_review_reasons_json**` carries a human-readable `**message**` from ingest or policy (for example **private place or residence**). The candidates table offers **Link to canonical**, which opens a modal: `**GET /v1/candidates/{substrate_location_id}/suggested-canonicals`** (ingest-style ranking; no scores in JSON) plus manual catalog search via `**GET /v1/canonical-locations?q=…**`, then confirm with `**POST /v1/locations/{substrate_location_id}/link-canonical**` (`{ "stylebook_location_canonical_id": "<uuid>" }`, idempotent `changed: false` when already on that canonical). The canonical detail page uses **one table** of linked places with article mentions nested under each place (mentions include `**substrate_location_id`** for grouping; the UI loads up to **500** mentions per canonical). **Unlink** is `**POST /v1/locations/{id}/unlink-canonical`** (returns row to the open queue; safe alias cleanup on the old canonical is server-side). **Move…** uses the same modal + link endpoint for atomic A→B relink. Legacy `**POST /v1/candidates/{id}/accept`** remains for “accept as new” / accept-by-id flows. **Create new canonical** opens a **dialog** to confirm or edit the catalog **label** (defaults from the substrate name), then posts `**{ "create_new": true, "name": "<label>" }`** to that accept route. `**POST /v1/candidates/{id}/accept**` returns `**message**` and `**stylebook_location_canonical_id**` (the canonical the substrate was linked to) so the UI can run the same `**GET /v1/candidates?project_slug=…&status=open&limit=100&offset=0&q=…**` preflight as “similar candidates” and link matches to that canonical from a follow-up dialog.
- **Auth:** Core API session only — `POST /v1/auth/login`, `GET /v1/auth/me`, `POST /v1/auth/logout` with `**email` + `password`**, same as Agate UI. Use `**VITE_AUTH_API_BASE**` as empty string in dev so the browser stays on the Stylebook UI origin and the Vite proxy forwards `/v1` to Core. `**GET /v1/auth/me**` includes `**org_role**`; organization admins see the same account-menu actions as Agate (**Change password**, **Manage users**, **Manage stylebooks**). Those links navigate to the Agate UI origin (`**VITE_AGATE_UI_ORIGIN`**, default `**http://localhost:5173**`) so `/account/password`, `/admin/users`, and `/admin/stylebooks` run in the Agate SPA with the shared session cookie when both apps are served from localhost (or the deployment maps sibling origins correctly). The legacy path `**/admin/catalogs**` redirects to `**/admin/stylebooks**`.
- **Proxies (local dev):** `[apps/stylebook-ui/vite.config.ts](../apps/stylebook-ui/vite.config.ts)` mirrors Agate UI:
  - `/v1` → Core API (`VITE_CORE_API_PROXY_TARGET`, default `http://localhost:8004`)
  - `/api/agate` → Agate API (`VITE_AGATE_API_PROXY_TARGET`, default `http://localhost:8000`), strip prefix
  - `/api/stylebook` → Stylebook API (`VITE_STYLEBOOK_API_PROXY_TARGET`, default `http://localhost:8003`), strip prefix
- **API bases:** `VITE_AGATE_API_BASE` defaults to `/api/agate` (`GET /projects` seeds the default `**?project=…`** when it is missing; the Stylebook shell header does not include a project picker). `VITE_STYLEBOOK_API_BASE` defaults to `/api/stylebook` (locations and UI-compat stubs under `/v1/...` on the Stylebook service). All fetches use `**credentials: 'include'**` so the Core session cookie is sent to the dev origin.
- **Client layout:** typed calls are split under `apps/stylebook-ui/src/lib/stylebook-api/` and re-exported from `src/lib/api.ts` for pages that still follow the agate-ai-platform import style.
- **Shell vs home heading:** the top bar `**ShellProductBrand`** title is always **Stylebook**. The dashboard main heading shows the **selected catalog** display name (same resolution as sidebar scope: org stylebooks + `**/stylebook/<slug>/`** / defaults), provided by `**StylebookScopeProvider**` in `Layout` and `useSelectedStylebookLabel()` on the home page.

## Agate UI review library (`src/lib/review/`)

Processed-item review helpers are grouped to match backend layout (`content/` vs `entities/location/` vs `overlay/`). Import from `@/lib/review/…` in components and pages.

| Area | Path |
|------|------|
| Article / item chrome | `review/content/` (`articleFields`, `detailTab`, `displayTitle`, `sourceDisplay`, `evidenceSpan`) |
| Location review | `review/entities/location/` (`placeGeometry`, `placeEditFields`, `mentionOccurrences`, `reviewRow`) |
| People review | `review/entities/person/` (`personEditFields`, `reviewRow`); `ProcessedItemPeopleVerificationSection`, `PeopleTable`, `PersonEditForm` |
| Overlay state | `review/overlay/verificationOverlay` |

See [`ENTITY_TYPES.md`](ENTITY_TYPES.md) for the full cross-repo map. Adding a new entity type later: add `review/entities/<type>/` when product ships that review UI.

## Agate UI responsibilities

- Render the **guided flow builder** and run experience (`/flow/new`, `/flow/:id/edit`, `/flow/:id`).
- Own browser-facing API access through `src/lib/api.ts`.
- Consume generated node registry output from `src/nodes/registry.ts`.
- Keep page and component code readable, explicit, and easy to scan.
- **Backfield Output — saved data policy:** The node panel owns the user setting for saved data reconciliation. Options are **Add Only** (“Adds new data from this flow without changing existing saved data.”), **Smart Merge** (“Updates data from this flow while preserving changes made by editors.”), and **Replace** (“Replaces existing saved data from this flow’s categories with this run’s results.”). The UI does not expose owned-domain overrides; backend/runtime inference is the source of truth.
- **Re-run / Run Again — current flow + policy:** Before **Rerun** (single item, bulk selection on run detail, or synthetic `items/1`), Agate UI shows a `showConfirm` dialog (`apps/agate-ui/src/lib/rerunWarning.ts`) titled **Rerun item?** (or **Rerun items?** for bulk). The copy says the current saved version of the flow will run, names the flow when available, states the Backfield Output policy, and says run-local review edits on the affected item(s) will be cleared. **Run Again** on run detail uses **Rerun all items?** with the same current-flow/policy summary. The dialog is destructive only when the policy is **Replace**.
- **Run detail — S3 batch setup:** While `total_items` is still **0** but the UI shows a placeholder row (`isRunPreparingItems` in `runPreparingItems.ts`), the **Source** column reads **Preparing items ...** and the **No Items Processed** empty state is hidden until real `agate_processed_item` rows exist.
- **Processed item Info tab:** **Item Information** shows story fields (**Source**, **URL**, **Headline**, **Author**, **Publication date**) as read-only text with a hover affordance; click a field to edit and save on the review overlay under `**article**` (merged over ingest input/output on load). Run timestamps and estimated AI cost sit below a divider; cost displays with two decimal places.
- **Processed item detail tabs:** the run item page (`**/runs/{runId}/items/{itemId}**`) keeps the active tab in the URL as `**?tab=<id>**` (`info`, `places`, `people`, `organizations`, `events`, `works`, `images`, `meta`, `json`). Invalid or missing values fall back to `**places**` (batch items) or `**info**` (single-input runs). A legacy `**#<tab>**` fragment on first load is promoted to `**?tab=**` for sharing.
- **Processed item JSON tab:** when the API returns **`reviewed_output`** (saved place or story review), the tab defaults to **Reviewed**; **Original** shows immutable run **`output`**. A single **Download** button exports whichever version is selected. When there is no reviewed output, only original output is shown.
- **Processed item Review (run item):** On wide viewports the **Places** tab uses a **viewport-capped two-column band**—a **Review and edit places** heading and short instructions above **story text** on the left (scrolls inside the pane) and a **compact map + geocoded-places table** on the right so the main page rarely needs vertical scroll. **Geocoded places** render in a dense table (name, type, address, **Actions**) for every merged model and user-added row, including **needs review** places with no map geography. Selecting a row highlights the story and zooms the map when geometry exists. The name-column source pill shows **No geography** when the row has no drawable geometry (failed geocode, cleared geometry, region-mismatch QA without a pin); otherwise it reflects **`geocode.geocode_type`** (and **`confidence.source`** when present). Assigning or changing geography on the map saves **`geocode_type: manual`** and clears model QA flags on the overlay patch. **Open Stylebook place**, **Adopt for Stylebook** (only when server **`geometry_differs`** and the story place has saved geography), **Find on map** (shown for rows with no drawable geography), and **Remove from story** (removes the row from review, soft-deletes mentions for this article; when no other stories use the saved place, unlinks from the catalog and deletes the substrate without adding an empty **candidates** row) live in **Actions**. Use **Stylebook** in user-facing copy (not “catalog”). The black **Edit** button on a selected place opens explicit **Save** / **Cancel** in the map toolbar (upper right), with add/clear geography tools on the left; the geocoded-places table is hidden while editing and the map expands into that space. While editing, the right pane uses **Map** and **Place details** tabs so the map keeps full height; **Place details** edits label, type (PlaceExtract taxonomy dropdown), formatted address, mentions in story, and role in story. The review band is slightly taller while editing. Review-only rows save to the run overlay; persisted rows save via Stylebook API to the story place (same **Save** label). Linked persisted rows show a notice under the map that Stylebook does not change until adopt. The map and merge lane use **geocoded** place rows when present (see `docs/API.md` → merged baseline and review enrichment); the **Visualizations** tab does **not** repeat a second locations map for Geocode nodes.
- **Processed item add place:** In the article pane, selecting story text shows a contextual **Add place** action and an accessible fallback button. The selected sentence or paragraph is locked into the right-side add inspector as the source passage; users can choose **Change selection** before saving. The text step requires **Place name**, **Type** (existing PlaceExtract taxonomy with human-readable labels), and **Mention in the story**. When the item has a linked saved story article (`article_id` from substrate context or upstream node output), continuing saves a normal story place through Stylebook API with no geography yet, appends a `locations.user_added` overlay row, refreshes the places list so the row appears as **Needs geography**, then opens the same map/details editor used by existing add/replace geography. When there is story text but no linked article (typical **JSON Output** runs without **Backfield Output**), continuing saves the place in the review overlay only (same list and map editor flow; not added to the location catalog until a saved article exists). Map saves for user-added places write geometry into ``locations.user_added`` (and mirrored ``by_anchor`` for preview); reviewed JSON materializes those coordinates onto ``json_output.consolidated.places`` when that is the only places bucket on the item. **Finish later** is represented by closing/canceling the map edit and resuming later from **Find on map** in the places table.
- **Processed item Review — People tab:** On wide viewports the **People** tab uses a **two-column band**—story text on the left and a **people table + edit form** on the right (no map). The table lists each merged person with name, title, affiliation, type, role in story, and link status. Selecting a row highlights the story and opens **Edit** for name, title, affiliation, type, and role in story. **Save** writes review-only rows to the run overlay under `people.by_anchor` / `people.user_added`; persisted rows save mention fields through Stylebook API (`PATCH /v1/people/{id}`). **Remove from story** soft-removes the row from review and deletes the substrate mention when a saved article exists. **Open Stylebook person** and **Review in Stylebook** link to the canonical detail or people candidates queue. Linked canonical rows show a notice that Stylebook canonical fields do not change from this tab until linked through the candidates flow. User-added people use `user_person:*` anchors in `people.user_added`. Reviewed JSON materializes overlay people onto `stylebook_output.people` and `consolidated.people` when present.

## Guided flow builder (Agate UI)

All create, edit, and run routes share one guided builder (`GuidedFlowBuilder.tsx` + `components/flow-builder/`). There is **no left node palette**, **no drag-to-connect**, and **no manual connection handles** on the canvas (`.guided-flow-canvas` hides React Flow handles in `index.css`).

### Stepper and bookends

- Three steps: **Choose an input** → **Choose an output** → **Build your flow** (`FlowStepper`, `flowBuilderSteps.ts`). On input/output steps the stepper is a compact text row (no card chrome). Each bookend chooser shows centered step copy with explainer text above the cards (`STEP_CHOOSER_COPY`: **Where will your input data come from?** / **Where would you like to save your output?**). On the scaffold step the stepper and page heading are hidden so the canvas uses the full height. Hover the source or destination node and use the swap control to open the bookend swap dialog (`BookendSwapDialog`) — middle steps stay in place when the new bookend type is compatible (`canReplaceInputBookend` / `canReplaceOutputBookend` in `flowGraphModel.ts`).
- **New flows** (`/flow/new`) start on the input step; **edit** (`/flow/:id/edit`) and **run view** (`/flow/:id`) open on **Build your flow** with bookends already complete.
- Input types: Text, JSON, S3. Output types: JSON Output, Backfield Output (`BookendChooser`, `flowBuilderDefaults.ts`).
- **Continue** on each bookend step is gated until required fields pass (`ConfigureGatePanel` + `canContinueBookendNode`).
- Changing a bookend **type** when middle steps exist shows a plain-language confirm via `useAppMessage`; confirm clears middle steps, cancel keeps the graph.

### Scaffold (“+” chain)

- Middle steps are added only via **+** on nodes (not on the output bookend) and **+** on serial edges (`GuidedFlowCanvas`, `AddNodeChooser`).
- Compatibility filtering uses synced `nodeMetadata` (`nodeCompatibility.ts`: port types + transitive `requiredUpstreamNodes`).
- **ConfigureGatePanel** opens after add; other **+** affordances stay disabled until **Continue**.
- Parallel branches fan vertically; serial steps extend horizontally (`flowGraphModel.ts` layout). The canvas **auto-layouts** on add, delete, and load (with recenter), and nodes can be **dragged** to adjust positions; dragged positions persist on save. New steps still get auto positions; existing dragged nodes keep their placement unless a full bookend relayout runs.
- Middle steps can be deleted with confirmation; the model rewires tips to output (`deleteMiddleNode`).
- The **+** chooser lists compatible middle steps only (no search field in v1; the scaffold catalog is small enough to scan).

### Run view vs edit

- **Run view** (`RunGraph.tsx`) embeds the guided builder in **read-only** mode: stepper navigation and node panels work; **+**, delete, and bookend change are off until **Edit flow**.
- **Run flow** starts a run without entering edit mode; run output appears in `NodePanel` / `RunPanel`.
- **Node panel:** Right-hand configuration uses the shared shell and tab model documented in **[Agate nodes and node panels](#agate-nodes-and-node-panels)** below. JSON Output has no settings tab—only **Output** after a run. Numeric fields users type freely (for example S3 max files per run) use a plain text input, not browser number spinners.
- **Edit flow** takes a snapshot; **Cancel** restores it; **Save** uses shared `validateGraphForSave` and `paramsForGraphSave`.

### UX reference patterns

Patterns borrowed from other products (behavioral parity, not visual clone):

| Pattern | Reference | Backfield |
|--------|-----------|-----------|
| **+** on nodes | n8n | Node **+** adds the next step; hidden in read-only run view |
| Node creator list | n8n | **+** chooser shows compatible steps only (no search in v1) |
| Read-only hides add controls | n8n | `getGuidedFlowCapabilities({ readOnly })` |
| Source / destination bookends first | Unstructured | Input → Output → Scaffold stepper |
| **+** on DAG | Unstructured | Branch and serial **+** on guided canvas |
| Valid layout before run | Unstructured | Save validation + single bookend rules |

**Out of scope (v1):** Unstructured-style **“Build it For Me”** one-click preset workflows — consider a follow-up quick-start template slice.

### Key modules

| Module | Role |
|--------|------|
| `pages/GuidedFlowBuilder.tsx` | Orchestration: stepper, bookends, scaffold state, save, run embed |
| `pages/RunGraph.tsx` | Run header, edit unlock, run polling; embeds guided builder |
| `lib/flowGraphModel.ts` | Topology, layout, hydrate/save spec |
| `lib/flowValidation.ts` | Shared save validation |
| `lib/guidedFlowCapabilities.ts` | Read-only vs edit affordances |

## Auth and API bases (Agate UI)

- **Core API (login / session):** `POST /v1/auth/login`, `GET /v1/auth/me`, `POST /v1/auth/logout`, `POST /v1/auth/change-password`. `GET /v1/auth/me` returns `organization_name` (publication / tenant display name). `GET /v1/me/workspaces` lists workspaces and visible projects for the signed-in user (used on `/`, `/workspace/:workspaceSlug`, and in the sidebar). Organization admin routes under `/v1/organizations/{org_id}/…` (users, workspaces, workspace rename, workspace memberships — admins can assign a user to **multiple** workspaces via `PUT …/workspace-memberships`). Use `**VITE_AUTH_API_BASE`** (empty string for same-origin). Typed fetch helpers live in `**src/lib/core-api.ts`** (session cookie, `credentials: 'include'`).
- **Project workspace — credentials:** (1) **API access keys** (`bfk_…`) are issued by Core API (`/v1/projects/{id}/api-keys`); the **API** tab uses `**core-api.ts`** helpers and `[ProjectAccessKeysPanel](../apps/agate-ui/src/components/ProjectAccessKeysPanel.tsx)` for Bearer access to Backfield APIs. (2) **Geocoding, search, and S3 overrides** for a project use Agate API `/projects/{id}/secrets` on the project **Integrations** tab (`**api.ts`**). Optional **LLM / Azure** project env keys still use the same Agate secrets API from the full **Project settings** dialog when present; prefer the **Models** tab and organization AI settings for LLM credentials.
- **Agate API:** project/graph/run calls go through `**src/lib/api.ts`**. Default `**VITE_API_BASE`** is `/api/agate` so the Vite dev server can proxy to `agate-api` on one browser origin with `credentials: 'include'`. New project workspace selection should match `GET /v1/me/workspaces`; Agate API rejects `workspace_id` values the session user is not allowed to assign (see `docs/API.md`).
- **Local dev proxy:** `[apps/agate-ui/vite.config.ts](../apps/agate-ui/vite.config.ts)` proxies `/v1` → Core API, `/api/agate` → Agate API, and `/api/stylebook` → Stylebook API (strip prefix). Override targets with `VITE_CORE_API_PROXY_TARGET`, `VITE_AGATE_API_PROXY_TARGET`, and `VITE_STYLEBOOK_API_PROXY_TARGET` (e.g. in Docker Compose).
- **Org admin — stylebooks (Agate UI):** organization admins open **Manage stylebooks** from the account menu (when the host passes `onManageCatalogs`), which routes to `**/admin/stylebooks`**. On that page they create or rename stylebooks, set the organization default, and remove stylebooks. **Who may edit** each stylebook (canonical locations and imports) is configured per user on `**/admin/users`** via **Stylebooks** (same pattern as **Workspaces**). Stylebook UI passes the same callback for org admins (full-page navigation to Agate; see Stylebook **Auth** bullet above). The pages call Stylebook API org routes via `**src/lib/stylebook-org-api.ts`** (default base `**/api/stylebook**`, same session cookie). After create/rename/default/remove on the stylebooks admin page, the UI dispatches `**agate:workspaces-changed**` so the hub sidebar can refresh workspace and stylebook context.
- **Org admin — Settings shell (Agate UI):** organization admins open **Settings** from the sidebar (`/settings`), which shows a **hub** of four stacked links: **AI models** (`/settings/models`), **Integrations** (`/settings/integrations`), **Users** (`/admin/users`), and **Stylebooks** (`/admin/stylebooks`). Each sub-page uses the **page name** as the main heading (`h1`) with a **breadcrumb** link (**Settings**) back to `/settings` (`SettingsScreenHeader`). `**/settings/integrations`** configures organization defaults for Geocode Earth, Geocodio, Brave Search, and Amazon S3 using Core `**PUT /v1/organizations/{org_id}/integration-secrets/{integration_key}**` with preset keys `platform.geocode.*`, `platform.search.*`, and `platform.storage.*` (see `docs/API.md`). Legacy `**/admin/integrations**` redirects to `**/settings/integrations**`.
- **Org admin — AI models (Agate UI):** organization admins open **AI models** from the account menu (`onAiModelsSettings`), which routes to `**/settings/models`** (legacy `**/admin/ai-models**` redirects there). The page includes **Provider credentials** (Core `**GET …/integration-secrets/ai-provider-catalog`**, `**PUT …/integration-secrets/{key}**`, `**DELETE**` — OpenAI, Anthropic, Gemini, OpenRouter, and Azure OpenAI API keys; secrets are write-only in the UI). Saved vendor keys from `**GET …/integration-secrets/catalog**` show **Update** and **Remove** for each row (**Remove** runs `**DELETE …/integration-secrets/{key}`** and drops **every** organization catalog model still linked to that credential, after confirmation). Multiple catalog models may reuse the same saved credential. Azure resource endpoints are saved under **project** Integrations (or bootstrap/env); see `docs/API.md`. **Model catalog** actions: **Add model** (presets from `**GET …/ai-models/curated-options`** or custom routing string + credential), **Edit** (status, capabilities, currency, optional usage prices for estimates — entered per **1 million tokens** in the UI, stored **per token** via Core API), **Test connection** (`POST …/ai-models/{id}/test-connection`), and **Remove** (`DELETE …/ai-models/{id}` — clears catalog row and project availability picks for that model). Calls use `**src/lib/core-api.ts`** against `**/v1/organizations/{org_id}/…**`.

## Shared UI package (`@backfield/ui`)

- Reusable shell components for multiple Backfield apps (Agate UI and Stylebook UI) live in `[packages/backfield-ui](../packages/backfield-ui)`.
- `**LeafletMap` geocoder:** optional `**geocoder`** prop shows a compact place/address search while editing geography. It uses the public **[Photon](https://photon.komoot.io)** API (OpenStreetMap data, no API key): viewport `**lat`/`lon`/`zoom`** bias and `**location_bias_scale**`, `**dedupe=0**` when the query contains digits (better house-level matches), a **global** `/api` retry if the biased search is empty, optional `**/structured`** fallback for `housenumber street, city` patterns, then **setView** / **fit bounds** without animation (avoids bad map clicks mid-transition) (Photon `extent` is `**[lon, lat, lon, lat]`** for two corners, not min/max ordered) plus a **non-interactive** temporary blue dot at the hit (cleared when the geocoder unmounts). Results do not change saved geometry by themselves.
- `**nodeOutputs`:** `@backfield/ui/nodeOutputs` holds the canonical mapping from graph topology + node types to `**execute_graph` output keys** (snake_case slugs, legacy keys, `__outputKeysByNodeId`). Agate UI imports it through `[apps/agate-ui/src/lib/nodeOutputs.ts](../apps/agate-ui/src/lib/nodeOutputs.ts)`. Synced `agate-runtime` panels use `@/lib/nodeOutputs` (resolved to that re-export) so parity copies stay aligned with `backfield-ui`’s package `**exports`** (no separate filesystem-relative path).
- **Tailwind:** add `../../packages/backfield-ui/src/**/*.{ts,tsx}` to the app’s Tailwind `content` array (see `[apps/agate-ui/tailwind.config.js](../apps/agate-ui/tailwind.config.js)`).
- **Exports:** `ShellProductBrand` (large product title + “Backfield Platform” subtitle, `Link` to home); `UserAccountMenu` (account icon + dropdown: signed-in email when `userLabel` is set, optional change password when `onChangePassword` is provided, optional manage users and manage stylebooks for org admins when the corresponding callbacks are provided, optional **AI models** when `onAiModelsSettings` is provided, log out). Navigation is via callbacks so hosts keep their own router.

## User-facing copy

- Write **every** user-visible string (labels, buttons, tooltips, placeholders, empty states, errors shown in the shell, onboarding, dialogs) for a **non-technical end user**: someone who uses the product to do editorial or operational work, not someone reading source code or RFCs.
- **Avoid technical or code-related language at all costs** in the UI: no stack traces, type names, JSON field paths, HTTP verbs or status codes, database or queue names, environment variable names, file paths, or “developer shorthand” unless you are deliberately building a **developer-only** screen (rare). Prefer plain English; if precision matters, describe the outcome (“We couldn’t save your changes”) not the mechanism.
- Write for a **general audience**, including people who are **not** developers.
- Avoid internal product names for infrastructure (services, ports, proxies, cookies, paths) unless the user must act on them—and even then, prefer plain language or hide details behind help links.
- Technical detail belongs in developer docs (this file’s other sections, `docs/API.md`, `docs/OPERATIONS.md`), not in labels, descriptions, or empty states shown to typical users.
- In Agate **Review** and cross-app handoff strings, prefer **Stylebook** (not “catalog”) for the organization’s canonical place library.
- **Review — mentions in story:** the place details editor shows a **Mentions in story** list (not a single “mention text” field). Use **Add mention**, **Remove mention**, and reorder controls; each row is one verbatim snippet. Clicking a mention selects it and highlights that span in the article. Say **mention** in UI copy, not “occurrence.”

## In-app messages (no browser `alert` / `confirm`)

- **Do not use** `alert()`, `window.alert`, `confirm()`, or `window.confirm` for user-visible notices or confirmations. They break visual consistency and are poor for accessibility.
- **Do use** the shared `**AppMessageProvider`** + `**useAppMessage()**` hook from each app’s `@/components/AppMessageProvider` (same implementation in `**apps/agate-ui**` and `**apps/stylebook-ui**`). The provider is mounted in each app’s root `**App.tsx**`, wrapping routes **inside** `**AuthProvider`** so every screen can call it.
- **API:**
  - `**showMessage(description, { title?, variant? })`** — single-action notice (OK). Default title is “Notice”; use `**variant: "destructive"**` (or `**showError**`) for failures.
  - `**showError(description, { title? })**` — shorthand for an error-styled notice (default title “Error”).
  - `**showConfirm(description, { title?, confirmLabel?, cancelLabel?, destructive? })**` → `**Promise<boolean>**` — two-action modal; resolves `**true**` when the user confirms, `**false**` on cancel or dismiss.
- Implementation uses the app’s existing **shadcn `Dialog`** primitives (`DialogContent` at `**sm:max-w-md**`) so copy matches the rest of the shell. Prefer this for `**catch**` blocks, validation messages, and destructive confirmations (revoke key, cancel run, delete geometry, etc.).

## Key conventions

- Prefer clear React components over clever abstractions.
- Extract repeated or dense logic into named helpers or smaller components.
- Keep API requests in `src/lib/api.ts` or similarly central helpers instead of scattering fetch calls.
- Keep storage keys and custom event names centralized and consistently prefixed.
- Reuse shared UI patterns instead of duplicating similar behavior per page.

## Agate nodes and node panels

Developer guide for adding or changing pipeline nodes in the guided flow builder. End-user copy rules still apply (**User-facing copy** above); this section is for implementers.

### Where files live

| Layer | Path | Edit here? |
|-------|------|------------|
| **Package (source of truth)** | `packages/backfield-agate/src/agate_nodes/<snake_case>/` | **Yes** — `metadata.json`, Python runtime (`node.py`, `runner.py`, …), `ui/*`, optional `prompts/` |
| **Synced UI copies** | `apps/agate-ui/src/nodes/<snake_case>/` | **No** — overwritten by `npm run sync-nodes` |
| **Generated registry** | `apps/agate-ui/src/nodes/registry.ts` | **No** — regenerated by sync |
| **Panel shell (app-only)** | `apps/agate-ui/src/components/NodePanel.tsx`, `components/node-panel/*` | **Yes** — shared chrome, tabs, field helpers |
| **Panel tab routing** | `apps/agate-ui/src/lib/nodePanelTabs.ts` | **Yes** — which tabs each node type shows |
| **Shared panel helpers** | `apps/agate-ui/src/lib/nodePanelAiModel.ts`, `flowValidation.ts` (bookend types) | **Yes** — reuse before copying logic into a panel |
| **Canvas chrome** | `apps/agate-ui/src/lib/nodeUtils.ts`, `nodeColors.ts` | **Yes** — icons and category colors from synced metadata |
| **Guided builder** | `apps/agate-ui/src/pages/GuidedFlowBuilder.tsx`, `components/flow-builder/` | **Yes** — bookends, **+** chooser, configure gate |

Runtime Python stays in the package; React panels are authored in `ui/` under the same folder so one PR can ship behavior + configuration UI. See [`ENTITY_TYPES.md`](ENTITY_TYPES.md) (Agate nodes) and [`.cursor/skills/add-entity-type/SKILL.md`](../.cursor/skills/add-entity-type/SKILL.md) for full-stack node work.

### Build and sync (`npm run sync-nodes`)

From `apps/agate-ui`:

```bash
npm run sync-nodes
```

- **`predev`** and **`prebuild`** run sync automatically.
- **`scripts/sync-nodes.js`** scans `packages/backfield-agate/src/agate_nodes/`, reads each `metadata.json`, and:
  - Copies `ui/NodeComponent.tsx`, `ui/PanelComponent.tsx`, `ui/VisualizationComponent.tsx`, and other `ui/*.ts(x)` helpers (for example `json_input/ui/schemaExample.ts`) into `apps/agate-ui/src/nodes/<folder>/`.
  - Inlines `prompt_file` / `output_format_file` from `defaultParams` into the generated registry metadata when those files exist.
  - Injects a `nodeMetadata` constant into copied Node/Panel files when missing (so panels can read defaults without importing the registry).
  - Writes **`src/nodes/registry.ts`** (`nodeMetadata`, lazy `nodeComponents`, `panelComponents`, `visualizationComponents`).

**Commit rule:** after changing package `metadata.json` or `ui/`, run sync and commit **both** the package tree and regenerated `apps/agate-ui/src/nodes/` (and `registry.ts`).

**Do not** hand-edit synced files under `apps/agate-ui/src/nodes/` except when you are changing the sync script itself.

### `metadata.json` contract

Each node folder includes a JSON descriptor consumed by the registry and compatibility layer:

| Field | Purpose |
|-------|---------|
| `type` | React Flow / executor type string (PascalCase, e.g. `PlaceExtract`) |
| `label` | User-facing name in panel header and chooser |
| `icon` | Lucide icon name (see `iconMap` in `nodeUtils.ts`) |
| `color` | Tailwind class on metadata (often `bg-*-500`); canvas/header also use **category** colors |
| `description` | Short paragraph under the panel title (`NodePanel`) |
| `category` | `input`, `output`, `extraction`, `enrichment`, … — drives `nodeColors.ts` |
| `dependencyHelperText` | Optional left-border hint under the description (omit on `GeocodeAgent`; it uses custom copy) |
| `requiredUpstreamNodes` | Transitive types required in branch ancestry (`nodeCompatibility.ts`) |
| `inputs` / `outputs` | Port ids, labels, and types for wiring and handle resolution |
| `defaultParams` | Initial node `data` in the graph editor |

Bookend types for the guided builder are fixed in `flowValidation.ts`: input `TextInput` | `JSONInput` | `S3Input`; output `Output` | `DBOutput`. Middle steps are everything else enabled in metadata.

### Canvas node (`ui/NodeComponent.tsx`)

Patterns used by synced nodes (match existing nodes when adding one):

- **React Flow** `NodeProps`, wrapped in `memo`.
- **Card** width `w-[280px]`; selected state `ring-2 ring-primary`.
- **Header:** `CardTitle` `text-sm font-medium`, icon in `w-6 h-6 rounded-full` with `getNodeBgColor(type)` and `getNodeIcon(type, 'h-4 w-4')`.
- **Preview body:** muted inset (`bg-muted`, `text-sm text-muted-foreground`) — keep summaries short; full editing lives in the panel.
- **Handles:** `Handle` with explicit `id` matching metadata port ids; positioned on the guided canvas edge (handles are hidden in CSS on `.guided-flow-canvas`; wiring is automatic).

Icons and colors come from synced metadata via `getNodeIcon` / `getNodeBgColor` (`nodeColors.ts` maps `category` and known type sets to `text-*-500` / `bg-*-100`).

### Side panel shell (`NodePanel.tsx`)

The app owns the right drawer; panels only render inner content.

| Element | Classes / behavior |
|---------|-------------------|
| Panel width | `w-96`, full height, `border-l`, `bg-background/95`, `backdrop-blur-sm` |
| Header | `p-4 border-b`; icon `h-9 w-9 rounded-full` + title `font-semibold text-lg` |
| Body scroll | `flex-1 overflow-y-auto p-4 space-y-4` |
| Description | `text-sm text-muted-foreground leading-relaxed` from metadata |
| Dependency hint | `text-sm text-muted-foreground border-l-2 border-muted pl-3` when `dependencyHelperText` is set |
| Tabs | Shown when `getNodePanelTabs` returns more than one id; `TabsList` grid with `text-xs sm:text-sm` triggers |
| Invalid connection | Amber callout above tabs when the builder passes `invalidConnectionMessage` |

`NodePanel` loads the synced lazy panel from `panelComponents[selectedNode.type]` inside `NodePanelTabProvider` + `Suspense`.

**`GraphPanelContext`** (passed from `GuidedFlowBuilder` / run view): `organizationId`, `projectId`, workspace Stylebook defaults, `fetchProjectAiModels(capabilities)`, and loading flags. Panels use this for org Stylebook lists and project AI model dropdowns—do not call Core API directly from panels except through existing helpers (`listOrgStylebooks`, `fetchProjectAiModels`).

### Panel tabs

Tab ids and labels are centralized:

- **Registry:** `apps/agate-ui/src/lib/nodePanelTabs.ts` — `NodePanelTabId`, `NODE_PANEL_TAB_LABELS`, `getNodePanelTabs(type, { hasRunOutput })`.
- **Gating:** each section in `PanelComponent.tsx` is wrapped in `<NodePanelTabGate tab="…">` from `components/node-panel/NodePanelTabContext.tsx` (renders children only when the active tab matches).

| Node type | Tabs (no run) | Extra when run has output |
|-----------|----------------|---------------------------|
| TextInput, S3Input | Settings | Output |
| JSONInput | Settings, Info | Output |
| PlaceExtract | Settings, Prompt, Output, Info | (Output tab always listed) |
| GeocodeAgent | Settings, Models | — |
| DBOutput | Settings, Stylebook | — |
| Output (JSON) | — | Output only |

When adding a tab for a new node type, update `getNodePanelTabs` and add matching `NodePanelTabGate` blocks in the package `ui/PanelComponent.tsx`, then sync.

### Typography and spacing (panel design system)

Agate UI uses the app **Inter/system stack** via Tailwind and shadcn—nodes do not define custom fonts.

| Role | Tailwind |
|------|----------|
| Panel title | `text-lg font-semibold` (shell) |
| Tab triggers | `text-xs sm:text-sm` |
| Field labels | `text-sm font-medium` — shadcn `Label` default; **do not** use `text-xs` or muted labels for primary fields |
| Required fields | `FieldLabel` (`components/node-panel/FieldLabel.tsx`) — red `*` + screen-reader “(required)” |
| Helper / hint under a field | `text-xs text-muted-foreground` |
| Section intro (Info tab, empty states) | `text-sm text-muted-foreground leading-relaxed` |
| Checkbox label beside control | `text-sm font-normal` |
| Compact selects | `SelectTrigger` with `className="text-xs"` where vertical space is tight |

**Layout inside a panel:**

- Top-level tab content: `space-y-4` between sections.
- Label + control group: `space-y-2`.
- Lists inside a section: `space-y-1` or `space-y-2` with `text-xs text-muted-foreground` for bullets.

### Colors and icons

- **Header/canvas icon color:** `getNodeIconColor` / `getNodeBgColor` from `nodeColors.ts` (category-based).
- **Metadata `icon`:** must exist in `iconMap` in `nodeUtils.ts` (extend the map when adding a new Lucide name).
- **Metadata `color`:** retained on metadata for parity; category mapping is what most nodes use on the canvas.
- **Destructive / validation:** `text-destructive` for load errors; invalid connection uses amber panel in the shell.

Prefer **Stylebook** in user-facing panel strings, not “catalog,” except when referring to the AI model list loaded from the project (internal code may still say `catalogRows`).

### `PanelComponent.tsx` patterns

Author in `packages/backfield-agate/src/agate_nodes/<node>/ui/PanelComponent.tsx`.

**Props:** declare only what the panel reads. `NodePanel` passes a common bundle, but TypeScript intersects panel prop types—avoid unused optional props on the interface.

| Prop | Typical use |
|------|-------------|
| `node` | `node.id`, `node.data` |
| `editMode` + `setNodes` | Required together for editable fields; `disabled = !(editMode && setNodes)` |
| `graphContext` | Stylebook + AI model catalog |
| `currentRun` + `nodeOutputLookupSpec` | Output tab previews (`getNodeOutputById`) |
| `onChange` | Text input only — optional callback alongside `setNodes` |

**Patching node data:**

```tsx
setNodes((nds) =>
  nds.map((n) => (n.id === node.id ? { ...n, data: { ...n.data, field: value } } : n)),
)
```

Merge defaults at the top: `const merged = { ...DEFAULTS, ...(node.data || {}) }`.

**AI model selects** (`PlaceExtract`, `GeocodeAgent`, Backfield Output adjudication): use `apps/agate-ui/src/lib/nodePanelAiModel.ts` — `catalogToSelectOptions`, `resolvedAiModelSelectValue`, `hasExplicitAiModelChoice`, `INVALID_AI_MODEL_SELECTION_VALUE`, and per-node `AiModelFieldKeys` constants. Load rows via `graphContext.fetchProjectAiModels([...capabilities])`. Show catalog **name** only in the UI; persist `provider_model_id` and optional `*_ai_model_config_id`.

**Stylebook id:** persist `stylebook_id` (snake_case). Read with `resolvedStylebookId` from `nodePanelAiModel.ts` (still accepts legacy `stylebookId` once).

**GeocodeAgent:** when **Use cache** is on, require a Stylebook selection (`stylebook_id`). Cache-off omits `stylebook_id`. Three model picks: routing, geographic reasoning, evaluation (see product copy in the panel).

**LLM catalog source:** Core `GET /v1/projects/{id}/ai-models/effective` only—no hard-coded model presets in panels. **Project → Models** tab uses `include_disabled=true` for admin availability (`docs/API.md`).

### Checklist: new or changed node UI

1. Add or update `packages/backfield-agate/src/agate_nodes/<snake_case>/` (`metadata.json`, Python, `ui/NodeComponent.tsx`, `ui/PanelComponent.tsx`).
2. Register tabs in `nodePanelTabs.ts` if the panel has multiple sections.
3. Reuse `nodePanelAiModel.ts` / `FieldLabel` / `NodePanelTabGate` instead of duplicating helpers.
4. Extend `iconMap` in `nodeUtils.ts` if using a new icon name.
5. Update `nodeCompatibility.ts` ports / `requiredUpstreamNodes` in metadata as needed.
6. Run `npm run sync-nodes` from `apps/agate-ui`.
7. Commit package **and** synced `apps/agate-ui/src/nodes/` output.
8. Add or adjust vitest coverage when tab routing or validation behavior changes (`nodePanelTabs.test.ts`, `flowValidation.test.ts`, …).

The default guided scaffold ships **PlaceExtract** and **GeocodeAgent** as middle steps; users add steps via the **+** chooser (no free-form palette).

## TypeScript expectations

- Prefer explicit types for props, API responses, and helper return values.
- Avoid `any` when a concrete type is easy to add.
- Keep file and symbol names descriptive.

## Frontend change checklist

- For new user-facing errors or confirmations, use `**useAppMessage**` (see **In-app messages** above), not browser dialogs.
- If API contracts changed, update `src/lib/api.ts`.
- If node metadata or node UI changed, follow **[Agate nodes and node panels](#agate-nodes-and-node-panels)** (edit package `ui/`, run `npm run sync-nodes`, commit synced output).
- If browser storage or custom events changed, keep prefixes and docs aligned.
- If a page or component became large, split it into smaller readable pieces.