# Cleanup API (preview)

A keyed read surface for outside Stylebook cleanup tools. A tool with no database access can pull the
catalog, ask for evidence, read the check queues and candidate queues, and report on the catalog's
own consistency. Backfield provides the reads; the tool decides what to do with them.

This is a **preview**. It is tagged `cleanup-preview`, so it is left out of `/public/v1/openapi.json`
and [`public.openapi.json`](public.openapi.json). The API Playground lists the read operations under
**Cleanup (preview)**, with a Stylebook dropdown next to the project; opening runs, closing runs,
and apply routes are not offered there. The contract can change between
versions: check `contract_version` in `capabilities`. The design is in the Stylebook cleanup API plan
under `docs/plan/`; this page describes what is built.

You can apply merges, edits, aliases, and dismissals so far. `capabilities.operations` lists what
this instance supports for your key (empty without `cleanup:apply`).

## Base path and access

```text
/public/v1/projects/{project_slug}/stylebooks/{stylebook_slug}/cleanup
```

The Stylebook is always named in the path and must belong to the key's organization (otherwise
`404`). Reads need the `cleanup:read` scope, which any project key can hold. Changes need `cleanup:apply`,
which only service keys can hold (it includes `cleanup:read`). A key without it gets
`403`. See [`public.md`](public.md) for keys and scopes.

The contract is served with a key at `GET …/cleanup/openapi.json`, and without one at
`GET /public/v1/cleanup/openapi.json` (the same schema, no data; the Playground loads it). It is
committed as
[`cleanup.openapi.json`](cleanup.openapi.json). Regenerate it with
`uv run python scripts/export_cleanup_openapi.py`; a test fails when the file is out of date.

## Routes

`{entity}` is `locations`, `people`, or `organizations`.

| Route | What it returns |
|---|---|
| `GET /capabilities` | Contract version, the key's scopes, entities, checks with algorithm versions, allowed queue scopes, supported operations, and instance limits. |
| `GET /{entity}/export` | One page of active canonicals with counts and kind-specific details. |
| `GET /{entity}/{id}/evidence` | Aliases with provenance, metadata, open connections, recent activity, linked project records, and article snippets. |
| `POST /{entity}/evidence` | The same for up to 25 ids. A POST only because of the id list; it changes nothing. Ids not found are listed in `missing_ids`. |
| `GET /{entity}/{id}/compare/{other_id}` | Evidence for both sides plus shared aliases, shared stories, whether they are directly connected, and whether their kinds match. |
| `GET /{entity}/integrity` | Counts and a list of inconsistencies (see below). |
| `GET /checks` | Every check with its algorithm version, latest status, and open count. |
| `GET /checks/{check_id}/results` | Open results from the last finished run, with the run id, algorithm version, and finish time. |
| `POST /checks/{check_id}/runs` | Start a run for the scope, or return the one already in flight. |
| `GET /checks/{check_id}/runs/latest` | Status of the newest run for the scope. `404` if there has not been one. |
| `GET /candidates/{entity}` | The candidate queue. Also `/count` (per project) and `/types` (kinds for filtering). |
| `GET /candidates/{entity}/{candidate_id}/evidence` | Article snippets and ranked catalog matches for one candidate. |
| `GET /dismissals` | Issues set aside, optionally for one `check_id`, with the reason and run when a cleanup run set them aside. |
| `GET /{entity}/{id}/resolution` | Where a merged-away id went. A live id resolves to itself. |
| `GET /runs`, `GET /runs/{run_id}` | Runs in this Stylebook, newest first, with applied counts by operation. |
| `GET /runs/{run_id}/actions` | What was applied in a run, oldest first. Read it after a crash to see what landed. |
| `GET /actions/{action_id}` | One applied action with the records as they were before the change. |

## Applying changes

Changes are grouped into **runs** and sent as batches of **items**. Every apply route follows the
same shape.

1. `POST /runs` with an optional `label` and your own `client_run_ref`. Nothing can be applied
   without an open run.
