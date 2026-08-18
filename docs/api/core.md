# Core API

Core API owns browser authentication, organization administration, project credentials, shared AI configuration, and the consumer-facing public API. It runs from `apps/core-api`.

Consumer routes under `/public/v1` are documented separately in [`public.md`](public.md). This page focuses on session and administration contracts under `/v1`.

## Authentication and tenancy

Core API issues and clears the signed `session` cookie through `/v1/auth`. A valid session carries
one organization and an organization role. Login issues a session immediately when the user has
one membership. With several memberships it returns organization choices and a short-lived,
single-purpose credential in an HttpOnly SameSite cookie; JavaScript never receives the signed
token. `/v1/auth/select-organization` exchanges and deletes that cookie before issuing a session.
The credential binds the user, allowed organizations, purpose, and expiry. There is no shared
durable nonce store in the current architecture, so a copied cookie value can be replayed until
expiry; successful exchange prevents replay in the same browser context by deleting the cookie.
Authenticated users switch with `/v1/auth/switch-organization`.

- Organization admins may administer all workspaces, projects, users, Stylebooks, and AI configuration in their organization.
- Members see projects in assigned workspaces plus any explicit project grants that remain in use.
- `SERVICE_API_TOKEN` is accepted by administration routes intended for automation and has
  cross-organization authority. Slug-based project operations require
  `X-Backfield-Organization-ID`; automation never receives an implicit organization.
- Project API keys use the `bfk_…` Bearer format only on documented `/public/v1` routes. Core's
  internal `/v1` routes reject them; those routes accept the intended browser session or trusted
  service token.
- Routes compare path and resource ownership with the authenticated organization or project. A caller cannot use an identifier from another tenant to widen access.

`GET /health` is unauthenticated. Bootstrap routes are deployment setup surfaces, not normal application APIs.

## Route families

### Session and current-user context

- `/v1/auth/login`, `/v1/auth/select-organization`, `/v1/auth/switch-organization`,
  `/v1/auth/me`, `/v1/auth/change-password`, and `/v1/auth/logout` manage browser sessions.
- Login trims and lowercases the submitted email for lookup. Ambiguous legacy rows that normalize
  to the same address receive the same generic invalid-credentials response as an unknown account.
- Login, organization-selection, and current-user responses expose `must_change_password`. A
  successful password change clears the flag set for newly provisioned temporary passwords and
  refreshes the session. While flagged, a session may use only organization selection,
  `/v1/auth/me`, `/v1/auth/change-password`, and logout; all product routes return
  `password_change_required`. Authorization reloads the current database flag rather than trusting
  session claims.
- Password changes reject the current password, apply the shared strength rules, and enforce
  bcrypt's 72 UTF-8 byte limit before hashing.
- `/v1/me/workspaces` returns the workspaces and nested projects visible to the signed-in user. Organization admins can see empty workspaces; members can see empty workspaces assigned to them.

These routes are session-oriented. Service tokens and project API keys do not substitute for a browser identity where a route requires one.
If the selected membership is removed, protected routes return `409` with
`detail.code="organization_selection_required"` instead of selecting another membership.

### Organization administration

Routes under `/v1/organizations/{org_id}` manage:

- organization display name;
- projects and Stylebooks available to administration screens;
- workspaces and their assigned Stylebooks;
- users, roles, and workspace or explicit project memberships.

Workspace membership replacement endpoints treat the submitted collection as the complete desired state. User disable and role changes protect the current user and the last organization administrator. Soft-disabled accounts keep their email reserved; organization admins can edit display name and role, and re-enable a user with `PATCH /v1/organizations/{org_id}/users/{user_id}` (`disabled: false`) instead of creating a duplicate account.

Workspace deletion is organization-admin only. `GET /v1/organizations/{org_id}/workspaces/{workspace_id}/delete-preview` returns rollup counts plus per-project tallies. `POST /v1/organizations/{org_id}/workspaces/{workspace_id}/delete` requires `{ "confirm_name": "<exact workspace name>" }`, runs the same project teardown for every project in the workspace, then deletes the workspace and its memberships. Shared Stylebook canonicals for the organization are kept.

Organization preferences live at `GET` / `PATCH /v1/organizations/{org_id}/settings`. Members and service tokens may read; only organization admins may write. The first preference is `map_default_viewport` (`lat`, `lng`, `zoom`), used as the empty-map fallback across Agate, Stylebook, and the API Playground when no geometry or selection already frames the map. Send `null` for `map_default_viewport` to clear it.

### Project credentials

Routes under `/v1/projects/{project_id}/api-keys` list, create, and revoke project API keys.

- Raw key material is returned only when a key is created.
- Members may create, list, and revoke only their own read-only keys for projects they can
  currently access.
- Organization admins may list and revoke every project key in their active organization.
- Service keys require organization-admin authority and may receive `runs:trigger`.
- Trusted service-token operators retain cross-organization key-management authority.
- Lists retain revoked-key metadata without returning key secrets.
- Every personal-key use reloads the owner, organization membership, project access, and project
  ownership. Disabling the owner or removing either membership immediately invalidates the key.
  Legacy ownerless personal keys fail closed. Ownerless `service` rows remain the explicit trusted
  automation-key form.

### AI models and integration secrets

Organization routes manage the AI model catalog, connection tests, default credentials, and encrypted integration secrets. Project routes expose the effective catalog, project availability, project credential overrides, and default role assignments.

Important contracts:

- Secret responses expose metadata only; plaintext and ciphertext are never returned.
- Custom model credentials must belong to the same organization as the model.
- Organization `curated-options` are flagship presets generated from LiteLLM's model catalog, not a
  hardcoded id list. Creating from `curated_id` still snapshots provider, model id, and capabilities
  onto the organization catalog row.
- Project overrides do not alter the organization catalog.
- Deleting a model or credential clears dependent selections while retaining historical AI call records without the removed foreign key.
- Secret writes require the configured master encryption key.

### Public API

Core API mounts project-key-authenticated reads and run triggering under `/public/v1`. Current families include projects, articles, mentions, locations, people, organizations, and runs. Public routes enforce the key's project binding and scopes; a project slug in the path does not override the credential's tenant.

The small `/v1/public/ping` compatibility path remains available. New consumer integrations should use `/public/v1`.

## Boundary responsibilities

Core API owns authentication and organization-facing administration, but it does not execute Agate graphs or manage editorial Stylebook candidates. Agate API owns graph and run control; Stylebook API owns canonical catalog and editorial entity operations.

Request and response models are validated at the HTTP boundary. Shared authorization, session, credential, and database behavior comes from `backfield-auth` and `backfield-db` rather than service-to-service authentication calls.
