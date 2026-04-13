# Flowbuilder UI

React/TypeScript frontend for the Agate flow builder: visual pipeline editor, runs, and project management. Talks to Flowbuilder API and Auth API.

## Local development

From repo root with Docker:

```bash
make up   # includes flowbuilder-ui
```

Or run the UI only (with APIs available):

```bash
make dev-ui
# or: cd apps/flowbuilder-ui && npm run dev
```

- **UI**: http://localhost:5173  

Default API base URLs are set for local (see `apps/flowbuilder-ui/Makefile` for build env vars).

## Make commands (from repo root)

| Command | Description |
|---------|-------------|
| `make dev-ui` | Run Flowbuilder UI dev server |
| `make build-flowbuilder-ui-prd` | Build production bundle (set `VITE_API_BASE`, `VITE_AUTH_API_BASE`) |
| `make deploy-flowbuilder-ui-prd` | Sync dist to S3 and invalidate CloudFront |

## Production

See [DEPLOY.md](./DEPLOY.md) for building and deploying to S3/CloudFront.
