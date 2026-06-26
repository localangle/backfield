---
name: write-a-prd
description: >-
  Creates a PRD through user interview, codebase exploration, and module design,
  then saves it under prd/<slug>/prd.md at the repo root (gitignored). Use when
  the user wants to write a PRD, create a product requirements document, or plan
  a new feature.
---

# Write a PRD

Turn a free-form description of a problem into a structured PRD file through codebase exploration and a thorough user interview.

## Output location

Each initiative lives in its **own directory** under **`prd/`** at the **repository root** (same level as `Makefile` / `AGENTS.md`):

**`prd/<slug>/prd.md`**

- `<slug>` is a **kebab-case** directory name (e.g. `make-map-interface`).
- The **`prd/`** tree is **gitignored** so local PRDs stay out of version control.
- Create `prd/<slug>/` when saving if it does not exist.

Downstream work (**prd-to-issues**, **issues-to-tasks**) uses **`prd/<slug>/issues/…`** and per-issue **`tasks/…`** under the same slug — see those skills.

Do not save under a different root layout unless the user explicitly directs a one-off exception for that session.

## When to apply

- The user wants a **PRD**, **product requirements document**, or structured **feature plan** before implementation.
- The goal is a **saved artifact** at `prd/<slug>/prd.md` (usually Markdown), not just chat notes.

## Process

### 1. Collect the plan

Ask the user for a long, detailed description of the problem they want to solve and any initial ideas for solutions. There is no required format — a brain dump is fine. The goal is to understand their thinking before touching the codebase.

Also ask for the **slug**: the directory name **`prd/<slug>/`** (kebab-case, stable, URL-safe). Confirm the PRD file will be **`prd/<slug>/prd.md`** (format is almost always Markdown).

### 2. Explore the codebase

**Before** the deep interview pass, explore the repo to verify assertions and understand current implementation. Look for:

- Modules and files that will be affected by this change
- Existing patterns, conventions, and abstractions to follow or build on
- Anything that contradicts or complicates the user's description of the current state

Use `AGENTS.md`, `docs/`, and code search as needed.

### 3. Interview the user

Interview the user about every aspect of the plan until there is a **shared, unambiguous** understanding. Walk down each branch of the design tree; resolve dependencies between decisions **one by one**.

- Do **not** move to the next branch until the current one is resolved.
- Do **not** accept vague answers — if the user says "it depends", ask what it depends on and resolve **each** case.

Cover at minimum:

- Every **actor** who interacts with the feature and what they need
- Every **failure mode** and what the correct behaviour is
- Every **edge case** that the user stories imply
- Every **integration** with existing modules or external systems
- Any decisions that would be **difficult or expensive to reverse**

### 4. Design the modules

Sketch the major modules to be built or modified. Actively look for **deep modules** — significant functionality behind a simple, stable, testable interface (the opposite of shallow, leaky abstractions). Prefer **fewer, deeper** modules over many thin ones.

For each module, confirm with the user:

- Does this match their expectations?
- Should tests be written for this module?
- Which parts of its interface are likely to change, and which are stable?

### 5. Write the PRD

Once there is a complete shared understanding, write the PRD using the template below and **save it** to **`prd/<slug>/prd.md`** (create `prd/<slug>/` if needed).

## PRD output template

Use this structure for the saved document (replace placeholders; omit empty sections only if truly N/A):

```markdown
# PRD: <feature name>

## Problem Statement

The problem the user is facing, from the user's perspective. Not a technical description — describe the gap between what exists and what is needed.

## Solution

The solution to the problem, from the user's perspective. Not an implementation plan — describe what will be true when the feature is complete.

## User Stories

A long, numbered list of user stories covering all aspects of the feature. Each story follows the format:

> As a `<actor>`, I want `<feature>`, so that `<benefit>`.

Be exhaustive. Include stories for error states, edge cases, and secondary actors. A story that implies a behaviour should have a corresponding story for the failure case.

## Implementation Decisions

Decisions made during the interview that constrain or shape the implementation. Include:

- Modules to be built or modified
- Interfaces of those modules
- Architectural decisions and their rationale
- Schema changes
- API contracts
- Specific interaction patterns

Do NOT include file paths or code snippets — these become outdated quickly.

## Module Design

For each module identified in step 4:

- **Name**: what to call it
- **Responsibility**: the single thing it owns
- **Interface**: what callers need to know (inputs, outputs, failure modes)
- **Tested**: yes / no

## Testing Decisions

- What makes a good test for this feature (test external behaviour, not implementation details)
- Which modules will have tests written
- Prior art in the codebase — similar tests to use as reference

## Out of Scope

Explicit list of things that will not be addressed in this PRD. Be specific — vague out-of-scope items create ambiguity later.

## Open Questions

Any unresolved questions that could not be answered during the interview. Each question should have an owner and a suggested resolution path.

## Further Notes

Any context, constraints, or decisions that do not fit the above sections.
```

## Out of scope for this skill

- This skill produces **`prd/<slug>/prd.md`**, not production code or migrations.
- It does **not** replace `docs/AGENTIC.md` → **Planning multi-step work** for large refactors unless the user explicitly wants the PRD to live there or to align with it.
