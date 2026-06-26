---
name: pre-pr-architecture-review
description: Review whether a branch still fits Backfield's architecture before opening a pull request. Use proactively before creating PRs, or when asked for an architecture review, design review, layering review, package-boundary review, or bigger-picture fit check.
---

# Pre-PR Architecture Review

Run this before creating a pull request.

## Goal

Check that the change still fits the repo's intended shape: package boundaries, service responsibilities, data ownership, runtime flow, and parity expectations.

## Review priorities

1. Boundary fit: does code live in the right app/package/doc, or is logic leaking across layers?
2. Dependency direction: are new imports, APIs, or shared utilities preserving the intended architecture?
3. Operational fit: does the change add env vars, queues, migrations, bootstrap logic, or runtime coupling that should be documented or reconsidered?
4. Long-term shape: does this move the codebase toward a cleaner system, or add incidental complexity that should be challenged now?

## How to run the review

1. Read the relevant source-of-truth docs first (`AGENTS.md`, `docs/ARCHITECTURE.md`, plus API/DB/FRONTEND/OPERATIONS as needed).
2. Inspect the diff and map it to affected layers.
3. Compare to existing repo conventions.
4. Identify architectural mismatches, missing doc updates, hidden coupling, or misplaced ownership.
5. Raise concerns interactively before PR creation when the right answer is not obvious.

## Output expectations

- Surface bigger-picture findings first, not file-by-file commentary.
- Explain what architectural rule or repo convention is being strained.
- Recommend the simplest change that restores alignment.
- If the architecture still holds, say so explicitly and mention any assumptions that future work should revisit.

## Interactive questions

Ask focused questions when a design choice is unresolved. Good examples:
- Should this live in `agate-runtime`, or is it really app-specific behavior?
- Is this a one-off env var, or should it be part of a documented operational contract?