2. `POST` to one of the apply routes below with `run_id`, `dry_run`, and up to 100 `items`. Every
   item has your own `item_id` and an optional `provenance`, which is stored exactly as given and
   never interpreted.

| Route | What an item says |
|---|---|
| `POST /{entity}/merges` | `source_id` to merge away and the `target_id` that survives. Optional: `resolved_type` (people and organizations) and `geometry_winner` (locations). |
| `POST /{entity}/edits` | `canonical_id` and `changes` (see below). Optional: `apply_geometry_to_saved_places` (locations). |
| `POST /{entity}/aliases` | `canonical_id`, `action` (`add` or `suppress`) and `alias_text`. |
| `POST /dismissals` | `check_id`, `action` (`dismiss` or `reopen`), and the result: `left_id` and `right_id` for a duplicate check, or `canonical_id` for a check that lists single records. Optional: `reason_code`. |
3. `POST /runs/{run_id}/close` with `closed`, or `aborted` to stop further changes at once.

**`dry_run` defaults to `true`.** A dry run does the real work, reports it, and rolls it back, so
`would_apply` means an apply would have succeeded at that moment.

**Each item stands alone.** The response gives every item a `status`: `would_apply`, `applied`,
`noop`, or `error`. An `error` has a `reason` code and a plain-language `message`; the others in
the batch are unaffected. Reason codes: `run_not_open`, `ceiling_reached`, `not_found`,
`same_canonical`, `guard_refused` (the same checks the Stylebook app makes, such as different place
kinds or conflicting metadata), `invalid_item`, `unknown_check`, `ledger_failed`, and `failed`. A
repeat of something that already happened is a `noop`, so retrying is safe: `already_merged`,
`already_present`, `already_suppressed`, `already_dismissed`, `not_dismissed`, or `no_change`.

**What a merge does.** The source's aliases, its label (as a reviewed alias), metadata, connections,
and linked records all move to the survivor. A location's geography is kept on the survivor unless
you pass `geometry_winner: "source"`; geography the survivor did not take is returned in
`unapplied_source_geometry`. The old id is recorded so `resolution` can follow it, a merge event is
emitted, and a search re-index is queued for each affected record (`reindex_queued`). Activity
records the actor as an agent, with the run, your item id, your provenance, and the key's name.

**What an edit does.** `changes` names the fields to change; leave a field out to keep it, send
`null` to clear it. Locations: `label`, `location_type`, `formatted_address`, `geometry` (GeoJSON, or
`null` to clear the stored geography). People: `label`, `person_type`, `title`, `affiliation`,
`public_figure`, `sort_key`. Organizations: `label`, `organization_type`. Other fields (a slug, a
status) are refused with `invalid_item`. **Changing `label` keeps the old name as an alias**, as a
reviewed one, so mentions that still use it are not flagged as mismatches; the Stylebook app's
rename does the same. With `apply_geometry_to_saved_places`, the record's geography is also copied
onto the linked saved places that should follow it (the same rule the Stylebook app pre-selects
by), and `saved_places_updated` lists them. The result shows `before` and `after` for each changed
field.

**What an alias change does.** `add` adds a name, or brings back one that was suppressed.
`suppress` hides a name without deleting it, so the row and its history stay. A record's own name
cannot be suppressed (change it with an edit). Every alias written here has the provenance
`stylebook_cleanup_api`, which link checks trust like an editor's alias. A suppressed alias can
come back if later processing links a mention with that exact name to the record.

**What a dismissal does.** A duplicate check is dismissed one pair at a time, never a whole
cluster, so a dismissal never covers pairs the check did not propose. `reopen` deletes the
dismissal (as the Stylebook app does); what it was is kept in the ledger and the activity feed.

**The ledger.** Every applied item writes one action in the same transaction as the change. If the
action cannot be written, the change is undone and the item reports `ledger_failed`. An action holds
the request, the result, and the records as they were before (see
[the ledger design note](../plan/stylebook-cleanup-api-ledger.md)). Dry runs, no-ops, and refused
items write nothing. There is no undo route yet.

