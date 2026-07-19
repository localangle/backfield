# Deployment and production artifacts

## Support boundary

**Production self-hosting from this checkout is unsupported.** The Compose file, Make targets, and
CLI in this repository are for local development and for **building/publishing artifacts**. There is
no `make deploy` target and no deployment infrastructure under `infra/`.

A separate deployment system—outside this repository—may consume published manifests. That system is
responsible for runtime configuration, networking, secrets, migrations, seeding, and rollout. Do not
treat this document as a self-hosting runbook.

First administrators are created with `backfield seed` (or the seed step in `backfield init`). There
is no HTTP bootstrap endpoint and no environment-variable admin bootstrap path.

## What this repository implements

This repository builds and publishes production application artifacts:

- Linux/AMD64 OCI images for Agate API, Core API, Stylebook API, and the worker
- deterministic archives for the Agate and Stylebook static UIs
- an atomic JSON manifest that binds those artifacts to one source commit

A consuming deployment system must fetch a complete published manifest, configure the runtime
described in [runtime configuration](runtime-configuration.md), run migrations and seed tasks,
deploy the four image digests, publish the three UI archives, and configure origin routing.

## Production image builds

Docker Bake defines the production targets in `docker-bake.hcl`. Build from the repository root:

```bash
make docker-build-prod-apis \
  APP_VERSION=<immutable-version> \
  GIT_SHA=$(git rev-parse HEAD) \
  BUILD_TIME=$(git show -s --format=%cI HEAD)

make docker-build-prod-worker \
  APP_VERSION=<immutable-version> \
  GIT_SHA=$(git rev-parse HEAD) \
  BUILD_TIME=$(git show -s --format=%cI HEAD)
```

The Bake targets are `agate-api`, `core-api`, `stylebook-api`, and `worker`. They use the repository
root as build context, target each Dockerfile's `prod` stage, and build for `linux/amd64`.

The production API stages install non-editable packages and start Uvicorn without reload as a
non-root `appuser`. The worker starts Celery through `apps/worker/scripts/entrypoint.sh` (also
non-root in prod). Every image receives `APP_VERSION`, `GIT_SHA`, `BUILD_TIME`, and `LICENSE.md`.
APIs expose version metadata on `GET /version`, and the worker includes them in its startup log.

Agate API's production image also contains `backfield-migrate` and `backfield-seed` for one-off
tasks. Alembic assets are copied to `/app/packages/backfield-db`, with `BACKFIELD_ALEMBIC_ROOT` set
to that directory.

## Static UI builds

Build same-origin production bundles:

```bash
make ui-build
```

Outputs are written to:

- `apps/agate-ui/dist/`
- `apps/stylebook-ui/dist/`
- `apps/api-playground/dist/`

Vite loads each app's `.env.production`. The default browser paths are:

- `/v1` for Core API
- `/api/agate` for Agate API
- `/api/stylebook` for Stylebook API

The origin or CDN must route those paths to the matching API and serve `index.html` as the SPA
fallback. When the API receives a forwarded prefix rather than a stripped path, set
`BACKFIELD_HTTP_PATH_PREFIX` on that API.

Deploy the API Playground at `playground.{organization-slug}.backfield.news`. Configure wildcard
DNS, TLS, and static-host routing for those tenant domains. The app infers and calls the matching
`https://api.{organization-slug}.backfield.news` origin directly; set that tenant API’s
`PLAYGROUND_ORIGIN` to the exact Playground URL (do not rely on a global origin regex). Preserve
the Playground CSP and `Referrer-Policy: no-referrer` at the static host.

Serve hashed assets with a long cache lifetime and `index.html` with `Cache-Control: no-cache`.

## Artifact publication

After lint, tests, and required smoke pass on `main` in the canonical
`localangle/backfield` repository, the `publish-artifacts` CI job may:

1. derive the immutable version `main-<first-12-sha>-amd64`
2. build and push any missing image targets to ECR with SBOM and supply-chain attestations
3. wait for ECR scanning and block publication on critical findings
4. build all three UIs and create deterministic gzip archives
5. upload UI archives under `versions/<version>/ui/`
6. upload `manifests/<version>.json` last as the ready-to-deploy marker

New manifests use `schema_version: 2` and require four images plus three UI archives
(`agate-ui`, `stylebook-ui`, and `api-playground`). Historical `schema_version: 1` manifests retain
the two-UI inventory for rollback and SemVer aliasing. The manifest records schema version, source
SHA, build time, architecture, image tags/digests/URIs and scan counts, plus UI object keys,
checksums, and sizes. Consumers should deploy by digest and verify UI checksums. Release-alias
manifests retain the canonical-version UI `object_key` values; consumers must use those keys rather
than synthesizing paths from the SemVer alias.

Publishing is retry-safe: CI skips image tags already present, and the manifest is written only after
every required artifact is available and verified. Fork workflows do not publish artifacts.

## Release aliases

Pushing a tag matching `vX.Y.Z` runs the release-alias workflow. The tag must point to a commit on
`main`. The workflow does not rebuild images or UIs; it aliases the existing immutable manifest after
validating the source commit and artifact set.

Do not deploy an arbitrary mutable image tag or a partial artifact set. Use an immutable main version
or validated SemVer alias backed by a complete manifest.

## Sequence for a consuming deployment system

For an external deployment system only (not supported as in-repo self-hosting):

1. fetch and validate the selected artifact manifest
2. provision runtime secrets and connectivity (`SESSION_SECRET` required; no built-in default)
3. run `backfield-migrate` with `BACKFIELD_DATABASE_URL_DIRECT`
4. run `backfield-seed --admin-email … --admin-password-file …`
5. deploy the API and worker images by manifest digest
6. publish and checksum-verify the three UI archives, including the tenant API Playground host
7. configure `/v1`, `/api/agate`, and `/api/stylebook` routing, plus Playground DNS/TLS
8. set each tenant API `PLAYGROUND_ORIGIN` to that tenant’s Playground URL
9. check each API's `/health` and `/version`
10. run the applicable smoke checks against the deployed environment

`backfield seed` is idempotent: it ensures the organization and administrator exist, but re-runs do
not change an existing administrator's password or role.
