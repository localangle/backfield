# Storylines (deferred)

**Status:** Deferred — not scheduled. Phase A connections shipped; see
[`knowledge-graph.md`](../architecture/knowledge-graph.md) for the live connection model.

This document preserves the **decision record** for multi-article coverage packaging
(**storylines**) in Stylebook. It is product intent, not a runtime contract. Re-derive
detailed schema and API shapes when implementation resumes.

## Why storylines (not Event canonicals)

Events and propositional claims are hard to identity-manage and fight Stylebook’s
substrate → candidate → canonical muscle. Articles hold journalism; mentions ground
entities; **storylines** group coverage across articles and cycles (e.g. “2026 city
budget”, “dispute between X and Y”). Clients have asked for issue-shaped navigation;
storylines fill that gap better than Event/Claim Stylebook canonicals.

## Target shape

```text
Article
  ◄── mention / occurrence ──► substrate ──► Canonical
  ◄── membership (optional primary) ──► Storyline (accepted)

Canonical person / org / location
  ◄── connection (preferred nature) ──► Canonical
         └── evidence[] (article, quote, confidence, …)
```

**Storylines** are first-class Stylebook catalog objects (coverage packages), not Event
entities. **Claims / stances:** prefer article ∩ storyline ∩ entity evidence packs;
structured facts only when the object is crisp (preferred nature to a canonical, or later
topic/work).

Borrowed from temporal-graph cookbooks: **communities / packages** map to storylines;
**episodes** remain articles; **entity nodes** remain canonicals; **facts / edges** remain
connections with evidence.

## Decision log

### Lifecycle and presentation

| Decision | Choice |
|----------|--------|
| Lifecycle | Candidate → accepted; only accepted are public first-class |
| Membership | Many-to-many article ↔ storyline |
| Ranking | Optional **primary** storyline per article; others secondary |
| Failure mode | Optimize against **false merge / wrong assign** (precision over recall) |
| Entity overlap in matching | **Soft prior** (boost / tighten bar); never a hard gate |
| Tenancy | Org-scoped storyline identity; project-aware membership (Stylebook-like) |
| Persistence | **Own tables and APIs** (not forced through entity substrate abstractions) |
| Presentation | Stylebook-class UX: catalog surfaces, article-review tab peer to people/places/orgs |
| Agate role | Post–Backfield Output side effect (propose only); not a required canvas node |
| Agate review | Read-only hint + link to Stylebook (recommended; confirm at implement time) |

### Identification (compute)

Incremental, not full-corpus reclustering per ingest:

1. Use existing article embeddings (pgvector).
2. ANN against storyline search docs (summary embedding + optional member centroid) and a
   capped orphan neighborhood for rare “birth new storyline” proposals.
3. Cheap filters (time window, project/org scope); shared canonicals as soft signal.
4. LLM yes/no only on top-K neighbors; high threshold; prefer **link-to-existing** over create.
5. Occasional batch jobs for drift / merge suggestions — not on the hot path.

Cost should grow with **#storylines**, not **#articles**.

## Sketch schema (re-derive at implement time)

Rough table names under `stylebook_*` in `packages/backfield-db`:

- **`stylebook_storyline`** — org catalog package: label, slug, summary, status
  (`candidate` | `accepted` | `rejected` | `merged`), optional `merged_into_id`, optional
  primary article / archive flags.
- **`stylebook_storyline_membership`** — article membership: status (`proposed` | `accepted` |
  `rejected`), optional `is_primary` (at most one accepted primary per article), confidence,
  source (`auto` | `editor`). Uniqueness: `(storyline_id, article_id)`.
- **`stylebook_storyline_embedding`** (or columns on storyline) — search doc for ANN;
  reuse pgvector patterns from `substrate_article_embedding`.

Activity / bundles: extend `stylebook_activity` for storyline and membership events; bump
bundle schema when export/import of accepted storylines ships.

No backfill of historical storyline membership required for v1 when this lands.

## Open points (resolve at implement time)

- Candidate UX: queue density caps given precision-first thresholds.
- Public API shapes for storyline list/detail and `include=` expansion.
- Exact status enum and merge/archive semantics.

## References

- Parent ADR: [`knowledge-graph.md`](../architecture/knowledge-graph.md) (Phase A connections)
- [Graphiti](https://github.com/getzep/graphiti) — temporal context graphs, episodes, communities
- Entity model: [`../development/entities/overview.md`](../development/entities/overview.md)
