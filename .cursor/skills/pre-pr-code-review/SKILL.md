---
name: pre-pr-code-review
description: Review a branch or diff for cleanup opportunities before opening a pull request. Use proactively before creating PRs, or when asked for a code review, cleanup pass, simplification review, dead-code review, or readability review.
---

# Pre-PR Code Review

Run this before creating a pull request.

## Goal

Make the change set cleaner, smaller, and easier to understand before anyone else reviews it.

## Review priorities

1. Look for simplifications: smaller helpers, clearer names, less branching, less duplication.
2. Look for removable code: dead paths, obsolete comments, stale helpers, redundant tests, unused imports or fields.
3. Look for readability and style issues: oversized functions, awkward control flow, inconsistent naming, unclear docs, formatting or typing slips.
4. Look for correctness and regression risk: edge cases, missing validation, contract drift, untested behavior.

## How to run the review

1. Inspect the actual diff first. Confirm it matches the task and does not include unrelated cleanup.
2. Compare against nearby patterns in Backfield.
3. Prefer actionable findings over broad praise.
4. If a cleanup is obviously correct and local, propose or make it before PR creation.
5. If intent is unclear or the cleanup has trade-offs, raise it interactively before proceeding.

## Output expectations

- Present findings ordered by impact.
- For each finding, explain why it matters and what cleaner shape you recommend.
- If no findings remain, say that explicitly and mention any residual risks or test gaps.

## Interactive questions

When you need user input, ask focused questions one at a time. Good examples:
- Should we delete this compatibility path now or keep it for a follow-up?
- Do you want this helper inlined, or reused by a second caller first?
- Is this extra abstraction intentional, or can we collapse it into one readable function?
