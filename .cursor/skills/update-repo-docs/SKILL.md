---
name: update-repo-docs
description: Keep Backfield repository docs in sync with code and workflows. Use when behavior, architecture, operations, testing, or developer workflows change.
---

# Update Repo Docs

## Quick Start

1. Identify the source-of-truth doc for the change.
2. Update that doc first instead of only patching `README.md`.
3. Keep terminology aligned with `AGENTS.md`.
4. Add concise guidance, not a long narrative.

## Source-Of-Truth Map

- `docs/README.md`: complete documentation index
- `docs/architecture/`: boundaries, runtime, database, and canonicalization
- `docs/api/`: Agate, Core, Stylebook, processed-item review, and public API contracts
- `docs/development/`: local setup, testing, nodes, entities, and frontend conventions
- `docs/operations/`: runtime configuration, migrations, deployment, and troubleshooting
- `AGENTS.md`: repository workflow, engineering posture, validation, planning, and reviews
