---
name: create-stylebook-check
description: >-
  Add a Stylebook cleanup check (Checks hub) by copy-then-adapting an existing
  check end to end: finder, registry entry, API route, frontend config, and
  tests. Runs a short interview for entity type, check kind, description, and
  example records to catch. Use when adding a new data-quality / cleanup check
  for locations, people, or organizations.
disable-model-invocation: true
---

# Create a Stylebook cleanup check

Cleanup checks power the **Checks** hub (`/stylebook/<slug>/cleanup`): stylebook-scoped
data-quality triage over canonical records. This skill adds **one new check** by mirroring
an existing one as closely as possible, adapted to the new case.

**Core idea:** read the closest existing check first, then copy-then-adapt every layer.
Do not invent new shapes — match the reference check's structure, naming, and UX.

**Read first (in order):**

1. [`quality/checks.py`](../../../packages/backfield-entities/src/backfield_entities/quality/checks.py)
   — the registry; its module docstring is the canonical "add a check" recipe and the
   **single source of truth** for which checks exist and how counts are computed.
2. The **reference check** for your kind (see table below) — finder + API route + frontend.
3. [`docs/development/frontend/stylebook.md`](../../../docs/development/frontend/stylebook.md) → **Stylebook Review** — hub UX and copy.

**Not this skill:** adding a brand-new canonical **entity type** (a new `etc.` beyond
location/person/organization). That is a much larger job — use
[`add-entity-type`](../add-entity-type/SKILL.md) first, then return here to add checks.

**Related:** [`backfield-db-change`](../backfield-db-change/SKILL.md) (only if the check
needs a new index/column), [`update-repo-docs`](../update-repo-docs/SKILL.md),
[`review-backfield-change`](../review-backfield-change/SKILL.md).

---

## Two kinds of check

Pick the kind first — it decides every reference file.

| Kind | What it flags | Detail UX | Reference check |
|------|---------------|-----------|-----------------|
| **cluster** | Groups of canonicals likely the **same** record (duplicate detection) | drag-to-merge, delete empty, Keep separate | `duplicate-people` |
| **list** | **Individual** canonicals with a problem (bad link, missing/incorrect attribute) | Mark reviewed (dismiss per canonical) | `mismatched-people` (linked-name issue) or `missing-geometry-locations` (attribute issue) |

The user's **examples of records to catch** map directly:
- **cluster** → example pairs that *should* and *should not* cluster (tune similarity).
- **list** → example records (and counter-examples) the predicate must / must not flag.

---

## Interview

Ask **one question at a time**; wait for each answer. Skip anything already known.

1. **Entity type** — `location` | `person` | `organization`. (A new entity type → stop,
   use [`add-entity-type`](../add-entity-type/SKILL.md).)
2. **Check kind** — cluster or list (use the table above; confirm from their description).
3. **Description** — 1–2 sentences for the hub. **Product language, non-technical**
   (say "places / people / organizations", "linked mentions"; never "substrate" or DB terms).
4. **Examples to catch** — concrete records/pairs it should flag, plus a few it should
   **not** flag. These seed the predicate and the tests.
5. **Detection logic** — what exactly makes a record/cluster qualify (the predicate or
   similarity rule). Push for something conservative and explainable.
6. **Check id** — kebab-case, e.g. `mismatched-locations`. This string must be **identical**
   across: route segment, finder `_CHECK_ID`, dismissal key, and frontend config id.
7. **Title** — start with **"Potential …"** for consistency (e.g. "Potential mismatched places").

Then restate the plan (id, kind, entity, reference check, predicate) before writing code.

---

## Copy map

For the chosen entity type `<E>` (location|person|organization) and kind, copy-then-adapt:

### Backend — `packages/backfield-entities/src/backfield_entities/quality/`

| Layer | File | Action |
|-------|------|--------|
| Finder | `finders/<check>.py` | New module. Copy the reference finder; keep `count_*` + `list_*`/`paginate_*`. Set local `_CHECK_ID` = the check id. |
| Shared (cluster) | `finders/_duplicate_labels.py`, `finders/_clustering.py` | Reuse as-is; pass `model=` and `check_id=`. |
| Shared (list/mismatch) | `finders/_name_mismatch_common.py` | Reuse `CanonicalMismatchAgg`, alias-key loaders, `organization_project_ids`; add a `*_CHECK_ID` constant. |
| Row shape | `types.py` | Reuse an existing `Cleanup*Row`; only add a new dataclass if the row carries new fields. |
| Dismissals | `dismissals.py` | Do not edit. Call `load_dismissed_keys(..., check_id=<id>)` and `filter_dismissed_pairs` (cluster) or filter by `canonical_dismissal_key` (list), exactly like the reference. |
| Registry | `checks.py` | Add a `CleanupCheckDef` to the matching `*_CLEANUP_CHECKS` tuple with `id`, `title`, `description`, `entity_type`, `kind`, and a `count=lambda session, ctx: <count_fn>(...)` wired from `CleanupCountContext`. **Counts auto-wire here — no router dispatch to edit.** |

