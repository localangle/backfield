# Agate UI — production static bundle

Build a same-origin bundle suitable for syncing to S3 (or any static host) behind CloudFront or another CDN.

## Build

From repo root:

```bash
make agate-ui-build
```

From this app:

```bash
make build-prd
# or: npm ci && npm run build
```

Production env defaults live in [`.env.production`](./.env.production):

- `VITE_API_BASE=/api/agate`
- `VITE_STYLEBOOK_API_BASE=/api/stylebook`
- `VITE_AUTH_API_BASE=` (empty — browser calls `/v1/...` on the same origin)

Override only when your routing layout differs (for example split hostnames):

```bash
VITE_AGATE_UI_ORIGIN=https://app.example.com \
VITE_STYLEBOOK_UI_ORIGIN=https://app.example.com \
make build-prd
```

Optional: `VITE_TIMEZONE=America/Chicago` (default in app code).

## Deploy

Backfield Cloud (or your operator) syncs `apps/agate-ui/dist/` to the static bucket:

- Long-cache hashed assets (`*.js`, `*.css`, …)
- `index.html` with `Cache-Control: no-cache` so SPA routing updates propagate

Path routing on the origin must forward:

- `/v1/*` → Core API
- `/api/agate/*` → Agate API (strip prefix)
- `/api/stylebook/*` → Stylebook API (strip prefix)
- all other paths → this SPA (`index.html` fallback)
