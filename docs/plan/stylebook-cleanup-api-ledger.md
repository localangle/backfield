# Stylebook cleanup API: runs, ledger, and before-state (design note)

**Status:** Design for phase C, slice 1 (2026-11-23). Settles the "before-state format" and
"ceilings" open questions in [`stylebook-cleanup-api.md`](stylebook-cleanup-api.md). Phase E
(undo) builds on the shapes here, so change them deliberately.

## Principles

- The ledger records what **was applied**. Dry runs, no-ops, and refused items write nothing; the
  response reports them.
- The ledger row is written in the **same transaction** as the change. If the row cannot be
  written, the item fails and the change rolls back (fail closed).
- The before-state is a **pre-image of every row the operation can touch**, taken before the
  operation runs. It is enough to rebuild the rows by hand even if undo never exists for the
  operation. Undo (phase E) uses it and refuses, changing nothing, when the current rows no longer
  match what the operation left behind.
- Values are stored as given. Reason codes and provenance are never interpreted.

## Tables

| Table | Purpose |
|---|---|
| `stylebook_cleanup_run` | A caller-opened grouping: label, caller's own reference, status (`open`, `closed`, `aborted`), the key that opened it, timestamps. |
| `stylebook_cleanup_action` | One row per applied item: run, Stylebook, operation, entity type, subject canonical ids, the caller's item id and provenance, the key, the request and result, the before-state, whether reindex was queued, applied and (later) undone timestamps. |
| `stylebook_canonical_redirect` | `merged_into`: old canonical id to the survivor, per Stylebook and entity type. Unique on `(stylebook_id, entity_type, old_id)`. |

Indexes follow the routes: runs by Stylebook and status; actions by run and by Stylebook and
time, and by subject canonical; redirects by the unique key and by the survivor.

## Merge before-state (`schema` 1)

Taken from the Stylebook before `apply_merge` runs, with the same code for every entity type
(through the entity table registry). Columns are stored by name; the binary geometry column is
skipped because it is rebuilt from `geometry_json`.

```json
{
  "schema": 1,
  "operation": "merge",
  "entity_type": "location",
  "source": {
    "canonical": { "...every column but binary geometry..." },
    "aliases": [ { "...alias row incl. id..." } ],
    "meta": [ { "...meta row incl. id..." } ],
    "linked_records": [ [project_id, record_id] ],
    "connections": [ { "...connection row incl. id, closed_at...", "evidence_ids": [1, 2] } ]
  },
  "target": {
    "canonical": { "...every column but binary geometry..." },
    "alias_norms": ["normalized alias", "..."],
    "meta_types": ["meta type", "..."]
  }
}
```

What each part is for:

- `source.canonical`, `aliases`, `meta`: recreate the deleted source and give back the rows that
  moved to the survivor (matched by id).
- `source.linked_records`: the records to relink to the source on undo.
- `source.connections` (open and closed, with their evidence ids): connections the merge moved,
  deduplicated, or dropped as self-loops.
- `target.canonical`: the survivor's geography, kind, and label before the merge, because the
  merge can overwrite them.
- `target.alias_norms`, `meta_types`: which survivor aliases and metadata already existed, so an
  undo removes only what the merge added.

Size: one row per alias, metadata item, and connection, plus an id pair per linked record. A
canonical with thousands of linked records stores thousands of id pairs; that is the accepted
cost, bounded by the per-run ceiling.

**How much of a merge revert is automatic (phase E).** Automatic when the survivor and the moved
rows are still as the merge left them. Refused with a named reason, changing nothing, when any
of them changed since (a later edit, a second merge into the survivor, a deleted survivor).

## Result

`result_json` holds what the operation reported (relinked count, transferred alias and metadata
counts, source geography the survivor did not take), so a caller who lost a response can read the
action back.

## Ceilings

Per run, per operation class, from environment settings so an operator can raise one without a
deploy (a restart of Core API picks it up). An item past its ceiling returns `error` with reason
`ceiling_reached`; nothing is applied. Defaults are sized from the 2024 passes (3,846 merged-away
place labels; 2,065 organization merges in one wave) with headroom, and are far smaller for the
operations that are hardest to reverse.

| Operation class | Setting | Default |
|---|---|---|
| `merge` | `BACKFIELD_CLEANUP_CEILING_MERGE` | 5000 |
| `edit` | `BACKFIELD_CLEANUP_CEILING_EDIT` | 5000 |
| `alias` | `BACKFIELD_CLEANUP_CEILING_ALIAS` | 5000 |
| `dismissal` | `BACKFIELD_CLEANUP_CEILING_DISMISSAL` | 5000 |
| `retirement` | `BACKFIELD_CLEANUP_CEILING_RETIREMENT` | 500 |
| `deletion` | `BACKFIELD_CLEANUP_CEILING_DELETION` | 200 |

A ceiling counts applied actions in the run, so dry runs and refused items never use it up.

## Kill switch

Closing a run as `aborted` makes every later apply on it return `error` (`run_not_open`). Revoking
the key stops everything. Closing as `closed` also stops applies; the difference is only the
recorded intent.
