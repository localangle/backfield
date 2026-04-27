---
name: issues-to-tasks
description: >-
  Breaks a single vertical-slice issue into concrete, ordered, AI-executable
  tasks. Saves one task.md per task under prd/<slug>/issues/<issue-dir>/tasks/
  in the gitignored prd/ tree. Use when the user wants to implement an issue,
  start work on a ticket, or break down an issue into smaller steps.
---

# Issues to Tasks

Break a **single** vertical-slice issue into concrete, ordered tasks that can each be completed in one focused AI session.

## Output location

Tasks live **under the issue directory**, each task in its **own subdirectory** with a markdown file (parallel to how each issue has **`issues/<issue-dir>/issue.md`**):

**`prd/<slug>/issues/<issue-dir>/tasks/<task-dir>/task.md`**

- **`<slug>`** and **`<issue-dir>`** match the layout from [`prd-to-issues`](../prd-to-issues/SKILL.md) (e.g. `prd/make-map-interface/issues/02-draw-pins/`).
- **`<task-dir>`** is **`MM-kebab-short-title`** where **`MM`** is zero-padded order (`01`, `02`, …) and **`kebab-short-title`** summarizes the task.
- Each task is exactly **`task.md`** inside its **`tasks/<task-dir>/`** folder.

Create `prd/<slug>/issues/<issue-dir>/tasks/` and each task subdirectory when saving.

Do not write tasks outside this layout unless the user explicitly directs a one-off exception.

## When to apply

- The user wants to **implement an issue**, **start work on a ticket**, or **break an issue into smaller steps**.
- The issue is typically **`prd/<slug>/issues/<issue-dir>/issue.md`** from **prd-to-issues**.

## Process

### 1. Locate the issue

Ask the user which issue to decompose: path to **`prd/<slug>/issues/<issue-dir>/issue.md`**, or **`slug` + `issue-dir`**, or enough context (URL, pasted header) to identify it.

Read that **`issue.md`**.

Infer the PRD path **`prd/<slug>/prd.md`** (parent of `issues/` is `prd/<slug>/`). Read the PRD for context. Do **not** edit the PRD.

If **`issue.md`** still has a **Parent PRD** field pointing at **`../../prd.md`**, treat that as confirmation of layout.

### 2. Explore the codebase

Explore the parts of the codebase this issue touches. Focus on:

- Files and modules that will be created or modified
- Existing patterns to follow (naming, error handling, test layout)
- Interfaces or contracts this issue must respect

### 3. Draft the task list

Break the issue into **ordered** tasks. Each task must:

- Be completable in a **single AI session** (one focused prompt exchange)
- Have a **clear, verifiable output** (a file, a passing test, a working endpoint)
- Respect **dependency order**: schema before logic, logic before API, API before UI; tests **alongside** or **immediately after** each layer

Label each task with its **type**:

- **WRITE**: create or modify production code
- **TEST**: write or update tests
- **MIGRATE**: schema or data migration
- **CONFIG**: environment, tooling, or infrastructure change
- **REVIEW**: human decision required before proceeding

Prefer **WRITE** and **TEST** tasks **interleaved** over a block of WRITE then a block of TEST.

### 4. Quiz the user

Present the proposed task list as a **numbered list**. For each task show:

- **Title**: short imperative description (e.g. “Add `user_id` column to `sessions` table”)
- **Proposed directory**: `tasks/<MM-kebab-short-title>/`
- **Type**: WRITE / TEST / MIGRATE / CONFIG / REVIEW
- **Output**: what exists or passes when this task is done
- **Depends on**: task numbers that must complete first

Ask the user:

- Does the **order** feel right?
- Are any tasks **too large** for one session?
- Are any tasks **too small** and should be merged?
- Are all **REVIEW** tasks correctly identified?

Iterate until the user **approves** the list.

### 5. Write the task files

For each approved task, write **`prd/<slug>/issues/<issue-dir>/tasks/<task-dir>/task.md`** using the template below. **Number tasks** sequentially; use those numbers in **Depends on** (reference sibling task numbers; optionally add sibling **`task-dir`** names for clarity).

**Do not** modify **`issue.md`** or **`prd.md`**.

## Task file template

Each **`task.md`** describes **one** task:

```markdown
# Task <n>: <Task title>

**Parent issue**: `../../issue.md` (Issue <issue-number>: <short issue title>)
**Parent PRD**: `../../../prd.md`
**Type**: WRITE / TEST / MIGRATE / CONFIG / REVIEW
**Output**: <what exists or passes when done>
**Depends on**: Task <m> / none

<A short paragraph describing exactly what to do. Written as an instruction to the AI that will execute it. Include: which files to touch, which pattern to follow, which existing code to use as reference. Do NOT include code snippets — describe intent, not implementation.>
```

## Out of scope for this skill

- Editing **`issue.md`** or **`prd.md`** — read-only.
- Executing tasks (implementation is separate work).
