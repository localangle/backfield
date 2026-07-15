# Entity canonicalization

Backfield separates ingested evidence from editorial identity:

- `substrate_*` rows are project-scoped observations created from processed content.
- `stylebook_*_canonical` rows are organization catalog identities.
- aliases provide normalized lookup names for a canonical.
- the nullable canonical foreign key on a substrate row records the accepted link.

Locations, people, and organizations use the same broad shape: entity, article mention, mention
occurrence, canonical, alias, and metadata. Type-specific policy remains in
`backfield_entities.entities.<type>`.

## Ingest and decision flow

Backfield Output first upserts the article and extracted substrate rows. For each supported entity
domain it then:

1. Computes or reuses the project-scoped substrate identity.
2. Resolves the explicit same-organization Stylebook or the organization's default.
3. Applies type policy to produce `link_existing`, `materialize_new`, or `defer`.
4. Optionally asks the configured AI model to adjudicate a closed recall set.
5. Applies the decision or records it as a review suggestion.
6. Persists the decision trace in `canonical_review_reasons_json`.

When `auto_apply_canonicalization` is false, link and create decisions remain pending suggestions.
Deferred private residences may be marked waived when auto-apply is enabled so they do not remain
in the open candidate queue. Other unresolved rows remain pending for Stylebook review.

Manual Stylebook creation can create a canonical and primary alias without a substrate row.
Materializing from ingest creates the canonical and link together and copies type-specific catalog
fields from the originating substrate once. Linking to an existing canonical does not overwrite
the canonical's editorial fields with substrate values.

## Location policy

Location policy checks exact active labels and non-suppressed aliases, then ranked fuzzy recall.
Automatic links pass the shared type matrix and content sanity checks. Strict gates are enabled by
default and add jurisdiction, district identity, container-versus-fine-place, geometry, formatted
address, and name-anchor checks. `BACKFIELD_STRICT_CANONICAL_GATES=0` disables those additional
gates, but not the base matching policy.

Resolved locations without a safe match generally materialize a canonical. These categories stay
review-oriented:

- private residences and ordinary addresses;
- roadway spans;
- road and highway intersections;
- streets without the required resolved geometry;
- extraction or geocode results already marked for review.

Intersections and spans never auto-materialize, although they may link to an existing compatible
canonical. Exact and fuzzy candidates for addresses, intersections, and named places must preserve
the street or venue identity rather than resolving only to a containing city or neighborhood.
Political districts use structured district identity when available.

## Person policy

Person tier-one matching requires an exact normalized name or alias plus affiliation; title is
used by stricter comparison and recall but not by that automatic-link identity. When recall
returns no candidates, policy creates a canonical unless extraction review signals block
materialization. Ambiguous recall, descriptive pseudonyms, first-name-only identities, children,
animals, and non-person extractions defer according to their review metadata.

AI-assisted person adjudication can select only from recalled canonicals and must meet the shared
0.9 link-confidence threshold. If it declines every recalled candidate, a new canonical is allowed
only when the extraction review policy permits it.

## Organization policy

Organization tier-one matching combines normalized name identity with `organization_type`.
Compatible type variants may link; incompatible alias/type matches defer. When recall returns no
candidates, policy creates a canonical; ambiguous recall is offered for review or AI adjudication.

AI-assisted organization adjudication is closed-list. The normal link threshold is 0.9; the
explicit compatible-type path uses its separate 0.75 threshold. Name-variant recall may run for
acronyms and multiword names before creating a new canonical.

## Reconciliation and provenance

Canonicalization and article reconciliation are separate controls. Backfield Output's
`add_only`, `smart_merge`, and `replace` policies decide how newly produced domains affect prior
machine-generated mentions. Re-ingest replaces current system-extraction occurrences while
preserving user review and edit evidence. Stale machine mentions can be retired, and substrate
entities with no active mentions can be unlinked and removed.

Every automatic outcome records structured reasons, including exact identity, fuzzy recall,
materialization, ambiguity, deferral, and AI adjudication. Semantic documents point to substrate
occurrence evidence; canonical identity is resolved through the substrate link at query time.

## Catalog selection

Catalog selection follows one current rule:

1. An explicit Stylebook row id, validated against the project's organization.
2. A supplied Stylebook slug, including slug redirects.
3. The organization's default Stylebook, falling back to the first catalog by id when no row is
   marked default.

Backfield Output uses explicit id or organization default. Stylebook routes can use slug or
organization default. GeocodeAgent does not use this fallback: its project-scoped substrate cache
works without a Stylebook id, while canonical lookup, adjudication, and materialization require
the node's explicit Stylebook id.