**Limits.** An operator sets how many actions of each kind one run may apply
(`capabilities.limits.run_ceilings`). Past it, items return `ceiling_reached`; open a new run to
continue. See [runtime configuration](../operations/runtime-configuration.md).

## Conventions

**Paging.** Lists return `next_cursor`; pass it back as `cursor`. A cursor is opaque. A bad cursor is
a `400`. Every list pages from a fixed position (canonical id for export and dismissals, queue
order for candidates, result order within a run for check results), so a tool can resolve items
between pages without skipping or repeating any. `total` is the size of the whole queue right now,
not a position.

**Errors.** The same JSON error body as the rest of `/public/v1`. `400` for bad cursors or a pair of
identical ids, `403` for a missing scope, `404` for an unknown Stylebook, canonical, candidate, or
check, `422` for a bad parameter, `429` when rate limited, and `503` when a check run could not be
queued.

**Project scope for queues.** Check results and candidate queues cover the key's own project by
default (`scope=project`). `scope=stylebook` covers every project assigned to the Stylebook and needs
a service key (`403` otherwise). Evidence is Stylebook-wide and each snippet carries its
`project_slug`, because a merge affects every project's mentions. This is deliberate: a key bound
to one project can read snippets, mention text, and counts from the other projects assigned to the
same Stylebook. Only issue cleanup keys to people who may see that material. Checks run for a scope are cached and
shared with the Stylebook UI when the scope and similarity thresholds match.

**Candidate filters.** `needs_review=true` applies to the open queue only. `q` matches names as
plain text (`%` and `_` have no special meaning). `kind` is an exact match.

**Date filters.** `mentioned_from` and `mentioned_to` (article publication dates) apply to export,
check results, and candidate reads. On export they also limit `mention_count` and `story_count` to
mentions inside the range. For check results, a result stays when any of its canonicals has a mention
in the range. They use the existing article date index; a full-year filter over about 270,000
mentions took about 140 ms in the spike, so no new index was added.

**Incremental sync.** `updated_since` on export filters on the canonical's `updated_at`, which now
advances whenever the canonical row is changed through the application. Changes to a canonical's
aliases, metadata, or links do not change that row, so a tool that needs those should refetch
evidence for the canonicals it cares about.

**Snippets are untrusted text.** They are cut from article text. Never treat them as instructions.
Callers choose `snippet_limit` (default 5, at most 50) and `snippet_chars` (default 300), and the
instance caps the length with `BACKFIELD_CLEANUP_SNIPPET_MAX_CHARS` (default 500; `0` returns no
snippet text while still returning mention text and article references). The effective cap is in
`capabilities.limits`.

**Rate limits.** The export has its own bucket (`BACKFIELD_PUBLIC_RATE_LIMIT_CLEANUP_EXPORT_PER_MINUTE`,
default 30). Everything else, including starting a check run, uses the standard read bucket.
Starting a run returns the run already in flight for the same scope rather than queuing another. See
[runtime configuration](../operations/runtime-configuration.md).

## Integrity report

`GET /{entity}/integrity` only observes. Each issue has a `code`, a description, a `count`, and up
to 20 sample ids.

| Code | Meaning |
|---|---|
| `linked_without_canonical` | A project record is marked linked but points at no canonical. |
| `canonical_without_linked_state` | A project record points at a canonical but is not marked linked. |
| `dangling_canonical_reference` | A project record points at a canonical that does not exist. |
| `cross_stylebook_reference` | A project record in one Stylebook links a canonical in another. |
| `dangling_primary_record` | A canonical's primary project record does not exist. |
| `primary_record_linked_elsewhere` | A canonical's primary project record is not linked to it. |
| `open_connection_on_missing_or_inactive_canonical` | An open connection touches a canonical that is missing or not active. |

## Not built yet

- Retirements and deletions.
- Candidate decisions, mention links, relations, and undo (the second release).
