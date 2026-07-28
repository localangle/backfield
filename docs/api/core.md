# Core API

Core API owns browser authentication, organization administration, project credentials, shared AI configuration, and the consumer-facing public API. It runs from `apps/core-api`.

Consumer routes under `/public/v1` are documented separately in [`public.md`](public.md). This page focuses on session and administration contracts under `/v1`.

## Authentication and tenancy

Core API issues and clears the signed `session` cookie through `/v1/auth`. A valid session carries one organization and an organization role.

- Organization admins may administer all workspaces, projects, users, Stylebooks, and AI configuration in their organization.
- Members see projects in assigned workspaces plus any explicit project grants that remain in use.
- `SERVICE_API_TOKEN` is accepted by administration routes intended for automation and has cross-organization authority.
- Project API keys use the `bfk_…` Bearer format. They are bound to one project and carry `read` and, for eligible service keys, `runs:trigger` scopes.
- Routes compare path and resource ownership with the authenticated organization or project. A caller cannot use an identifier from another tenant to widen access.

`GET /health` is unauthenticated. Bootstrap routes are deployment setup surfaces, not normal application APIs.

## Route families

### Session and current-user context

- `/v1/auth/login`, `/v1/auth/me`, `/v1/auth/change-password`, and `/v1/auth/logout` manage browser sessions.
- `/v1/me/workspaces` returns the workspaces and nested projects visible to the signed-in user. Organization admins can see empty workspaces; members can see empty workspaces assigned to them.

These routes are session-oriented. Service tokens and project API keys do not substitute for a browser identity where a route requires one.

### Organization administration

Routes under `/v1/organizations/{org_id}` manage:

- organization display name;
- projects and Stylebooks available to administration screens;
- workspaces and their assigned Stylebooks;
- users, roles, and workspace or explicit project memberships.

Workspace membership replacement endpoints treat the submitted collection as the complete desired state. User disable and role changes protect the current user and the last organization administrator.

### Project credentials

Routes under `/v1/projects/{project_id}/api-keys` list, create, and revoke project API keys.

- Raw key material is returned only when a key is created.
- User keys require a session and are read-only.
- Service keys require organization-admin authority and may receive `runs:trigger`.
- Revocation rules distinguish a user's own key from another user's key or a service key.

### AI models and integration secrets

Organization routes manage the AI model catalog, connection tests, default credentials, and encrypted integration secrets. Project routes expose the effective catalog, project availability, project credential overrides, and default role assignments.

Important contracts:

- Secret responses expose metadata only; plaintext and ciphertext are never returned.
- Custom model credentials must belong to the same organization as the model.
- Project overrides do not alter the organization catalog.
- Deleting a model or credential clears dependent selections while retaining historical AI call records without the removed foreign key.
- Secret writes require the configured master encryption key.

### Public API

Core API mounts project-key-authenticated reads and run triggering under `/public/v1`. Current families include projects, articles, mentions, locations, people, organizations, and runs. Public routes enforce the key's project binding and scopes; a project slug in the path does not override the credential's tenant.

The small `/v1/public/ping` compatibility path remains available. New consumer integrations should use `/public/v1`.

## Boundary responsibilities

Core API owns authentication and organization-facing administration, but it does not execute Agate graphs or manage editorial Stylebook candidates. Agate API owns graph and run control; Stylebook API owns canonical catalog and editorial entity operations.

Request and response models are validated at the HTTP boundary. Shared authorization, session, credential, and database behavior comes from `backfield-auth` and `backfield-db` rather than service-to-service authentication calls.
