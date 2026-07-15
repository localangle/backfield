# Stylebook frontend

`apps/stylebook-ui` is the editorial UI for Stylebook canonicals, project-scoped
candidate queues, imports, and data-quality review.

## URL and scope contracts

Every Stylebook is addressed by a stable path:

```text
/stylebook/<stylebook-slug>/...
```

The path slug is mirrored to Stylebook API requests as `stylebook_slug`.
Project scope has two distinct query keys:

- `project_scope` carries workflow and shell context.
- `project` filters evidence, mentions, and linked substrate rows.

Canonical metadata and connections are Stylebook-wide and must not change when the
project evidence filter changes. When a canonical list receives `project` without
`project_scope`, it promotes the inherited value to `project_scope` and clears the
filter so arriving from an Agate project does not accidentally prefilter the list.

Canonical list state is URL-backed. Shared keys are `q`, `type`, `sort`,
`min_mentions`, `page`, `project`, and `project_scope`. People additionally use
`public_figure`, `title`, and `affiliation`. Filters are applied server-side before
pagination. Detail links carry the current query so breadcrumbs and browser back
restore the list.

## Active compatibility redirects

Keep these redirects unless a separate migration removes their consumers:

- `/` and `/?stylebook=<slug>` → `/stylebook/<slug>`
- unprefixed location, people, and organization list, detail, create, candidate, and
  import routes → the equivalent `/stylebook/<slug>/...` route
- `/import` → `/stylebook/<slug>/import/locations`
- unprefixed `/works/candidates` and `/agents/:agentType` → their prefixed stubs
- unknown protected routes → `/stylebook/default`

Redirects remove the legacy `stylebook` query parameter and preserve the other
query parameters.

## Current entity routes

Locations, people, and organizations each have implemented candidate, canonical
list, detail, and create routes:

```text
/stylebook/<slug>/<locations|people|organizations>/candidates
/stylebook/<slug>/<locations|people|organizations>/canonical
/stylebook/<slug>/<locations|people|organizations>/canonical/<uuid>
/stylebook/<slug>/<locations|people|organizations>/create
```

Imports are GeoJSON for locations and CSV for people and organizations:

```text
/stylebook/<slug>/import/locations
/stylebook/<slug>/import/people
/stylebook/<slug>/import/organizations
```

Works and agent routes remain UI stubs. Work has no backing API or editorial surface and is
omitted from the home cards.

## Shared entity shells

Per-type pages are thin wrappers around shared shells and
`src/lib/entityConfigs/<type>/`:

```text
apps/stylebook-ui/src/
  components/
    CandidateQueuePage.tsx
    CanonicalLinkModalGeneric.tsx
    CanonicalListPage.tsx
    CanonicalDetailLayout.tsx
    CanonicalMentionsSection.tsx
    LocationGeographySection.tsx
  lib/
    useCandidateQueuePage.ts
    useCanonicalListUrlState.ts
    entityRegistry.ts
    entityTypes.ts
    entityConfigs/
      candidateQueueTypes.ts
      canonicalLinkModalTypes.ts
      canonicalListTypes.ts
      canonicalDetailTypes.ts
      connectionPickers.ts
      location/
      person/
      organization/
  pages/
    LocationCandidates.tsx
    PersonCandidates.tsx
    OrganizationCandidates.tsx
    Locations.tsx
    People.tsx
    Organizations.tsx
    LocationDetail.tsx
    PersonDetail.tsx
    OrganizationDetail.tsx
```

Each implemented type supplies `candidateQueue`, `canonicalLinkModal`,
`canonicalList`, and `canonicalDetail` configuration. Import and create forms stay
as type-specific pages while sharing their common shells and form classes.

## Candidate queues

Candidate queues are project-scoped; link and create actions target the Stylebook
in the path. The shared shell provides:

- Open and deferred queues with server-side filtering and pagination.
- Product-readable review reasons and inline editor notes.
- Suggested-canonical lookup plus manual Stylebook search.
- Create-new confirmation with a similar-canonical warning.
- Link, create, and defer recommendations from AI review.
- Incremental AI-review polling and bulk acceptance.
- Post-action notices and an optional related-candidates follow-up.

Location, person, and organization pages all use this shell. New types must extend
the configuration seams instead of copying a page body.

## Canonical lists and details

Canonical lists share search, project, minimum-mention, sort, and pagination
behavior. Type-specific filters live in the list configuration.

Each canonical detail page uses this section order:

1. Details
2. Geography for locations only
3. Mentions grouped by linked substrate row
4. Metadata
5. Connections

Mentions respect the project filter. Metadata and connections remain
Stylebook-wide. Move/link dialogs exclude the source canonical. When unlinking the
last evidence leaves an empty canonical, the shared delete prompt is used. Do not
show canonical status in the detail card.

## Stylebook Review

The Stylebook home and `/cleanup` routes share **Entities** and **Review** tabs.
Review runs are explicit: opening the page does not start work. The hub shows
durable run state, issue count from the latest successful run, and last-run
freshness. A row starts its check, then polls the latest run until completion.

Implemented checks cover:

- duplicate and geography-quality checks for locations;
- duplicate and mismatched-record checks for people;
- duplicate and mismatched-record checks for organizations;
- questionable person and organization canonicals, with individual and bulk keep/delete actions.

Duplicate review supports merge, delete-empty, and keep-separate decisions.
Dismissals are durable. AI review can propose the same merge or dismissal actions;
accepting a proposal uses the same backend operations as manual review. Every
flagged item links to its canonical detail page.

## Cross-app navigation

Agate builds Stylebook links through `apps/agate-ui/src/lib/platformUrls.ts` and
passes the selected workspace Stylebook slug plus optional project context.
Stylebook workspace and project links return to Agate through its own platform URL
helpers. Leave origins unset for same-origin deployment or set the paired
`VITE_*_UI_ORIGIN` values for sibling hosts.

Apply [`conventions.md`](conventions.md) to all Stylebook copy and UI behavior.
