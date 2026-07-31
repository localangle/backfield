# Organization tenancy upgrade

One-time upgrade runbook for the organization-tenancy release: Alembic revisions `068` through
`072`. It replaces the usual migrate-then-deploy order for this upgrade only. Retire this page once
every retained environment has passed `072`.

This is written for a consuming deployment system. See the support boundary in
[deployment](deployment.md); nothing here makes in-repo self-hosting supported.

## What changes

| Revision | Change | Safe alongside pre-upgrade code? |
| --- | --- | --- |
| `068_s3_ledger_project_scope` | S3 ingestion ledger uniqueness and `ix_agate_s3_ingestion_ledger_source_item` gain `project_id` | Yes, until project-scoped writers create duplicates |
| `069_project_stylebook_ownership` | Adds nullable `backfield_project.stylebook_id`, backfills it, creates `General` workspaces for orphans | Yes, but aborts on multiple default Stylebooks, a missing Stylebook, or a mismatched `General` workspace |
| `070_project_stylebook_runtime` | Makes `workspace_id` and `stylebook_id` required; adds composite foreign keys and the unique constraints they need | **No.** Older writers insert NULLs, which both violate the constraint and block the migration |
| `071_project_org_slug_scope` | Replaces global `UNIQUE(project.slug)` with `UNIQUE(organization_id, slug)`, plus two indexes | **No.** Organization-qualified readers must already be live |
| `072_user_password_change_flag` | Adds `must_change_password` | Yes, but the release build *requires* it |

Behavior changes operators should expect afterward:

- Users with several organization memberships must choose an organization at sign-in.
- Browser routes become `/org/:orgSlug/...`, with authenticated redirects from legacy paths for one
  compatibility window.
- Project `bfk_` keys authenticate `/public/v1` only. User-owned keys revalidate owner, membership,
  and project access on every request; service keys are validated as ownerless credentials.
- Provisioned users must replace their temporary password before reaching any other route.

## Why the order is unusual

`071` is an explicit exception to the normal migrate-before-application sequence. Relaxing the
global slug constraint while an old reader still resolves projects by bare slug lets that reader
select another organization's project. `068` has the same shape once duplicates exist: a reader that
ignores `project_id` can match the wrong ledger row.

`070` pulls the other way. Application code that writes projects without a workspace and Stylebook
starts failing the moment it lands, and a NULL row written between `069` and `070` will block `070`
from running at all.

Those constraints only conflict during a **rolling** deploy, where old and new code serve
simultaneously. With a maintenance window there is no overlap, and a single image plus a single
migration run satisfies all of them. Prefer the window unless an environment genuinely cannot take
one.

## Preflight

Run the read-only audit against the target database. It works before `069` adds its column:

```bash
backfield tenancy-audit --json
```

Exit `1` means blockers; exit `2` means the audit could not run. Stop on either. Resolve every
blocker before continuing — `070` performs its own hard-stop validation and refuses to run on the
first project or workspace with a null, missing, or cross-organization assignment. That check is
narrower than the audit, which also catches graph Stylebook conflicts, linked-canonical mismatches,
and duplicate slugs. Neither guesses a replacement catalog; repair the rows and rerun rather than
forcing the migration.

Two connection details differ between the commands here, and getting them wrong is quiet rather
than loud:

- `backfield tenancy-audit` reads **`BACKFIELD_DATABASE_URL`** (then `DATABASE_URL`). It does *not*
  read `BACKFIELD_DATABASE_URL_DIRECT`, and falls back to a localhost default, so a task configured
  only with the direct URL will audit the wrong database or fail to connect.
- `backfield-migrate` and `backfield organization create` prefer **`BACKFIELD_DATABASE_URL_DIRECT`**.

All three commands ship only in the **Agate API** image, which also sets
`BACKFIELD_ALEMBIC_ROOT=/app/packages/backfield-db`. The Core API, Stylebook API, and worker images
do not include the CLI.

Also confirm before starting:

- a verified database backup
- the current `alembic_version.version_num`. `backfield-migrate` upgrades to **head**, not to `072`,
  so an environment below `068` also gets every other pending revision. If the current revision is
  before `019_sb_loc_canon_uuid`, stop and read the destructive warning in
  [migrations](migrations.md) first — that revision does not preserve location canonical rows.
- the selected artifact manifest validates, with all four images and three UI archives
- `SESSION_SECRET` is configured (there is no built-in default)

## Upgrade with a maintenance window

Recommended for every environment that can take a few minutes of downtime.

1. Announce the window and run the preflight audit. Stop if it exits non-zero.
2. Back up the database.
3. Stop accepting new runs and let in-flight worker tasks drain.
4. Stop the worker, then the APIs. Nothing that reads projects or the S3 ledger may still be
   running — this is what makes the ordering constraints moot.
