# Agentic development (humans and assistants)

This page orients **people and coding assistants** on how work is organized in Backfield: where rules live, how tasks are scoped, and what to run before you finish.

## Start here

1. **[`AGENTS.md`](../AGENTS.md)** — Primary guide: repo map, commands, style, validation defaults, and Git workflow (including **fresh branch when you begin implementation** unless told otherwise).
2. **[`docs/AGENT_WORKFLOWS.md`](AGENT_WORKFLOWS.md)** — Task-type checklists (backend, DB, frontend, runtime, review): what to read and which checks to run.
3. **[`docs/TESTING.md`](TESTING.md)** — Validation ladder (`make lint`, `make test`, `make smoke`, etc.).
4. **[`docs/PLANS.md`](PLANS.md)** — When and how to plan multi-step or risky work.

## Cursor / IDE conventions

- **Rules:** [`.cursor/rules/`](../.cursor/rules/) — workspace rules (workflow, Python, DB, frontend, docs freshness). Treat them as binding alongside `AGENTS.md`.
- **Skills:** [`.cursor/skills/`](../.cursor/skills/) — optional playbooks (e.g. DB changes, smoke, doc updates, self-review). Use when the task matches the skill’s description. For **Plan mode** or explicit design stress-tests, see [`grill-me`](../.cursor/skills/grill-me/SKILL.md). Before opening a PR, run [`pre-pr-code-review`](../.cursor/skills/pre-pr-code-review/SKILL.md) and [`pre-pr-architecture-review`](../.cursor/skills/pre-pr-architecture-review/SKILL.md).

## Recommended workflow

1. **Branch:** When you start writing code, use a **fresh branch** from the task base (usually `main`) unless the instructions say to continue on an existing branch. One coherent task per branch and per PR.
2. **Read first:** Open the source-of-truth doc for the area you touch (`docs/ARCHITECTURE.md`, `docs/DATABASE.md`, `docs/API.md`, etc.).
3. **Implement:** Prefer surgical diffs; match existing patterns; update docs when behavior or operations change.
4. **Validate:** Follow [`docs/TESTING.md`](TESTING.md) and [`AGENTS.md`](../AGENTS.md) → **Validation defaults**.
5. **Pre-PR review:** Run both [`pre-pr-code-review`](../.cursor/skills/pre-pr-code-review/SKILL.md) and [`pre-pr-architecture-review`](../.cursor/skills/pre-pr-architecture-review/SKILL.md) before creating a PR; address findings or questions interactively first.

## Reference implementation

For parity with the legacy stack, consult **agate-ai-platform** as described in [`AGENTS.md`](../AGENTS.md) → **Reference implementation**.

## See also

- [`docs/OPERATIONS.md`](OPERATIONS.md) — Compose, env vars, local bootstrap.
- [`README.md`](../README.md) — Quick start and ports.
