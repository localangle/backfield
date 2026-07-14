# Entity model

Backfield separates story content from entities that can be curated in a
Stylebook.

- `content/` contains story carriers and run-scoped ingest context. An article is
  content, not an entity type.
- `entities/<type>/` contains canonical identity rules, project-scoped substrate
  rows, mentions, and editorial review behavior.

Runtime and package boundaries are described in
[`../../architecture/overview.md`](../../architecture/overview.md).

## Entity registry

The Python registry is
`packages/backfield-entities/src/backfield_entities/registry/entity_types.py`.
Stylebook UI mirrors the same slugs in `src/lib/entityTypes.ts`.

| Type | Slug | Consolidated key | Current support |
|---|---|---|---|
| Location | `location` | `places` | Extract, geocode, ingest, canonical curation, import/transfer, Agate review |
| Person | `person` | `people` | Extract, ingest, canonical curation, import/transfer, Agate review |
| Organization | `organization` | `organizations` | Extract, ingest, canonical curation, import/transfer, Agate review |
| Work | `work` | `works` | Reserved registry entry and UI stubs; no functional API, ingest, canonical, or editorial surface |

Python folders use singular slugs. Pipeline JSON retains product and compatibility
keys such as `places` and `people`. Canonical IDs are UUID strings.

## Substrate and canonicals

A substrate row is a project-scoped instance evidenced by a story. A canonical is
the Stylebook-wide editorial identity to which one or more substrate rows may link.

```text
pipeline output
  → Backfield Output
  → project-scoped substrate row + mentions
  → canonical policy
      → link an existing canonical
      → create and link a canonical
      → leave the row for editorial review
```

Candidate queues contain substrate rows that are not linked to a canonical.
Linking, moving, or unlinking changes that relationship without changing the
canonical's Stylebook-wide metadata and connections.

Canonical policy uses the shared `CanonicalPersistPlan` contract:

- `LINK_EXISTING` links a strong identity match and refreshes aliases.
- `MATERIALIZE_NEW` creates a canonical when policy allows it.
- `DEFER` records review reasons and leaves the substrate row in the queue.

Rules are type-specific. Location identity includes resolved geography and
jurisdiction constraints. Person identity uses normalized name and affiliation;
title is not part of the substrate identity fingerprint. Organization policy uses
its own name and organization signals. Projects may use rules-only or AI-assisted
canonical adjudication; model-assisted links must still satisfy the shared
confidence threshold.

## Evidence and editorial scope

Mentions and linked substrate rows are project evidence. Canonical details,
aliases, metadata, and connections belong to the Stylebook. This distinction is
reflected in API query parameters and UI filters:

- filtering by project narrows evidence;
- editing canonical metadata or connections affects the Stylebook identity;
- editing a story row from Agate review affects that story's substrate evidence and
  does not silently rewrite the canonical.

## Canonical connections

Connections are directed Stylebook relationships. Manual connections require a
human-readable description, a normalized nature, or both. Automatic inference is
description-first, includes quote-backed evidence, and only writes sufficiently
confident relationships.

Supported inferred families include person–organization, organization–location,
person–location, person–person, and organization–organization. Exact edge
uniqueness is project-scoped and includes endpoints, nature, and description.

## Creating and transferring canonicals

Canonicals can be created manually, imported, or transferred in an organization
Stylebook bundle:

- locations import from GeoJSON;
- people and organizations import from CSV;
- bundle transfer includes location, person, and organization canonicals, aliases,
  project-scoped metadata, and connections whose endpoints are included.

Bundle import assigns new canonical IDs and resolves project-scoped data by project
slug or explicit mappings. It does not transfer substrate rows, candidate state,
geocode cache, semantic embeddings, or activity logs.

For the cross-layer implementation pattern, use
[`implementation.md`](implementation.md).
