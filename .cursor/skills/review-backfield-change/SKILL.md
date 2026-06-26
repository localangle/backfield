---
name: review-backfield-change
description: Review Backfield changes for correctness, readability, and cross-layer consistency. Use when reviewing pull requests, checking agent output, or performing self-review before finishing a task.
---

# Review Backfield Change

## Review Order

1. Confirm the diff matches the request and does not include unrelated cleanup.
2. Identify the affected layers: UI, API, worker, core, DB, docs, or ops.
3. Check cross-layer naming and contract consistency.
4. Check validation coverage and docs updates.

## Checklist

- [ ] Logic is correct and edge cases are handled.
- [ ] Functions remain readable and are split when they become too large.
- [ ] API, worker, DB, and docs use consistent names for queues, tasks, statuses, and tables.
- [ ] Docs were updated when behavior changed.
- [ ] `make lint` and `make test` ran.
- [ ] `make smoke` ran for meaningful runtime changes.