5. Run migrations as one task: `backfield-migrate` with `BACKFIELD_DATABASE_URL_DIRECT`. This applies
   `068` through `072` in one pass. Do not let several services race the same database.
6. Deploy the API and worker images by manifest digest, and publish the three UI archives.
7. Start the APIs, then the worker.
8. Check `/health` and `/version` on each API.
9. Run the applicable smoke checks.

`069`, `070`, and `071` take brief ACCESS EXCLUSIVE locks on `backfield_project`, and `070` also
locks `stylebook` and `backfield_workspace`. That is not a concern inside a window, and is
negligible at current table sizes.

Post-upgrade verification, beyond the standard smoke lanes:

- sign in as a single-organization user and confirm a normal session
- sign in as a multi-organization user and confirm the organization chooser, then switch
  organizations and confirm no prior-organization data remains visible
- confirm a legacy unprefixed URL redirects to its `/org/:orgSlug/...` equivalent
- confirm a project API key still works against `/public/v1` and is rejected by the internal APIs

## Upgrade without downtime

Only if an environment cannot take a window. **This path is not supported by the repository's
tooling** and needs two application builds plus manual revision targeting. Read this whole section
before starting.

Two facts drive the shape:

- The Alembic chain is linear, so `072` cannot be reached without passing through `071`.
- The release build reads `must_change_password` on every session resolution, so it cannot run
  against a database stopped at `070`.

Together these rule out "everything except `071`". The workable split needs a pinned intermediate
version: commit `85e16858` ("Add explicit organization sessions and scoped routes"). That build
introduced organization-qualified readers and writers, does not yet reference
`must_change_password`, and by design tolerates the old global slug constraint — a colliding create
returns a temporary-unavailability `409` rather than a server error. It predates this release's
version tag, so select its main-commit manifest rather than a SemVer alias.

1. Apply `068` and `069` only. Both are safe alongside the running pre-upgrade code.
2. Deploy the pinned intermediate build. Drain and replace every old API and worker task, and verify
   none remain.
3. Repair the drain window before going further. Between steps 1 and 2, pre-upgrade code was still
   creating projects with no workspace or Stylebook. Those rows make the intermediate build return
   `500` when it reads them, and they will block `070`. Rerun `backfield tenancy-audit` after the
   drain and fix everything it reports.
4. Apply `070`. It must come after old writers are gone *and* after step 3, since rows written
   earlier in the window still exist.
5. Apply `071` and `072`.
6. Deploy the final release build.

Do not create cross-organization duplicate project slugs before step 5 completes. Note that these
migrations take write-blocking locks: `070` holds ACCESS EXCLUSIVE on `backfield_project`,
`stylebook`, and `backfield_workspace`, and its foreign keys are added validated, so they scan those
tables. Brief at current sizes, but not free.

`backfield-migrate` always upgrades to head and takes no revision argument, so the partial steps
need Alembic directly. Run this from the Agate API image, which has `alembic` installed and
`BACKFIELD_ALEMBIC_ROOT` set, and reuse the repository's own config builder so `script_location`
resolves the same way:

```bash
python -c "from alembic import command; \
from backfield_db.migrate import build_alembic_config; \
command.upgrade(build_alembic_config(), '069_project_stylebook_ownership')"
```

Substitute the target revision for each step. This resolves `BACKFIELD_DATABASE_URL_DIRECT` through
`alembic/env.py` exactly as `backfield-migrate` does, so the same connection guidance applies. Use
`backfield-migrate` for the last migration so the database ends at head.

## Tenants and first sign-in

After the upgrade, provision each additional client organization from the Agate API image:

```bash
backfield organization create … --temporary-password-file /secure/path/passwords.json --json
```

Provisioning is atomic and idempotent for an exact input, and fails without changing anything on
partial or conflicting state. See [organization provisioning](organization-provisioning.md) for the
full input contract, password-file format, and rerun rules. New administrators must replace their
temporary password before any other route becomes available.

## Rollback

Forward repair is strongly preferred. Alembic unwinds in reverse (`072`, `071`, `070`, `069`,
`068`), and three revisions constrain going backward:

- Downgrading `071` stops if cross-organization duplicate project slugs already exist. Application
  rollback is unsafe from the moment duplicates are created, and this guard halts the unwind before
  any later step runs.
- Downgrading `069` **drops** `backfield_project.stylebook_id`. Because projects may be created with
  a Stylebook that differs from their workspace default, those choices cannot be reconstructed from
  `workspace.stylebook_id`. This is the only step that loses data.
- Downgrading `068` recreates the global ledger constraint and fails if rows differing only by
  project already exist.

If an upgrade fails before any of those rows exist, restore the backup and rerun the preflight audit.
