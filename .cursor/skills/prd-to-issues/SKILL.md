---
name: prd-to-issues
description: >-
  Breaks a PRD into independently-grabbable issues using tracer-bullet vertical
  slices. Writes one issue.md per slice under prd/<slug>/issues/<dir>/ within
  the gitignored prd/ tree. Use when the user wants to convert a PRD to issues,
  create implementation tickets, or break down a PRD into work items.
---

# PRD to Issues

Break a PRD into independently-grabbable issues using **vertical slices** (tracer bullets).

## Output location

Issues live **under the same initiative directory as the PRD**:

**`prd/<slug>/issues/<issue-dir>/issue.md`**

- `<slug>` matches the PRD folder (PRD file is **`prd/<slug>/prd.md`** — see [`write-a-prd`](../write-a-prd/SKILL.md)).
- **`<issue-dir>`** is one directory per vertical slice, named **`NN-kebab-short-title`** where **`NN`** is a zero-padded sequence number (`01`, `02`, …) for stable ordering and **`kebab-short-title`** summarizes the slice (e.g. `01-map-shell`, `02-draw-pins`).
- Each slice is exactly **`issue.md`** inside its directory (not one combined issues file).

Create `prd/<slug>/issues/` and each `prd/<slug>/issues/<issue-dir>/` when writing.

Do not write issues outside this layout unless the user explicitly directs a one-off exception.

## When to apply

- The user wants to **convert a PRD to issues**, **create implementation tickets**, or **break a PRD into work items**.
- The PRD is often **`prd/<slug>/prd.md`**; it may live elsewhere if the user points to another path (still mirror the **`issues/<issue-dir>/issue.md`** pattern under that PRD’s parent when possible).

## Process

### 1. Locate the PRD

Ask the user for the **PRD file** path (read it; do not edit it). Default: **`prd/<slug>/prd.md`**.

Confirm **`<slug>`** (the parent directory name of `prd.md`) so issue paths stay consistent.

### 2. Explore the codebase (optional)

If the codebase has not already been explored for this workstream, explore it to understand the current implementation. Focus on modules called out in the PRD’s **Module Design** section.

### 3. Draft vertical slices

Break the PRD into **tracer bullet** issues. Each issue is a **thin vertical slice** that cuts through **all** relevant integration layers end-to-end — for example schema, logic, API, UI, and tests — not a horizontal slice of a single layer.

Slices may be **HITL** or **AFK**:

- **HITL** (Human In The Loop): requires a human decision or review during implementation — e.g. architectural choice, design review, or approval of a schema migration.
- **AFK** (Away From Keyboard): can be implemented and merged without that human gate.

Prefer **AFK** over **HITL** wherever possible.

**Vertical slice rules**

- Each slice delivers a narrow but **complete** path through every relevant layer.
- A completed slice is **demoable** or **independently verifiable**.
- Prefer **many thin** slices over few thick ones.
- Slices that **cannot** be verified on their own are too coarse.

### 4. Quiz the user

Present the proposed breakdown as a **numbered list**. For each slice show:

- **Title**: short descriptive name
- **Proposed directory**: `issues/<NN-kebab-short-title>/`
- **Type**: HITL / AFK
- **Blocked by**: which other slices (by **issue number** or **`NN`** / directory name) must complete first
- **User stories covered**: which **numbered** user stories from the PRD this addresses

Ask the user:

- Does the granularity feel right? (too coarse / too fine)
- Are the dependency relationships correct?
- Should any slices be merged or split further?
- Are all HITL slices correctly identified?

**Heuristic:** Flag any slice that addresses **more than 2–3** user stories or would likely take **more than half a day** — it is probably too coarse; propose a split.

Iterate until the user **approves** the breakdown.

### 5. Write the issue files

For each approved slice, write **`prd/<slug>/issues/<issue-dir>/issue.md`** using the template below. **Number issues sequentially** (`# Issue 1:`, `# Issue 2:`, …); use those numbers in **Blocked by** and in cross-references. Order creation follows **dependency order** (blockers first).

**Parent PRD** in each `issue.md`: use the path **`../../prd.md`** (relative from `issues/<issue-dir>/issue.md` up to `prd/<slug>/prd.md`).

**Do not** modify the PRD file.

## Issue file template

Each `issue.md` uses this structure (one file per vertical slice):

```markdown
# Issue <n>: <title>

**Type**: HITL / AFK
**Blocked by**: Issue <m> / None — can start immediately

### Parent PRD

`../../prd.md`

### What to build

A concise description of this vertical slice. Describe the end-to-end behaviour, not layer-by-layer implementation steps. Reference sections of the PRD rather than duplicating content.

### How to verify

Exactly how a developer (or the AI implementing this) confirms the slice is complete:

- **Manual**: step-by-step instructions to demo it
- **Automated**: what the test asserts

### Acceptance criteria

- [ ] Given <context>, when <action>, then <outcome>
- [ ] Given <failure condition>, then <expected behaviour>

### User stories addressed

- User story <n>: <short title>
- User story <n>: <short title>
```

## Out of scope for this skill

- Changing or “fixing” the PRD — read-only for the PRD path the user gave.
- Executing the issues (implementation belongs in normal dev workflow).
