---
name: update-repo-docs
description: Keep Backfield repository docs in sync with code and workflows. Use when behavior, architecture, operations, testing, or developer workflows change.
---

# Update Repo Docs

## Quick Start

1. Identify the source-of-truth doc for the change.
2. Update that doc first instead of only patching `README.md`.
3. Keep terminology aligned with `AGENTS.md` (including **Reference implementation: agate-ai-platform** when the change relates to parity or ports).
4. Add concise guidance, not a long narrative.

## Source-Of-Truth Map

- `docs/ARCHITECTURE.md`: package boundaries and runtime flow
- `docs/NODES.md`: Agate pipeline node profiles, layers, review tiers, checklists
- `docs/API.md`: route and orchestration behavior
- `docs/FRONTEND.md`: UI patterns and node sync flow (panel design; links to NODES.md for end-to-end node work)
- `docs/DATABASE.md`: schema, migrations, indexing
- `docs/OPERATIONS.md`: compose, env vars, troubleshooting
- `docs/TESTING.md`: validation ladder and smoke flow
- `docs/AGENT_WORKFLOWS.md`: task-based checklists
