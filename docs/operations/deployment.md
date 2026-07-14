# Deployment and production artifacts

## What this repository implements

This repository builds and publishes production application artifacts:

- Linux/AMD64 OCI images for Agate API, Core API, Stylebook API, and the worker
- deterministic archives for the Agate and Stylebook static UIs
- an atomic JSON manifest that binds those artifacts to one source commit

Environment provisioning and rollout are not implemented in this checkout: there is no `make deploy` target and no deployment infrastructure under `infra/`. A deployment system must consume a complete published manifest, configure the runtime described in [runtime configuration](runtime-configuration.md), run migrations and provisioning seed tasks, deploy the four image digests, publish the two UI archives, and configure origin routing.

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

The Bake targets are `agate-api`, `core-api`, `stylebook-api`, and `worker`. They use the repository root as build context, target each Dockerfile's `prod` stage, and build for `linux/amd64`.

The production API stages install non-editable packages and start Uvicorn without reload. The worker starts Celery through `apps/worker/scripts/entrypoint.sh`. Every image receives `APP_VERSION`, `GIT_SHA`, and `BUILD_TIME`; APIs expose them on `GET /version`, and the worker includes them in its startup log.

Agate API's production image also contains `backfield-migrate` and `backfield-seed` for one-off tasks. Alembic assets are copied to `/app/packages/backfield-db`, with `BACKFIELD_ALEMBIC_ROOT` set to that directory.

Docker builds exclude optional large local geocoding databases through the root `.dockerignore`.

## Static UI builds

Build same-origin production bundles:

```bash
make ui-build
```

Outputs are written to:

- `apps/agate-ui/dist/`
- `apps/stylebook-ui/dist/`

Vite loads each app's `.env.production`. The default browser paths are:

- `/v1` for Core API
- `/api/agate` for Agate API
- `/api/stylebook` for Stylebook API

The origin or CDN must route those paths to the matching API and serve `index.html` as the SPA fallback. When the API receives a forwarded prefix rather than a stripped path, set `BACKFIELD_HTTP_PATH_PREFIX` on that API.

Serve hashed assets with a long cache lifetime and `index.html` with `Cache-Control: no-cache`.

## Artifact publication

After lint, tests, and smoke pass on `main`, the `publish-artifacts` CI job:

1. derives the immutable version `main-<first-12-sha>-amd64`
2. builds and pushes any missing image targets to ECR with SBOM and supply-chain attestations
3. waits for ECR scanning and blocks publication on critical findings
4. builds both UIs and creates deterministic gzip archives
5. uploads UI archives under `versions/<version>/ui/`
6. uploads `manifests/<version>.json` last as the ready-to-deploy marker

The manifest records schema version, source SHA, build time, architecture, image tags/digests/URIs and scan counts, plus UI object keys, checksums, and sizes. Consumers should deploy by digest and verify UI checksums.

Publishing is retry-safe: CI skips image tags already present, and the manifest is written only after every required artifact is available and verified.

## Release aliases

Pushing a tag matching `vX.Y.Z` runs the release-alias workflow. The tag must point to a commit on `main`. The workflow does not rebuild images or UIs; it aliases the existing immutable manifest after validating the source commit and artifact set.

Do not deploy an arbitrary mutable image tag or a partial artifact set. Use an immutable main version or validated SemVer alias backed by a complete manifest.

## Deployment sequence

For a consuming deployment system:

1. fetch and validate the selected artifact manifest
2. provision runtime secrets and connectivity
3. run `backfield-migrate` with `BACKFIELD_DATABASE_URL_DIRECT`
4. run `backfield-seed --admin-email … --admin-password-file …`
5. deploy the API and worker images by manifest digest
6. publish and checksum-verify the two UI archives
7. configure `/v1`, `/api/agate`, and `/api/stylebook` routing
8. check each API's `/health` and `/version`
9. run the applicable smoke checks against the deployed environment

`backfield seed` is idempotent: it ensures the organization and administrator exist, but re-runs do not change an existing administrator's password or role. Local environment bootstrap and `POST /v1/bootstrap/first-user` are not production provisioning mechanisms.
