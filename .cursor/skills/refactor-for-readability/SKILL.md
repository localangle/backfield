---
name: refactor-for-readability
description: Improve Backfield code readability without changing behavior. Use when functions are too large, names are unclear, or code is harder to scan than necessary.
---

# Refactor For Readability

## Principles

- Prefer explicit, readable code over clever or heavily idiomatic code.
- Split large functions into smaller focused helpers, including private helpers.
- Keep imports at the top unless a local import is required for a documented reason.
- Preserve behavior and stay within the requested scope.

## Checklist

- [ ] The refactor keeps the same behavior.
- [ ] Large functions are broken into smaller named helpers where it improves clarity.
- [ ] Names are descriptive and consistent with nearby code.
- [ ] No speculative abstraction was introduced.
- [ ] Relevant tests still pass.
