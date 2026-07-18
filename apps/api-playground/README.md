# Backfield Public API Playground

`apps/api-playground` is the signed-in, schema-driven developer client served on tenant-specific
production domains such as `https://playground.example-newsroom.backfield.news`.

The app infers the organization slug from its own hostname and calls exactly
`https://api.{organization-slug}.backfield.news`. On localhost it automatically uses
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
The `/articles/search` form is the reference parameter UX: it groups related fields, aligns paired
controls, exposes schema types and numeric limits, and uses date, number, textarea, or select
controls when the accepted values are known. Empty optional controls are omitted from requests.
Every `project_slug` path parameter is a workspace-grouped dropdown populated from the signed-in
user's available projects.
On `/articles/search`, selecting a project loads its article facets with the in-memory project API
key and uses them to populate the `author` and `external_source` dropdowns. The `meta` parameter is
a visual condition builder: each row combines a metadata type (from the project's metadata
discovery endpoints), an is / is not operator, and a searchable category multi-select; rows encode
to the documented repeatable `meta` clause grammar shown in a live preview.

## Security boundary

- The Playground uses the existing Backfield session cookie only to load the signed-in
  organization, workspaces, and stylebooks for its shell. Opening the app requires an active
  Backfield session.
- The project API key is React state only. It is never put in local storage, session storage,
  cookies, URL state, analytics, request history, or third-party scripts. Public API requests omit
  browser credentials.
- The organization slug comes only from the Playground hostname. No organization selector, project
  slug, API key, request values, or response data is put in the URL.
- Refreshing or closing the tab clears the key. **Clear key** removes it immediately.
- Generated curl uses `$BACKFIELD_PROJECT_API_KEY` instead of printing the entered key.
- The production build injects a restrictive Content Security Policy. `index.html` also sets
  `Referrer-Policy: no-referrer` through a meta policy, which works on any static host.
- The production static host should send the same CSP and `Referrer-Policy: no-referrer` as HTTP
  response headers. The in-document policies remain a defense when an operator has not yet added
  host-level headers.

No request or response history is persisted.

## Local development

From the repository root, start the normal local stack:

```bash
make up
```

Open `http://localhost:5176` and load the schema. To run the app directly (the shared
`@backfield/ui` package needs its own install first):

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