### API — `apps/stylebook-api/src/stylebook_api/routers/stylebook_cleanup.py`

| Layer | Action |
|-------|--------|
| Response model | Add a `*Out` Pydantic model + `Paginated*Response` mirroring the reference (subclass `Canonical<E>Response`). |
| List route | Add `GET /{stylebook_slug}/cleanup/checks/<id>` by copying the reference route; call your finder's `list_*` and the `_<E>_*_responses_with_counts` helper. |
| Hydration helper | Reuse the existing `_<E>_responses_with_counts` / mismatch helper; add one only if your row shape is new. |
| Counts | **Nothing to add** — the hub `GET …/cleanup/checks` reads `check.count` from the registry. |
| Cluster only | Merge + delete endpoints already exist per entity type — reuse; don't duplicate. |

### Frontend — `apps/stylebook-ui/src/`

| Layer | File | Action |
|-------|------|--------|
| API types + fetch | `lib/stylebook-api/cleanup.ts` | Add a `get<Check>()` fetcher and a `case "<id>":` in `getCleanupCheckResults`. |
| Hub/page config | `lib/cleanupChecks.ts` | Add a `CleanupCheckConfig` (`id`, `title`, `description`, `kind`, `entityType`). Keep `id`/`kind`/`entityType` in sync with the backend registry (comment at top of file). Title uses **"Potential …"**. |
| Rendering | `pages/CleanupCheck.tsx` | cluster → `DuplicateClusterList` (reused automatically by kind). list → reuse `MismatchedLinksList` (linked-name) or `GeographyIssuesList` (attribute). Add a `case`/branch + empty-state copy only if a new component is truly needed. |

---

## Tests

Mirror existing coverage; copy the reference check's tests and adapt fixtures from the
**examples to catch**.

| File | Add |
|------|-----|
| `tests/entities/test_quality_finders.py` | Finder unit tests: at least one record/pair that **is** flagged and one that is **not**. |
| `tests/stylebook_api/test_stylebook_cleanup_api.py` | Route test (shape + pagination) **and** update `test_list_cleanup_checks` — add your `id` to the expected id set and its expected `count` (otherwise that test fails). |
| `tests/entities/test_cleanup_dismissals.py` | If list-kind: confirm a dismissed canonical drops out of the count/list. |

---

## Conventions (do not drift)

- **One id everywhere:** route segment = finder `_CHECK_ID` = dismissal key = frontend config id.
- **Registry is source of truth:** add the `count` callable in `checks.py`; never reintroduce a per-check count dispatch in the router.
- **Titles:** "Potential …" (consistent across the hub).
- **UI copy:** product language for non-technical editors; no internal DB terms (no "substrate").
- **Conservative predicates:** prefer false negatives over false positives — a check that
  over-flags erodes trust. Lean on the counter-examples from the interview.
- **Typing:** annotate finder signatures; parse API boundaries with Pydantic.

---

## Validation

```bash
make lint
make test
```

If you changed live cross-service behavior (rare for a read-only check):

```bash
make smoke
```

Update [`docs/development/frontend/stylebook.md`](../../../docs/development/frontend/stylebook.md) (**Stylebook Review**) via
[`update-repo-docs`](../update-repo-docs/SKILL.md) when the hub's check list changes.

---

## Checklist

```
- [ ] Interview captured: entity, kind, id, title, description, examples, predicate
- [ ] Read checks.py docstring + the reference check end to end
- [ ] Finder added (count_* + list_*/paginate_*), dismissals wired by check id
- [ ] CleanupCheckDef registered with count callable (counts verified in hub)
- [ ] API list route + response model added (reused hydration helper)
- [ ] Frontend: cleanup.ts fetcher + getCleanupCheckResults case; cleanupChecks.ts config
- [ ] CleanupCheck.tsx renders the new check (reused list/cluster component)
- [ ] Tests: finder + API route + test_list_cleanup_checks id set updated (+ dismissal)
- [ ] make lint && make test green
```
