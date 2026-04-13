---
name: review-backfield-change
description: Review Backfield changes for correctness, readability, and cross-layer consistency. Use when reviewing pull requests, checking agent output, or performing self-review before finishing a task.
---

# Review Backfield Change

## Review Order

1. Confirm the diff matches the request and does not include unrelated cleanup.
2. Identify the affected layers: UI, API, worker, core, DB, docs, or ops.
3. When the change touches Agate behavior, nodes, or UI, compare against **agate-ai-platform** (`/Users/cjdd3b/apps/agate-ai-platform` or the reviewer’s clone) for unintended drift or missed parity.
4. Check cross-layer naming and contract consistency.
5. Check validation coverage and docs updates.

## Checklist

- [ ] Logic is correct and edge cases are handled.
- [ ] Functions remain readable and are split when they become too large.
- [ ] API, worker, DB, and docs use consistent names for queues, tasks, statuses, and tables.
- [ ] Where relevant, behavior matches or intentionally diverges from agate-ai-platform (see `AGENTS.md`).
- [ ] Docs were updated when behavior changed.
- [ ] `make lint` and `make test` ran.
- [ ] `make smoke` ran for meaningful runtime changes.
