# Agent Workflows

Use this file to decide what to read and which checks to run for common task types.

For a short overview of how agentic work is organized in this repo (entry points, Cursor rules/skills, branch habits), see [`docs/AGENTIC.md`](AGENTIC.md).

## agate-ai-platform parity

Backfield is a refactor of **agate-ai-platform** (`/Users/cjdd3b/apps/agate-ai-platform` on this machine, or your local clone). For non-trivial features and fixes, **open the corresponding files there** and aim for **maximum fidelity** when copying or adapting. See `AGENTS.md` → **Reference implementation**.

## Git and branches

- **Default:** when you start writing code, check out a **fresh branch** from the task base (typically `main`) unless the instructions explicitly say to use or extend an existing branch.
- Create a **new branch** for each distinct task. Large or unrelated work (new packages, migrations, multi-app changes) should not ride on an unrelated existing branch.
- Name branches so the intent is obvious (for example `feat/backfield-agate-port`, `fix/worker-timeout`).
- See `AGENTS.md` → **Git workflow** for the full convention.

## Docs-only changes

- Read the matching source-of-truth doc before editing.
- Keep terminology consistent with `AGENTS.md` and other docs.
- Run any targeted checks if commands, code examples, or generated references changed.

## Backend or Python changes

- Read `AGENTS.md`, `docs/ARCHITECTURE.md`, and the relevant domain doc.
- Keep imports at the top unless there is a documented exception.
- Prefer readable helpers over long route handlers or utility functions.
- Run `make lint` and `make test`.

## Database changes

- Read `docs/DATABASE.md` and `docs/OPERATIONS.md` first.
- Keep table names namespaced by app prefix.
- Treat indexing decisions as part of the schema change, not an afterthought.
- Run `make lint`, `make test`, and the relevant migration or smoke flow.

## Frontend changes

- Read `docs/FRONTEND.md`.
- Update `src/lib/api.ts` when API contracts move.
- Reuse existing UI patterns before creating new ones.
- Run the relevant lint/build flow and smoke checks for user-visible behavior changes.

## Runtime or orchestration changes

- Check Agate API, worker, DB, and docs together.
- Keep queue/task/status naming aligned across API, worker, and tests.
- Run `make lint`, `make test`, and `make smoke`.

## Review workflow

- Before creating a PR, run both [`pre-pr-code-review`](../.cursor/skills/pre-pr-code-review/SKILL.md) and [`pre-pr-architecture-review`](../.cursor/skills/pre-pr-architecture-review/SKILL.md).
- Confirm the diff is scoped to the task.
- Check docs when behavior changed.
- Check tests and smoke coverage for meaningful runtime changes.
- Flag oversized functions, unclear naming, or mismatched cross-layer contracts.
- Raise cleanup or architecture concerns interactively before proceeding to PR creation.