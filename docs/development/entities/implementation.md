# Implementing an entity type

Use this guide for a canonical entity that spans persistence, Backfield Output,
Stylebook, an extract node, and Agate review. Start with
`.cursor/skills/add-entity-type/SKILL.md` so product and identity decisions are made
before implementation.

The conceptual model and current support matrix are in
[`overview.md`](overview.md). Node runtime and panel conventions are in
[`../nodes.md`](../nodes.md).

## Cross-layer checklist

### Registry and schema

- Add the singular slug and consolidated key to
  `backfield_entities/registry/entity_types.py` and the Stylebook UI registry.
- Add namespaced canonical, substrate, mention, alias, and metadata tables as the
  domain requires. Canonical IDs are UUID strings.
- Add indexes for project identity lookup, canonical links, candidate queue
  filters, and mention joins.
- Use the database-change skill and update `docs/architecture/database.md`.

### Entity domain

Under `packages/backfield-entities/src/backfield_entities/entities/<type>/`, add
the focused modules the type needs:

- `types.py` for structured domain values;
- `policy.py` for `CanonicalPersistPlan` decisions;
- `recall.py` for candidate retrieval;
- `persist.py` for standalone create, aliases, suggestions, link/unlink, and
  canonical cleanup;
- `review.py` or `review_display.py` when extraction or queue reasons need typed
  presentation;
- `merge.py` and mismatch helpers when Stylebook cleanup supports the type.

Reuse shared planning, retrieval, and linking code from `canonical/` and
`entities/linking/`. Keep type-specific identity rules in the type package.

### Worker ingest

Add `apps/worker/src/worker/substrate/entities/<type>/` with a handler and focused
upsert, mention, or adjudication modules. The handler must:

1. read the type's consolidated key;
2. reconcile project-scoped substrate rows and mentions;
3. call canonical policy;
4. link, materialize, or defer;
5. return reconciliation statistics.

Import the handler from `worker/substrate/orchestration.py` so its registration
side effect adds it to `entities/registry.py`.

### Stylebook API

Add `apps/stylebook-api/src/stylebook_api/entities/<type>/` for substrate,
candidate, and metadata operations, plus a stylebook-scoped canonical router under
`routers/`.

An editorially complete type provides:

- candidate list and context;
- suggested canonicals and canonical search;
- create, link, unlink, move, defer, and note operations;
- canonical list, detail, update, and delete;
- grouped mentions and linked substrate rows;
- canonical metadata and connections;
- cleanup checks when the type has merge or mismatch review;
- import registration and bundle transfer when bulk movement is supported.

Keep location compatibility routes intact; newer types use their plural substrate
routes and stylebook-scoped canonical routes.

### Stylebook UI

Add four configurations under
`apps/stylebook-ui/src/lib/entityConfigs/<type>/`:

```text
candidateQueue.tsx
canonicalLinkModal.ts
canonicalList.ts or canonicalList.tsx
canonicalDetail.ts
```

Register the type and routes, then mount thin page wrappers around
`CandidateQueuePage`, `CanonicalListPage`, and `CanonicalDetailLayout`. Reuse
`CanonicalLinkModalGeneric`; do not fork the shared shells.

The detail page includes details, grouped mentions, metadata, and connections.
Only types with geography add a geography section. The candidate queue must include
review reasons, inline notes, suggestions, similar-canonical warning, and shared
post-action behavior.

See [`../frontend/stylebook.md`](../frontend/stylebook.md) for URL and scope
contracts.

### Extract and Backfield Output

Canonical entity extraction follows:

```text
Text Input → <Type> Extract → Backfield Output → substrate → Stylebook
```

Locations add Geocode between extraction and output. The extract node emits the
registered consolidated key; Backfield Output remains the generic persistence
bookend and dispatches to the worker handler. Follow [`../nodes.md`](../nodes.md)
for runtime registration, prompt layout, metadata, panel source, and sync.

### Agate review

Add backend merge/enrichment code under:

```text
apps/agate-api/src/api/processed_item/entities/<type>/
```

Add frontend review helpers under:

```text
apps/agate-ui/src/lib/review/entities/<type>/
```

The processed-item tab must merge run output, overlay changes, and saved substrate
context; support evidence navigation and editor add/edit/remove operations; and
deep-link to the correct Stylebook canonical or candidate queue. Extend the shared
overlay model rather than building a parallel review state system.

## Current directory map

```text
packages/backfield-entities/src/backfield_entities/
  registry/entity_types.py
  canonical/
    candidate_review.py
    link.py
    link_matrix.py
    match_score.py
    plan_types.py
    retrieval.py
  entities/
    linking/substrate_actions.py
    location/
    person/
    organization/
  catalog/
    full_bundle.py
    resolve.py
    stylebook_library.py
  ingest/
    db_output_settings.py
    geocode_cache/
    semantic_indexing/

apps/worker/src/worker/substrate/
  orchestration.py
  entities/
    registry.py
    location/
    person/
    organization/
    work/                  # registration stub only

apps/stylebook-api/src/stylebook_api/
  entities/
    location/
    person/
    organization/
  imports/
    registry.py
    csv_people.py
    csv_organizations.py
  routers/
    stylebook_canonicals.py
    stylebook_person_canonicals.py
    stylebook_organization_canonicals.py
    stylebook_cleanup.py
    imports.py
    connections.py

apps/stylebook-ui/src/
  lib/entityConfigs/
    location/
    person/
    organization/
  pages/
    Location*
    Person*
    Organization*

apps/agate-api/src/api/processed_item/entities/
  location/
  person/
  organization/

apps/agate-ui/src/lib/review/entities/
  location/
  person/
  organization/
  custom/
```

## Validation

Add focused tests at each affected boundary: models and migrations, entity policy
and persistence, worker reconciliation, Stylebook API contracts, bundle transfer,
node output, and review merge/UI behavior.

Run:

```bash
make lint
make test
```

Run `make smoke` when the change affects live ingest, cross-service persistence, or
review behavior.
