# Stylebook API

Stylebook API owns editorial catalogs, saved entity evidence, candidate review, catalog cleanup, catalog transfer, and semantic mention search. It runs from `apps/stylebook-api`.

The current canonical domains are locations, people, and organizations.

## Authentication and tenancy

Routes accept the signed browser `session` cookie, `SERVICE_API_TOKEN` Bearer authentication, or a project-bound `bfk_…` API key. `GET /health` is unauthenticated.

Two scopes are used:

- Project-scoped routes take `project_slug`, resolve it to a project, and require project access. An optional `stylebook_slug` selects another Stylebook in the same organization; when omitted, the organization's default Stylebook is used (or its first Stylebook by id when none is marked default).
- Stylebook-scoped routes take `stylebook_slug` and require the Stylebook to belong to the authenticated organization. Reads follow the caller's catalog access. Writes require an organization admin, a Stylebook editor membership, or the service token. Project API keys cannot edit a Stylebook.

Organization library routes compare `org_id` with the session organization. The service token is allowed for automation across organizations.

## Catalogs and permissions

`/v1/organizations/{org_id}/stylebooks` lists, resolves, creates, renames, sets defaults, previews deletion, deletes, and manages Stylebook members.

- Slugs are stable catalog identifiers. Slug redirects keep renamed Stylebook URLs resolvable.
- Deleting a Stylebook requires explicit name confirmation.
- Deleting the default requires a replacement default.
- Workspaces pointing at a deleted Stylebook are reassigned to the effective default.
- `/v1/stylebooks/{stylebook_slug}/permissions` reports the caller's current catalog capabilities.

## Canonical entity families

Stylebook-scoped families under `/v1/stylebooks/{stylebook_slug}` provide list/search, type facets, detail, create, update, delete, linked saved entities, mentions, metadata, aliases, and connections as applicable:

- `/canonical-locations`
- `/canonical-people`
- `/canonical-organizations`

Canonical identifiers are UUID strings. Catalog responses expose immutable slugs for stable links. Project filters narrow mention and evidence counts without changing catalog ownership.

Location geometry uses GeoJSON `Point`, `Polygon`, or `MultiPolygon` with longitude-latitude coordinate order.

Canonical metadata is Stylebook-wide editorial data. Its rows retain a project association for storage and bundle transfer, but reads are not filtered to that project. Writes use the organization's first project as that association, so the organization must contain at least one project.

## Saved entities and candidate review

Project-scoped saved entity routes manage article evidence before or after a canonical decision:

- `/v1/locations` and `/v1/candidates`
- `/v1/people` and `/v1/people/candidates`
- `/v1/organizations` and `/v1/organizations/candidates`

Saved entities can be inspected, edited, linked or unlinked from a canonical, and removed from an article. Article-evidence create routes for each current domain validate selected quote offsets and create the saved entity, mention, and first occurrence together.

Candidate queues support open and deferred review, notes, context, suggested canonicals, recommendation clearing, acceptance into a new or existing canonical, and type facets. Location clustering is available in addition to the flat location queue.

Stylebook-scoped candidate AI review can evaluate open locations, people, or organizations. Starting a review queues work; status and cancellation routes expose cooperative progress. Recommendations do not mutate canonical links until accepted.

## Connections and metadata

Canonical location, person, and organization metadata is available on Stylebook-scoped routes. Connections can link current canonical domains and supported target types. Connection identifiers are serialized as strings so UUID-backed entities share one response contract.

Current Stylebook-scoped connection and nature routes are the primary catalog contract. Project-scoped canonical location metadata and connection paths remain supported compatibility contracts for callers that resolve catalog scope from `project_slug`.

## Imports, transfer, and cleanup

### Imports

Stylebook-scoped import routes analyze and import:

- GeoJSON locations;
- CSV people;
- CSV organizations.

Analysis returns detected input information before mutation. Imports allow partial success and report created and failed rows. Catalog write permission is required.

### Catalog transfer

Organization bundle-job routes export and import complete Stylebook catalog bundles asynchronously. Current bundles carry location, person, and organization canonicals and their catalog relationships, including aliases, metadata, and connections.

Bundles do not transfer project saved entities, candidate queues, caches, or activity history. Import upload and finalize are separate operations, and project mappings control project-scoped content such as metadata and connections.

### Cleanup

`/v1/stylebooks/{stylebook_slug}/cleanup` provides:

- available checks and asynchronous check runs;
- duplicate checks for locations, people, and organizations;
- missing-geometry and canonical/entity mismatch checks;
- questionable-person and questionable-organization checks with keep, delete, and bulk actions;
- merge and empty-canonical deletion actions for all current canonical domains;
- dismissal recording;
- optional AI review with proposal listing, acceptance, rejection, status, and cancellation.

Cleanup mutations require catalog edit access and preserve catalog tenancy.

## Activity, search, and dashboard stats

- `/v1/stylebooks/{stylebook_slug}/activity` returns a filtered, paginated catalog activity stream.
- Person and location semantic mention search ranks indexed article evidence within project scope and can filter by canonical, saved entity, mention, occurrence, and domain-specific fields.
- `/v1/stats` returns project-scoped canonical and pending-candidate counts for the Stylebook UI dashboard.
- `/v1/place-extract-location-types` exposes the shared location taxonomy used by extraction and catalog filters.

There is no HTTP geocode resolve endpoint and no Work API. Pipeline geocoding runs in the Agate worker (`geocode_agent`), not through Stylebook API. Canonical organization clients should use the Stylebook-scoped canonical organization family.
