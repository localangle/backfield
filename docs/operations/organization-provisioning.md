# Organization provisioning

Use the trusted host CLI to create a complete client organization. Provisioning connects directly
to the Backfield database/service layer through `BACKFIELD_DATABASE_URL_DIRECT` when configured;
there is no cross-tenant HTTP creation endpoint.

## Required inputs

Choose every tenant value explicitly. The command has no default organization, client, Stylebook,
workspace, project, or model selection:

```bash
backfield organization create \
  --organization-name "Acme News" \
  --organization-slug acme \
  --stylebook-name "Acme Stylebook" \
  --stylebook-slug acme-stylebook \
  --workspace-name "Acme Workspace" \
  --workspace-slug acme-workspace \
  --project-name "Acme Newsroom" \
  --project-slug newsroom \
  --client-admin-email admin@acme.example \
  --support-admin-email support@example.com \
  --temporary-password-file /secure/path/acme-temporary-passwords.json \
  --curated-model openai:gpt-5-nano \
  --curated-model openai:text-embedding-3-small \
  --json
```

Repeat `--curated-model` for each preset to snapshot. At least one model is required; the command
never selects all current presets or an implicit default. Preset identifiers are the same values
shown by the organization AI-model administration surface.

The temporary-password file is caller-owned JSON:

```json
{
  "client_admin_password": "replace-with-a-strong-temporary-password",
  "support_admin_password": "replace-if-the-support-user-is-new"
}
```

Create the file outside the repository with restrictive permissions. The client field is always
required. The support field is required only when `--support-admin-email` identifies a user that
does not already exist globally. Backfield reads but never creates, rewrites, deletes, prints, or
logs this file or its passwords.
Each password must satisfy the shared password policy and fit bcrypt's 72 UTF-8 byte limit.

## Transaction and rerun behavior

One transaction creates:

- the organization and its default Stylebook;
- the workspace and project, both directly assigned to that Stylebook;
- normalized globally unique users and visible `org_admin` memberships;
- exactly the selected curated AI model snapshot.

New users receive securely hashed temporary passwords and are marked to change them. Existing users
are attached by normalized email without changing their password or first-login state.
Flagged users may sign in and select an organization, but every application route except current
session details, password change, and logout remains blocked until the password is replaced.

An exact rerun reports and reuses the existing ids. If an organization slug already exists with a
different name, incomplete starter hierarchy, different ownership, missing or differently scoped
administrator, or different AI catalog configuration, provisioning fails and rolls back rather
than repairing or guessing. This strict check also means a rerun after independently changing the
organization AI catalog reports a conflict.

The current normalized email set of every `org_admin` membership must exactly equal the requested
client administrator plus the optional requested support administrator. Omitting a previously
requested support administrator, changing that address, or adding another administrator through
normal operations makes a later provisioning rerun conflict. The command never removes, replaces,
or silently adopts administrators.

Use `--json` for machine-readable output. Reports contain ids, slugs, selected model ids, and
created/reused state only; they never contain passwords or provider credentials.

## Credentials

Provisioning creates no AI, geocoding, search, or object-storage secrets. Shared provider
credentials remain deployment-level configuration. Organization and project overrides continue to
use the existing Settings and encrypted-secret mechanisms. Do not attach broad shared S3
credentials to a provisioned organization.
