# Backfield Public API Playground

`apps/api-playground` is the signed-in, schema-driven developer client served in production at
`https://playground.backfield.news`.

The app asks for an organization slug and derives exactly
`https://api.{organization-slug}.backfield.news`. When the playground itself runs on localhost, a
separate checkbox explicitly enables `http://localhost:8004`; there is no free-form API origin.

Agate and Stylebook link to the Playground from their sidebar footer and include the non-secret
organization slug so the Playground can restore the signed-in platform sidebar. Their
`VITE_PLAYGROUND_URL` build-time setting may override the destination for a custom deployment;
localhost builds use `http://localhost:5176`, and production defaults to the hosted URL above.

## Visual language

The Playground keeps its standalone CSS and dependency-light runtime, but mirrors the semantic
color tokens, control dimensions, card treatment, product header, and focus states used by Agate
and Stylebook. HTTP method badges, monospace paths, and response code blocks remain
developer-tool-specific accents. The endpoint navigator groups operations by resource and displays
paths relative to `/public/v1/projects/{project_slug}`; request construction still uses the exact
OpenAPI path.

## Security boundary

- The Playground uses the existing Backfield session cookie only to load the signed-in
  organization, workspaces, and stylebooks for its shell. Opening the app requires an active
  Backfield session.
- The project API key is React state only. It is never put in local storage, session storage,
  cookies, URL state, analytics, request history, or third-party scripts. Public API requests omit
  browser credentials.
- The organization slug may be carried in the URL as non-secret routing context. No project slug,
  API key, request values, or response data is put in the URL.
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

Open `http://localhost:5176`, select the explicit local API option, and load the schema. To run the
app directly:

```bash
cd apps/api-playground
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

The production bundle is written to `apps/api-playground/dist/`. Deploy it only at
`playground.backfield.news`; the bundle does not accept a configured or user-entered production API
origin.
