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
Additional complete organizations are created through the trusted host command
`backfield organization create`; see [organization provisioning](organization-provisioning.md).

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

Production (and shared `base`) stages use `python:3.11-slim-trixie` and explicitly install
`openssl` / `libssl3t64` from trixie-security (≥ `3.5.7-1~deb13u2`) before removing `perl-base`.
That clears ECR CRITICAL `CVE-2026-75803`; Debian bookworm still has no fixed openssl package, so
staying on `slim-bookworm` cannot pass the publish scan gate until a bookworm DSA ships.

The production API stages install non-editable packages and start Uvicorn without reload as a
non-root `appuser`. The worker starts Celery through `apps/worker/scripts/entrypoint.sh` (also
non-root in prod). Every image receives `APP_VERSION`, `GIT_SHA`, `BUILD_TIME`, and `LICENSE.md`.
APIs expose version metadata on `GET /version`, and the worker includes them in its startup log.

Agate API's production image also contains the generic `backfield` operator command plus the
compatibility `backfield-migrate` and `backfield-seed` entrypoints for one-off tasks. Use
`backfield organization create` from that image with `BACKFIELD_DATABASE_URL_DIRECT` for trusted
offline tenant provisioning. Alembic assets are copied to `/app/packages/backfield-db`, with
`BACKFIELD_ALEMBIC_ROOT` set to that directory.

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
fallback for document routes only. Do not rewrite API `404`/`403` responses to `index.html`
(CloudFront custom error responses apply to every origin, including `/api/*` and `/v1/*`).
When the API receives a forwarded prefix rather than a stripped path, set
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

Product releases use SemVer tags (`vX.Y.Z`). The workspace `pyproject.toml` version is an internal
monorepo stub and is **not** the product version.

The first public baseline is **`v0.8.0`**. Earlier tags such as `v0.0.1` are pre-history artifact
aliases only and are not advertised as product releases. Stay on `0.Y.Z` until you are ready to treat
the public API and upgrade path as a `1.0.0` stability contract.

### Cut a release

1. Choose a commit already on `main` whose CI `publish-artifacts` job has produced a complete SHA
   manifest (`main-<first-12-sha>-amd64`).
2. Pick the SemVer bump (from the current public baseline, starting at `v0.8.0`):
   - **patch** — fixes and small non-breaking changes (`0.8.0` → `0.8.1`)
   - **minor** — backward-compatible features (`0.8.0` → `0.9.0`)
   - **major** — breaking or ops-notable changes, or the jump to `1.0.0` when you are ready for a
     stability contract (for example migrations that need a coordinated upgrade)
3. Create and push an annotated tag:

```bash
git checkout main
git pull
git tag -a vX.Y.Z -m "Backfield vX.Y.Z"
git push origin vX.Y.Z
```

Pushing the tag runs the `Release` workflow, which:

1. Creates a GitHub Release (auto-generated notes plus a short deploy preamble). Re-running is
   idempotent if the release already exists.
2. Aliases the existing immutable artifact manifest to `vX.Y.Z` (when artifact publisher credentials
   are configured). Images and UIs are not rebuilt at tag time.
3. Launches a Cursor cloud agent against [`backfield-docs`](https://github.com/localangle/backfield-docs)
   to open a human-reviewed product-docs PR (changelog + targeted pages). Requires repository secret
   `CURSOR_API_KEY`. The agent must follow
   [release-update-contract.md](https://github.com/localangle/backfield-docs/blob/main/docs/meta/release-update-contract.md).
   Docs deploy only after that PR is merged. You can re-run docs sync alone via **workflow_dispatch**
   on the `Release` workflow with a tag input. See
   [`scripts/release_docs_agent/README.md`](../../scripts/release_docs_agent/README.md).

Do not deploy an arbitrary mutable image tag or a partial artifact set. Use an immutable main version
or validated SemVer alias backed by a complete manifest.

## Sequence for a consuming deployment system

For an external deployment system only (not supported as in-repo self-hosting):

1. fetch and validate the selected artifact manifest
2. provision runtime secrets and connectivity (`SESSION_SECRET` required; no built-in default)
3. run `backfield-migrate` with `BACKFIELD_DATABASE_URL_DIRECT`
4. run `backfield-seed --admin-email … --admin-password-file …`
5. run `backfield organization create …` once for each additional explicitly configured tenant
6. deploy the API and worker images by manifest digest
7. publish and checksum-verify the three UI archives, including the tenant API Playground host
8. configure `/v1`, `/api/agate`, and `/api/stylebook` routing, plus Playground DNS/TLS
9. set each tenant API `PLAYGROUND_ORIGIN` to that tenant’s Playground URL
10. check each API's `/health` and `/version`
11. run the applicable smoke checks against the deployed environment

This sequence assumes migrations are safe to apply before the new application starts. Upgrading an
existing environment across Alembic revisions `068`–`072` inverts that order for one revision;
follow the [organization tenancy upgrade runbook](organization-tenancy-upgrade.md) instead.

`backfield seed` is idempotent: it ensures the organization and administrator exist, but re-runs do
not change an existing administrator's password or role.
Complete organization provisioning is also idempotent for an exact input and fails atomically on
partial or conflicting state.
