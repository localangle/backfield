# Agentic development (humans and assistants)

This page is the single orientation for **people and coding assistants**: where the rules live, the per-task-type checklists for common work, and how to plan multi-step changes. For repo map, commands, style, validation defaults, and the full Git workflow, `AGENTS.md` is the primary guide — this page does not repeat it.

## Start here

1. **[`AGENTS.md`](../AGENTS.md)** — Primary guide: repo map, commands, style, **validation defaults**, and **Git workflow** (including the **fresh branch when you begin implementation** default).
2. **[`docs/TESTING.md`](TESTING.md)** — Validation ladder (`make lint`, `make test`, `make smoke`, and friends).
3. **Area docs** — Open the source-of-truth doc for the layer you touch: [`ARCHITECTURE.md`](ARCHITECTURE.md), [`DATABASE.md`](DATABASE.md), [`API.md`](API.md), [`PUBLIC_API.md`](PUBLIC_API.md), [`FRONTEND.md`](FRONTEND.md), [`NODES.md`](NODES.md), [`ENTITY_TYPES.md`](ENTITY_TYPES.md), [`OPERATIONS.md`](OPERATIONS.md).

## Cursor rules and skills

- **Rules:** [`.cursor/rules/`](../.cursor/rules/) — workspace rules (workflow, Python, DB, frontend, docs freshness). Treat them as binding alongside `AGENTS.md`.
- **Skills:** [`.cursor/skills/`](../.cursor/skills/) — optional playbooks; use when the task matches the skill description. Common entry points: [`add-agate-node`](../.cursor/skills/add-agate-node/SKILL.md), [`add-entity-type`](../.cursor/skills/add-entity-type/SKILL.md), [`grill-me`](../.cursor/skills/grill-me/SKILL.md) (Plan mode / design stress-tests), and the pre-PR reviews [`pre-pr-code-review`](../.cursor/skills/pre-pr-code-review/SKILL.md) and [`pre-pr-architecture-review`](../.cursor/skills/pre-pr-architecture-review/SKILL.md).

## Task-type checklists

Use these to decide what to read and which checks to run. They build on `AGENTS.md` → **Validation defaults**; they do not replace it.

### Docs-only changes

- Read the matching source-of-truth doc before editing; keep terminology consistent with `AGENTS.md` and the rest of `docs/`.
- Run any targeted checks if commands, code examples, or generated references changed.

### Backend or Python changes

- Read `AGENTS.md`, [`ARCHITECTURE.md`](ARCHITECTURE.md), and the relevant domain doc.
- Keep imports at the top unless there is a documented exception.
- Prefer readable helpers over long route handlers or utility functions.
- Run `make lint` and `make test`.

### Database changes

- Read [`DATABASE.md`](DATABASE.md) and [`OPERATIONS.md`](OPERATIONS.md) first.
- Keep table names namespaced by app prefix; treat indexing decisions as part of the schema change, not an afterthought.
- Run `make lint`, `make test`, and the relevant migration or smoke flow.

### Frontend changes

- Read [`FRONTEND.md`](FRONTEND.md), including **User-facing copy**: all UI strings for **non-technical** users — no code-y jargon, API/DB internals, or developer shorthand in labels, errors, or empty states.
- Update `src/lib/api.ts` when API contracts move; reuse existing UI patterns before creating new ones.
- **Agate node UI:** edit `packages/backfield-agate/src/agate_nodes/<node>/ui/` (and `metadata.json`), then run `npm run sync-nodes` in `apps/agate-ui`. Do not edit synced files under `apps/agate-ui/src/nodes/<node>/` directly — sync will overwrite them. Net-new nodes: read [`NODES.md`](NODES.md) and use [`add-agate-node`](../.cursor/skills/add-agate-node/SKILL.md).
- Run the relevant lint/build flow and smoke checks for user-visible behavior changes.

### Runtime or orchestration changes

- Check Agate API, worker, DB, and docs together; keep queue/task/status naming aligned across API, worker, and tests.
- Run `make lint`, `make test`, and `make smoke`.

### Review (before opening a PR)

- Run both [`pre-pr-code-review`](../.cursor/skills/pre-pr-code-review/SKILL.md) and [`pre-pr-architecture-review`](../.cursor/skills/pre-pr-architecture-review/SKILL.md); address findings or open questions interactively first.
- Confirm the diff is scoped to the task, docs are updated when behavior changed, and tests/smoke cover meaningful runtime changes.
- Flag oversized functions, unclear naming, or mismatched cross-layer contracts.

## Planning multi-step work

Plan when the work spans multiple apps or packages, includes migrations or queue/architectural changes, has several validation steps or operational risk, or needs a phased rollout rather than a single-file edit.

A good plan includes:

- A concise goal statement and the main implementation phases.
- Explicit validation steps, plus risks or operational notes when they matter.
- A small todo list that can be marked in progress and completed as work advances.

Plan hygiene: keep the plan close to the work and update it when scope changes; prefer one coherent plan per task; don't let plans become stale background notes — complete, revise, or retire them. For larger product work, the [`write-a-prd`](../.cursor/skills/write-a-prd/SKILL.md) and [`prd-to-issues`](../.cursor/skills/prd-to-issues/SKILL.md) skills produce structured PRDs and issues.
