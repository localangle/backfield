# Backfield Public API Playground

`apps/api-playground` is the schema-driven developer client for browsing and exercising the public
API. It is served on tenant-specific domains such as
`https://playground.example-newsroom.backfield.news` (production) and
`https://playground.example-newsroom.stg.backfield.news` (staging).

The app infers the organization slug and environment from its own hostname and calls the matching
API origin (`https://api.{organization-slug}.backfield.news` or
`https://api.{organization-slug}.stg.backfield.news`). On localhost it automatically uses
`http://localhost:8004`. There is no organization or API-origin selector.

Agate and Stylebook link to the matching tenant Playground from their sidebar footer. Their
`VITE_PLAYGROUND_URL` build-time setting may override the destination for a fixed custom deployment
or use `{organization_slug}` as a host placeholder. Localhost builds use
`http://localhost:5176`.

## Visual language

The platform sidebar reuses the shared `@backfield/ui` components (`ShellSidebar`,
`AgateProductMark`, `StylebookProductMark`) and `lucide-react` icons, so it is the same sidebar
users see in Agate and Stylebook. Those shared components are styled with Tailwind, which the
Playground compiles with preflight disabled; the rest of the app keeps its standalone plain CSS
that mirrors the semantic color tokens, control dimensions, card treatment, product header, and
focus states used by Agate and Stylebook. HTTP method badges, monospace paths, and response code
blocks remain developer-tool-specific accents. The endpoint navigator groups and labels
operations to match the Backfield API docs nav (Projects, Metadata, Articles, Mentions, People,
Locations, Organizations, Other) and displays paths relative to
`/public/v1/projects/{project_slug}`; request construction still uses the exact OpenAPI path.
Every endpoint uses the same schema-first parameter UX: fields are organized into Project,
Resource, Search, Area, Filters, Sort and page, Response details, and Request options sections as
needed. Paired controls align consistently; types, defaults, required fields, and numeric limits
come from OpenAPI; and known values use date, number, checkbox, textarea, or select controls. Empty
optional controls are omitted from requests. Field help appears below its control and is reserved
for details that are necessary to complete the request; defaults remain in the control itself.
Every `project_slug` path parameter is a workspace-grouped dropdown populated from the signed-in
user's available projects, and the selected project carries across endpoint changes.
Canonical `person_id`, `organization_id`, and `location_id` fields use debounced typeahead controls
backed by their public search endpoints. Article and mention ID fields use the same pattern with
article and mention search; the selected result stores the API ID while showing a readable label
and context.
Geographic search and coverage endpoints include an interactive map for drawing bounding boxes or
choosing a point and radius. H3 detail and batch-query endpoints include a hex-cell picker with
named resolution tiers. Click toggles a cell, while Shift-drag highlights cells across the pointer
path. Highlighted cells stay listed in the request fields; selecting multiple cells on the single-
cell detail endpoint sends them through the batch geo-cells query instead.
When an operation supports `author`, `external_source`, mention nature, or entity-type filters,
selecting a project loads the matching discovery endpoint with the tab-scoped project API key and
populates dropdown choices. Every `meta` parameter uses the visual condition builder: each row
combines a metadata type, an is / is not operator, and a searchable category multi-select; rows
encode to the documented repeatable `meta` clause grammar shown in a live preview.
The semantic-search and geo-cell batch request bodies use the same structured field controls.
**Edit as JSON** remains available as a lossless escape hatch, and request-body properties are
validated against their OpenAPI constraints before the request is sent. The public trigger-run
operation remains in the API contract but is intentionally omitted from the Playground interface.

## Security boundary

- The public schema loads immediately without authentication so every endpoint can be browsed.
  A project API key is required only to execute requests and load project-scoped field choices.
- When available, the existing Backfield session cookie loads the signed-in organization,
  workspaces, and stylebooks for the shell and project selector. Schema browsing does not depend
  on that session.
- The project API key is held in React state and this tab's `sessionStorage`, so it survives a
  reload but is discarded when the tab closes. It is never put in local storage, cookies, URL
  state, analytics, request history, or third-party scripts. Public API requests omit browser
  credentials.
- When a tab-scoped key is present after a reload, the Playground automatically reloads the public
  schema and restores the selected endpoint, endpoint filter, and expanded endpoint groups. Endpoint
  groups start collapsed, and searching temporarily reveals matching endpoints. Once loaded, the
  connection form collapses to a compact schema status and reload/clear controls.
- The organization slug comes only from the Playground hostname. No organization selector, project
  slug, API key, request values, or response data is put in the URL.
- Closing the tab clears the key. **Clear key** removes it immediately.
- Generated curl uses `$BACKFIELD_PROJECT_API_KEY` instead of printing the entered key.
- The production build injects a restrictive Content Security Policy. `index.html` also sets
  `Referrer-Policy: no-referrer` through a meta policy, which works on any static host.
  Map tiles are loaded from `https://*.basemaps.cartocdn.com` (allowed in `img-src`).
- The production static host should send the same CSP and `Referrer-Policy: no-referrer` as HTTP
  response headers. The in-document policies remain a defense when an operator has not yet added
  host-level headers.

No request or response history is persisted.

## Local development

From the repository root, start the normal local stack:

```bash
make up
```

Open `http://localhost:5176`; the public schema loads automatically and can be browsed without
authentication. Apply a project API key when you want to execute requests. To run the app directly
(the shared `@backfield/ui` package needs its own install first):

```bash
cd packages/backfield-ui && npm ci
cd ../../apps/api-playground
npm ci
npm run dev
```

The local Core and Stylebook APIs must be available at `http://localhost:8004` and
`http://localhost:8003`.

## Validation and production build

```bash
make api-playground-test
make api-playground-build
```

The production bundle is written to `apps/api-playground/dist/`. Serve it on
`playground.{organization-slug}.backfield.news`; the bundle does not accept a configured or
user-entered API origin.
