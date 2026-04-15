---
name: grill-me
description: >-
  Stress-tests plans and designs through sequential Q&A until decisions align; explores the codebase when facts live in code. Use in Cursor Plan mode, when the user wants to stress-test a plan, get grilled on a design, or says "grill me".
---

# Grill me (plan stress-test)

## When to apply

- The session is in **Plan mode**, or the user is explicitly **planning** before implementation.
- The user asks to **stress-test** a plan, **interrogate** a design, or says **"grill me"** (or similar).

## Behavior

1. **One question at a time.** Do not list a batch of questions; wait for an answer (or confirmation) before the next question.
2. **Walk the decision tree.** Cover branches in a sensible order so earlier answers **unlock** dependent questions. Call out when a later choice would invalidate an earlier one.
3. **Recommended answer:** After each question, state a **concise recommended option** and why it fits this repo (point to `AGENTS.md`, `docs/`, or code when useful).
4. **Codebase over guessing:** If the answer depends on how Backfield is structured, **read or search the repo** (files, patterns, existing APIs) instead of assuming. Summarize what you found in one or two sentences, then ask or decide.
5. **Shared understanding:** Continue until major forks are resolved or the user stops the loop. Offer a short **recap** of agreed decisions before handing off to implementation.

## Out of scope

- This skill does **not** replace `docs/PLANS.md` or project planning docs; it sharpens the plan interactively.
- Once the user switches to implementation-only work, default back to normal agent behavior unless they invoke grilling again.
