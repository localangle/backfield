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

PlaceExtract and GeocodeAgent preserve one terminal row for every extracted
location. Explicit country, subdivision, postal, and address components constrain
resolver acceptance. A rejected or review-required result retains its reason and
audit context but not provider identity, geometry, H3, or cache eligibility, and it
cannot create a canonical.
Recognized countries use ISO identity without requiring geometry; unknown country
labels never inherit a domestic default. Address displays must preserve the
structured house number and street, and article-level reconciliation keeps
co-located addresses and named places as distinct extraction identities.

### Sync link commit gate (auto-ingest only)

Before auto-ingest commits a `LINK_EXISTING` plan, a deterministic sync gate
(`backfield_entities.canonical.link_commit_gate`) vetoes obviously wrong pairs
using the same high-precision mismatch helpers as Stylebook cleanup, plus
location type/content sanity. A veto coerces the plan to `MATERIALIZE_NEW` when
policy allows, otherwise `DEFER`, and records
`sync_link_commit_veto` in `canonical_review_reasons_json`. Manual Stylebook UI
accepts and links are not gated—editors remain the escape hatch.

Person mismatch helpers treat dotted initials as equal (`CJ` / `C.J.`), allow a
small nickname map where prefix checks fail (`Tom` / `Thomas`), and rescue links
when the substrate name matches a trusted (non-`substrate_ingest`) alias on the
target canonical. Same-given / different-family pairs (for example Adam Fantilli
vs Adam Henrique) are vetoed before generic name-overlap rescue; generational
suffixes and surname particles do not create false conflicts.

AI-assisted adjudication returns a strict structured payload (`decision`,
`canonical_id`, finite numeric `confidence`, `same_identity`,
`conflicting_identity_evidence`). Rationale is audit-only. A `link_existing`
decision requires `same_identity=true` and `conflicting_identity_evidence=false`;
invalid or contradictory JSON is rejected (one corrective retry) and never
commits from prose alone.

### Alias provenance for exact match

Exact-alias lookups used for tier-1 / exact-identity autolink ignore
`substrate_ingest` aliases (`trusted_alias_only=True`). Editorial provenances
such as `stylebook_ui_accept` and `stylebook_ui_link` still count. Ingest aliases
may still appear in fuzzy recall for LLM adjudication; autolink-tier fuzzy
scores and the sync commit gate must not treat machine aliases as identity
evidence alone.

An exact location alias is a candidate set, not a first-row winner. Linking
requires one active, compatible, self-consistent survivor; multiple survivors
defer. Organization acronyms generated from a long name use
`generated_acronym` provenance and are recall-only evidence. Literal canonical
acronym labels and editor-accepted aliases remain trusted.

Neighborhood and other admin proper-name rows also require a compatible leading
placename head so distinct named areas cannot share identity. Stylebook-derived
substrate `external_id` values for fine-grained and admin location types include
a normalized name suffix so a poisoned candidate UUID cannot collapse distinct
places onto one substrate row. Already-linked ingest paths re-validate before
alias refresh and clear/re-plan on mismatch.

## Evidence and editorial scope

Mentions and linked substrate rows are project evidence. Canonical details,
aliases, metadata, and connections belong to the Stylebook. This distinction is
reflected in API query parameters and UI filters:

- filtering by project narrows evidence;
- editing canonical metadata or connections affects the Stylebook identity;
- editing a story row from Agate review affects that story's substrate evidence and
  does not silently rewrite the canonical.

Occurrence offsets are written only for a normalization-equivalent article slice.
When whitespace or encoding artifacts cannot be mapped back exactly, the evidence
text remains but its offsets are null.

Backfield Output's `replace` policy is authoritative for machine extraction,
including an emitted empty list: omitted article associations and their
`system_extraction` occurrences are retired. Editor-added, editor-modified, and
non-extraction associations are preserved, as are substrate identities still
used by other articles.

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
