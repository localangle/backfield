# Agate UI

React/TypeScript frontend for the Agate flow builder: visual pipeline editor, runs, and project management. Talks to Agate, Stylebook, and Core APIs through same-origin paths in production.

## Local development

From repo root with Docker:

```bash
make up   # includes agate-ui on :5173
```

Or run the UI only (with APIs available):

```bash
cd apps/agate-ui && npm run dev
```

- **UI**: http://localhost:5173
- **APIs (dev proxy)**: `/v1` → Core API, `/api/agate` → Agate API, `/api/stylebook` → Stylebook API

## Production build

From repo root:

```bash
make agate-ui-build
```

Or from this directory:

```bash
make build-prd
```

The bundle uses relative API bases (`/api/agate`, `/api/stylebook`, `/v1` for auth) so one build serves every client behind a path-routing origin. Output is written to `dist/`.

See [DEPLOY.md](./DEPLOY.md) for deployment notes.
